"""A-03: authorized decisions, stale evidence, immutable corrections and audit over HTTP."""

import hashlib
import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.attendance.access import AttendanceSettings
from app.attendance.repository import DemoCaseRepository
from app.audit.events import verify_chain
from app.core.contracts import CaseContext, PunchRecord, PunchSource
from app.main import create_app
from app.resolution import totals
from tests.factories import IST, make_case

NOW = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)  # Friday 11:30 IST; case is Thursday 12 Nov
WORK_DATE = date(2026, 11, 12)


def evidenced(exception_id="X-1", employee="E-001") -> CaseContext:
    data = make_case().model_dump()
    data["exception_id"] = exception_id
    data["employee"]["employee_id"] = employee
    data["schedule"]["employee_id"] = employee
    data["punches"] = [
        PunchRecord(
            punch_id=f"{exception_id}-P{i}",
            employee_id=employee,
            ts=datetime(2026, 11, 12, hour, 0, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, hour) in enumerate([("in", 9), ("break_start", 13), ("break_end", 14)])
    ]
    return CaseContext.model_validate(data)


def seed_totals(store, employee="E-001", weekday_hours=8.0):
    """Complete history from the quarter start to Thursday, Friday onwards still scheduled."""
    day = date(2026, 10, 1)
    while day <= date(2026, 11, 15):
        past = day <= WORK_DATE
        store.seed_day_total(
            employee_id=employee,
            work_date=day,
            worked_hours=(weekday_hours if day.weekday() < 5 else 0.0) if past else 0.0,
            scheduled_hours=8.0 if day.weekday() < 5 else 0.0,
            complete=past,
            source="test-seed",
        )
        day += timedelta(days=1)


@pytest.fixture
def env(tmp_path, settings):
    database = tmp_path / "cases.sqlite"
    repo = DemoCaseRepository(database)
    repo.seed_case(evidenced(), manager_id="M-1")
    repo.seed_case(evidenced("X-2", "E-002"), manager_id="M-1")  # no totals provisioned
    repo.seed_case(evidenced("X-3", "E-003"), manager_id="M-2")
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps(
            [
                {
                    "manager_id": manager,
                    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "timezone": "Asia/Kolkata",
                }
                for manager, token in [("M-1", "token-one"), ("M-2", "token-two")]
            ]
        )
    )
    app = create_app(
        settings,
        attendance_settings=AttendanceSettings(
            _env_file=None, enabled=True, database_path=database, credentials_path=credentials
        ),
    )
    store = app.state.resolution_store
    store.clock = lambda: NOW
    seed_totals(store)
    with TestClient(app) as client:
        yield client, store, database


def auth(token="token-one"):
    return {"Authorization": f"Bearer {token}"}


def version(client, exception_id="X-1"):
    return client.get(f"/exceptions/{exception_id}", headers=auth()).json()["evidence_version"]


def approve_body(client, *, key="key-approve-1", ts="2026-11-12T18:00:00+05:30", **extra):
    return {
        "decision": "approve",
        "actions": [{"type": "add_punch", "punch_type": "out", "new_ts": ts}],
        "evidence_version": extra.pop("evidence_version", None) or version(client),
        "idempotency_key": key,
        **extra,
    }


def audit_types(client, exception_id="X-1"):
    return [
        e["event_type"]
        for e in client.get(f"/exceptions/{exception_id}/audit", headers=auth()).json()
    ]


def test_approval_resolves_records_correction_and_audit(env):
    client, store, database = env
    before = version(client)
    response = client.post("/exceptions/X-1/decisions", json=approve_body(client), headers=auth())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "resolved" and result["evidence_version"] == before
    assert result["current_evidence_version"] != before == result["evidence_version"]
    assert version(client) == result["current_evidence_version"]  # older proposals now stale
    events = client.get("/exceptions/X-1/audit", headers=auth()).json()
    assert [e["event_type"] for e in events] == ["DECISION_APPROVED"]
    payload = events[0]["payload"]
    assert payload["policy"] == "IN-KA@2025.1" and payload["evidence_version"] == before
    assert payload["totals"] == {
        "week_start": "2026-11-09",
        "week_other_worked_hours": 24.0,
        "week_remaining_scheduled_hours": 8.0,
        "quarter_start": "2026-10-01",
        "quarter_other_overtime_hours": 0.0,
        "as_of": NOW.isoformat(),
    }
    assert all(c["passed"] for c in payload["checks"]) and len(payload["checks"]) == 6
    listing = client.get("/exceptions", headers=auth()).json()["items"]
    assert {i["exception_id"]: i["status"] for i in listing} == {"X-1": "resolved", "X-2": "open"}
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM corrections").fetchone()[0] == 1
        raw = json.loads(
            db.execute(
                "SELECT evidence_json FROM demo_case_snapshots WHERE exception_id='X-1'"
            ).fetchone()[0]
        )
        assert len(raw["punches"]) == 3  # raw punches untouched
        worked = db.execute(
            "SELECT worked_hours, source FROM day_totals WHERE employee_id='E-001' AND work_date=?",
            (WORK_DATE.isoformat(),),
        ).fetchone()
        assert worked[0] == 8.0 and worked[1].startswith("correction:DEC-")
        assert verify_chain(db)


