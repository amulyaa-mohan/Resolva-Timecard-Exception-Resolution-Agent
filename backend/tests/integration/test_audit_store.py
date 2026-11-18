"""Regression tests for audit findings A2 and A3 (2026-11-18), on SQLite and PostgreSQL.

A2: drafting a proposal must not hold the write lock while the model runs, and a proposal
drafted on evidence that changed meanwhile must not be stored.
A3: a reused X-Trace-Id must not crash a proposal.
"""

from __future__ import annotations

import pytest

from app.ai.providers import MockProvider
from app.core.contracts import GateStatus
from app.resolution.store import DecisionConflict
from tests.integration.test_resolution_api import (  # noqa: F401 (env is a fixture)
    auth,
    env,
    propose,
    seed_totals,
)


class ModelThatWritesMeanwhile:
    """A model that, while 'thinking', lets another writer act on the database."""

    name = "mock"
    model_id = "audit-writer"

    def __init__(self, during):
        self.during = during
        self.inner = MockProvider()
        self.side_effect_error: Exception | None = None

    def is_reachable(self) -> bool:
        return True

    def complete(self, request):
        try:
            self.during()
        except Exception as exc:  # recorded and asserted by the test
            self.side_effect_error = exc
        return self.inner.complete(request)


def test_a2_other_writers_proceed_while_the_model_runs(env, settings):  # noqa: F811
    client, store, database = env

    def another_manager_writes():
        # Before the fix the proposal held the global write lock here: SQLite raised
        # "database is locked" and PostgreSQL blocked until the model call timed out.
        with store._transaction() as connection:
            connection.execute("SELECT 1").fetchone()

    model = ModelThatWritesMeanwhile(another_manager_writes)
    result = store.propose("X-1", "M-1", provider=model, settings=settings)
    assert model.side_effect_error is None, model.side_effect_error
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert database.scalar("SELECT count(*) FROM proposals WHERE exception_id=?", ("X-1",))[0] == 1


def test_a2_proposal_on_changed_evidence_is_not_stored(env, settings):  # noqa: F811
    client, store, database = env

    def evidence_changes_meanwhile():
        with store._transaction() as connection:
            _, revision = store._load(connection, "X-1", "M-1", lock=True)
            store.backend.mark_resolved(connection, "X-1", revision, revision + 1)

    model = ModelThatWritesMeanwhile(evidence_changes_meanwhile)
    with pytest.raises(DecisionConflict, match="evidence changed"):
        store.propose("X-1", "M-1", provider=model, settings=settings)
    assert model.side_effect_error is None, model.side_effect_error
    assert database.scalar("SELECT count(*) FROM proposals WHERE exception_id=?", ("X-1",))[0] == 0


def test_a2_changed_evidence_is_a_409_over_http(env, settings, monkeypatch):  # noqa: F811
    client, store, _ = env
    original = store.propose

    def racing_propose(exception_id, manager_id, *, provider, settings):
        def bump():
            with store._transaction() as connection:
                _, revision = store._load(connection, exception_id, manager_id, lock=True)
                store.backend.mark_resolved(connection, exception_id, revision, revision + 1)

        return original(
            exception_id,
            manager_id,
            provider=ModelThatWritesMeanwhile(bump),
            settings=settings,
        )

    monkeypatch.setattr(store, "propose", racing_propose)
    response = propose(client)
    assert response.status_code == 409
    assert "evidence changed" in response.json()["detail"]


def test_a3_reused_trace_id_does_not_crash(env):  # noqa: F811
    client, _, database = env
    headers = {**auth(), "X-Trace-Id": "sametrace01"}
    first = client.post("/exceptions/X-1/proposal", headers=headers)
    second = client.post("/exceptions/X-1/proposal", headers=headers)
    assert first.status_code == second.status_code == 200, second.text
    count = database.scalar(
        "SELECT count(*) FROM llm_traces WHERE trace_id LIKE ?", ("sametrace01:PRP-%",)
    )[0]
    assert count == 2
    raw = database.scalar(
        "SELECT count(*) FROM llm_raw_outputs WHERE trace_id LIKE ?", ("sametrace01:%",)
    )[0]
    assert raw == 2