def test_stale_evidence_rejected_without_side_effects(env):
    client, *_ = env
    body = approve_body(client, evidence_version="sha256:" + "0" * 64)
    response = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert response.status_code == 409
    assert response.json()["errors"][0]["current_evidence_version"] == version(client)
    assert audit_types(client) == []


def test_second_approval_conflicts_and_old_version_is_stale(env):
    client, *_ = env
    first = approve_body(client)
    assert client.post("/exceptions/X-1/decisions", json=first, headers=auth()).status_code == 200
    again = {**first, "idempotency_key": "key-approve-2"}
    stale = client.post("/exceptions/X-1/decisions", json=again, headers=auth())
    assert stale.status_code == 409 and stale.json()["errors"][0]["type"] == "stale_evidence"
    fresh = approve_body(client, key="key-approve-3")
    conflict = client.post("/exceptions/X-1/decisions", json=fresh, headers=auth())
    assert conflict.status_code == 409 and "already resolved" in conflict.json()["detail"]
    assert audit_types(client) == ["DECISION_APPROVED"]


def test_idempotent_replay_and_key_reuse(env):
    client, *_ = env
    body = approve_body(client)
    first = client.post("/exceptions/X-1/decisions", json=body, headers=auth()).json()
    replay = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["decision_id"] == first["decision_id"]
    changed = {**body, "reason": "different"}
    assert client.post("/exceptions/X-1/decisions", json=changed, headers=auth()).status_code == 409
    assert audit_types(client) == ["DECISION_APPROVED"]


def test_invalid_correction_blocked_and_audited(env):
    client, *_ = env
    before = version(client)
    body = approve_body(client, ts="2026-11-12T18:03:00+05:30")  # not an exact anchor
    response = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert response.status_code == 422
    assert response.json()["title"] == "Validation failed"
    events = client.get("/exceptions/X-1/audit", headers=auth()).json()
    assert [e["event_type"] for e in events] == ["APPROVAL_BLOCKED"]
    assert events[0]["actor_type"] == "system" and events[0]["payload"]["requested_by"] == "M-1"
    assert version(client) == before  # nothing changed; the manager can retry


def test_missing_totals_block_approval(env):
    client, *_ = env
    body = approve_body(client, evidence_version=version(client, "X-2"))
    response = client.post("/exceptions/X-2/decisions", json=body, headers=auth())
    assert response.status_code == 422
    overtime = next(c for c in response.json()["errors"] if c["code"] == "OVERTIME_RISK")
    assert "incomplete" in overtime["reason"]
    event = client.get("/exceptions/X-2/audit", headers=auth()).json()[0]
    assert event["payload"]["totals"] is None


def test_totals_changed_after_proposal_block_at_approval(env):
    client, store, _ = env
    body = approve_body(client)
    # 13 h on Mon-Wed: 39 + 8 today + 8 remaining = 55 h > 48 h weekly limit.
    for offset in range(3):
        store.seed_day_total(
            employee_id="E-001",
            work_date=date(2026, 11, 9) + timedelta(days=offset),
            worked_hours=13.0,
            scheduled_hours=8.0,
            complete=True,
            source="late-import",
        )
    response = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert response.status_code == 422
    failed = [c["code"] for c in response.json()["errors"] if not c["passed"]]
    assert "OVERTIME_RISK" in failed


def test_reject_keeps_exception_open(env):
    client, *_ = env
    body = {
        "decision": "reject",
        "evidence_version": version(client),
        "idempotency_key": "key-reject-1",
        "reason": "Employee confirms a different clock-out time.",
    }
    response = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert response.status_code == 200 and response.json()["status"] == "open"
    assert audit_types(client) == ["DECISION_REJECTED"]
    approval = client.post(
        "/exceptions/X-1/decisions", json=approve_body(client, key="key-after"), headers=auth()
    )
    assert approval.status_code == 200


@pytest.mark.parametrize(
    "patch",
    [
        {"actions": []},  # approve without actions
        {"decision": "reject"},  # reject with actions and no reason
        {"source": "manager_edit"},  # edit without a reason
        {"manager_id": "M-1"},  # extra fields are refused
        {"idempotency_key": "short"},
    ],
)
def test_malformed_requests_rejected(env, patch):
    client, *_ = env
    body = {**approve_body(client), **patch}
    assert client.post("/exceptions/X-1/decisions", json=body, headers=auth()).status_code == 422
    assert audit_types(client) == []