def _late_arrival_case():
    """SCHEDULE_DEVIATION for its own employee E-LATE: in 09:25, break 13-14, out 18:00.

    Its own employee, because the PostgreSQL store reads the employee's whole workday: sharing
    E-001's day with X-1 would put two sets of break punches on the same instants."""
    from datetime import datetime

    from app.core.contracts import (
        DEFAULT_SEVERITY,
        CaseContext,
        EmployeeNote,
        ExceptionCode,
        PunchRecord,
        PunchSource,
    )
    from tests.factories import IST
    from tests.integration.test_resolution_api import evidenced

    data = evidenced("X-LATE", "E-LATE").model_dump()
    data["code"] = ExceptionCode.SCHEDULE_DEVIATION
    data["severity"] = DEFAULT_SEVERITY[ExceptionCode.SCHEDULE_DEVIATION]
    data["punches"] = [
        PunchRecord(
            punch_id=f"X-LATE-P{i}",
            employee_id="E-LATE",
            ts=datetime(2026, 11, 12, h, m, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, h, m) in enumerate(
            [("in", 9, 25), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 18, 0)]
        )
    ]
    data["notes"] = [
        EmployeeNote(
            note_id="N-LATE",
            text="The kiosk was down. I arrived at 09:05.",
            submitted_at=datetime(2026, 11, 12, 20, 0, tzinfo=IST),
        ).model_dump()
    ]
    data["detection_details"] = {"reason": "late arrival"}
    return CaseContext.model_validate(data)


def test_approving_an_adjustment_applies_it_once(env):  # noqa: F811
    # Found in the live demo: approval treated adjust_punch as an added punch and crashed.
    client, store, database = env
    client.app.state.attendance_repository.seed_case(_late_arrival_case(), manager_id="M-1")
    seed_totals(store, employee="E-LATE")
    version = client.get("/exceptions/X-LATE", headers=auth()).json()["evidence_version"]
    body = {
        "decision": "approve",
        "actions": [
            {
                "type": "adjust_punch",
                "punch_id": "X-LATE-P0",
                "new_ts": "2026-11-12T09:05:00+05:30",
                "evidence_ref": {"kind": "note", "id": "N-LATE"},
            }
        ],
        "evidence_version": version,
        "idempotency_key": "adjust-approve-1",
    }
    response = client.post("/exceptions/X-LATE/decisions", json=body, headers=auth())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"
    card = client.get("/exceptions/X-LATE/timecard", headers=auth()).json()
    effective_in = [p["ts"] for p in card["effective_punches"] if p["type"] == "in"]
    assert len(effective_in) == 1 and "09:05" in effective_in[0]  # moved, not duplicated
    assert card["net_worked_hours"] == pytest.approx(7 + 55 / 60)  # 09:05-18:00 minus 1 h
    worked = database.scalar(
        "SELECT worked_hours FROM day_totals WHERE employee_id=? AND work_date=?",
        ("E-LATE", "2026-11-12"),
    )[0]
    assert worked == pytest.approx(7 + 55 / 60)  # the day total uses the corrected hours


def test_timecard_reports_every_time_in_the_employee_zone(env):  # noqa: F811
    client, store, _ = env
    client.app.state.attendance_repository.seed_case(_late_arrival_case(), manager_id="M-1")
    seed_totals(store, employee="E-LATE")
    version = client.get("/exceptions/X-LATE", headers=auth()).json()["evidence_version"]
    body = {
        "decision": "approve",
        "actions": [
            {
                "type": "adjust_punch",
                "punch_id": "X-LATE-P0",
                "new_ts": "2026-11-12T03:35:00+00:00",  # 09:05 IST submitted in UTC
                "evidence_ref": {"kind": "note", "id": "N-LATE"},
            }
        ],
        "evidence_version": version,
        "idempotency_key": "tz-approve-1",
    }
    assert client.post("/exceptions/X-LATE/decisions", json=body, headers=auth()).status_code == 200
    card = client.get("/exceptions/X-LATE/timecard", headers=auth()).json()
    assert card["timezone"] == "Asia/Kolkata"
    times = [p["ts"] for p in card["raw_punches"] + card["effective_punches"]]
    times += [a["new_ts"] for a in card["corrections_applied"]]
    assert times and all(t.endswith("+05:30") for t in times), times
    assert card["corrections_applied"][0]["new_ts"].startswith("2026-11-12T09:05")