def test_authorization_is_server_side(env):
    client, *_ = env
    body = approve_body(client)
    assert client.post("/exceptions/X-1/decisions", json=body).status_code == 401
    spoof = {**auth("token-two"), "X-Resolva-Role": "admin", "X-Manager-Id": "M-1"}
    assert client.post("/exceptions/X-1/decisions", json=body, headers=spoof).status_code == 404
    assert client.get("/exceptions/X-1/audit", headers=auth("token-two")).status_code == 404
    assert client.get("/exceptions/X-3/audit", headers=auth()).status_code == 404
    assert audit_types(client) == []


def test_records_are_append_only_and_tamper_evident(env):
    client, _, database = env
    client.post("/exceptions/X-1/decisions", json=approve_body(client), headers=auth())
    with sqlite3.connect(database) as db:
        for statement in [
            "UPDATE audit_events SET actor_id='someone-else'",
            "DELETE FROM audit_events",
            "UPDATE decisions SET decision='reject'",
            "DELETE FROM corrections",
        ]:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(statement)
        db.execute("DROP TRIGGER audit_events_no_update")  # out-of-band tampering
        db.execute("UPDATE audit_events SET actor_id='someone-else'")
        assert not verify_chain(db)


def test_failure_mid_approval_rolls_everything_back(env, monkeypatch):
    client, _, database = env
    before = version(client)

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(totals, "upsert_day_total", broken)
    with pytest.raises(RuntimeError):
        client.post("/exceptions/X-1/decisions", json=approve_body(client), headers=auth())
    monkeypatch.undo()
    with sqlite3.connect(database) as db:
        for table in ("decisions", "corrections", "audit_events"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert version(client) == before


# ---- trusted totals loader


def loader_env(tmp_path, registry):
    from app.resolution.store import ResolutionStore

    database = tmp_path / "t.sqlite"
    DemoCaseRepository(database)
    store = ResolutionStore(database, registry, clock=lambda: NOW)
    return store, database


def load(database, case, policy, now=NOW):
    with sqlite3.connect(database) as db:
        return totals.load_aggregates(db, case, policy, now)


def test_loader_reads_week_and_quarter(tmp_path, registry, policy):
    store, database = loader_env(tmp_path, registry)
    seed_totals(store, weekday_hours=10.0)  # 1 h daily overtime on each past weekday
    agg = load(database, evidenced(), policy)
    assert agg.week_other_worked_hours == 30.0 and agg.week_remaining_scheduled_hours == 8.0
    assert agg.week_start == date(2026, 11, 9) and agg.quarter_start == date(2026, 10, 1)
    # 1 Oct - 11 Nov weekdays, excluding the work date: 30 days x 1 h
    assert agg.quarter_other_overtime_hours == 30.0
    assert agg.as_of == NOW


@pytest.mark.parametrize(
    "day,complete,reason",
    [
        (date(2026, 11, 10), False, "past day incomplete"),
        (date(2026, 10, 15), False, "quarter day incomplete"),
        (WORK_DATE, False, "work date not certified"),
    ],
)
def test_loader_refuses_incomplete_history(tmp_path, registry, policy, day, complete, reason):
    store, database = loader_env(tmp_path, registry)
    seed_totals(store)
    store.seed_day_total(
        employee_id="E-001",
        work_date=day,
        worked_hours=0.0,
        scheduled_hours=8.0,
        complete=complete,
        source="gap",
    )
    assert load(database, evidenced(), policy) is None, reason


def test_loader_needs_every_week_day(tmp_path, registry, policy):
    store, database = loader_env(tmp_path, registry)
    seed_totals(store)
    with sqlite3.connect(database) as db:
        db.execute("DELETE FROM day_totals WHERE work_date='2026-11-15'")
    assert load(database, evidenced(), policy) is None


def test_loader_uses_worked_hours_once_day_is_complete(tmp_path, registry, policy):
    store, database = loader_env(tmp_path, registry)
    seed_totals(store)
    store.seed_day_total(
        employee_id="E-001",
        work_date=date(2026, 11, 13),
        worked_hours=6.0,
        scheduled_hours=8.0,
        complete=True,
        source="import",
    )
    later = NOW + timedelta(days=1)
    agg = load(database, evidenced(), policy, now=later)
    assert agg.week_other_worked_hours == 30.0 and agg.week_remaining_scheduled_hours == 0.0


@pytest.mark.parametrize(
    "day,start,end",
    [
        (date(2026, 1, 1), date(2026, 1, 1), date(2026, 4, 1)),
        (date(2026, 3, 31), date(2026, 1, 1), date(2026, 4, 1)),
        (date(2026, 11, 12), date(2026, 10, 1), date(2027, 1, 1)),
        (date(2026, 12, 31), date(2026, 10, 1), date(2027, 1, 1)),
    ],
)
def test_quarter_bounds(day, start, end):
    assert totals.quarter_bounds(day) == (start, end)
