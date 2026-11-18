"""A-03: authorized decisions, stale evidence, immutable corrections and audit over HTTP."""

import hashlib
import json
import os
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
    data["schedule"]["shift_id"] = f"S-{employee}"
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


class Db:
    """Direct database access for assertions, for either backend."""

    def __init__(self, kind, target):
        self.kind, self.target = kind, target

    def connect(self):
        if self.kind == "sqlite":
            return sqlite3.connect(self.target, isolation_level=None)
        import psycopg

        from app.attendance.postgres import PgConnection

        return PgConnection(psycopg.connect(self.target, autocommit=True))

    def scalar(self, sql, params=()):
        connection = self.connect()
        try:
            return connection.execute(sql, params).fetchone()
        finally:
            (connection.raw if self.kind == "postgres" else connection).close()

    def raw_punch_count(self, exception_id):
        if self.kind == "sqlite":
            row = self.scalar(
                "SELECT evidence_json FROM demo_case_snapshots WHERE exception_id=?",
                (exception_id,),
            )
            return len(json.loads(row[0])["punches"])
        return self.scalar(
            "SELECT count(*) FROM exception_punches WHERE exception_id=?", (exception_id,)
        )[0]


def _postgres_dsn():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set TEST_DATABASE_URL to a disposable *_test PostgreSQL database")
    if not dsn.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a database ending in _test (it is wiped)")
    import psycopg

    from app.attendance.postgres import apply_migrations

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
    apply_migrations(dsn)
    return dsn


@pytest.fixture(params=["sqlite", "postgres"])
def env(request, tmp_path, settings):
    if request.param == "postgres":
        from app.attendance.postgres import PostgresCaseRepository

        dsn = _postgres_dsn()
        repo = PostgresCaseRepository(dsn)
        db = Db("postgres", dsn)
        storage = {"database_url": dsn}
    else:
        database = tmp_path / "cases.sqlite"
        repo = DemoCaseRepository(database)
        db = Db("sqlite", database)
        storage = {"database_path": database}
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
            _env_file=None, enabled=True, credentials_path=credentials, **storage
        ),
    )
    store = app.state.resolution_store
    store.clock = lambda: NOW
    seed_totals(store)
    for employee in ("E-002", "E-003"):  # employees must exist; X-2 has no totals on purpose
        assert db.scalar("SELECT count(*) FROM day_totals WHERE employee_id=?", (employee,))[0] == 0
    with TestClient(app) as client:
        yield client, store, db


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
    assert database.scalar("SELECT count(*) FROM corrections")[0] == 1
    assert database.raw_punch_count("X-1") == 3  # raw punches untouched
    worked = database.scalar(
        "SELECT worked_hours, source FROM day_totals WHERE employee_id='E-001' AND work_date=?",
        (WORK_DATE.isoformat(),),
    )
    assert worked[0] == 8.0 and worked[1].startswith("correction:DEC-")
    connection = database.connect()
    assert verify_chain(connection)


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
    statements = [
        "UPDATE audit_events SET actor_id='someone-else'",
        "DELETE FROM audit_events",
        "UPDATE decisions SET decision='reject'",
        "DELETE FROM corrections",
    ]
    if database.kind == "postgres":
        statements += ["UPDATE punches SET ts = ts", "TRUNCATE audit_events"]
    for statement in statements:
        with pytest.raises(Exception, match="append-only"):
            database.scalar(statement)
    connection = database.connect()
    trigger = (
        "DROP TRIGGER audit_events_append_only ON audit_events"
        if database.kind == "postgres"
        else "DROP TRIGGER audit_events_no_update"
    )
    connection.execute(trigger)  # out-of-band tampering by someone with DDL rights
    connection.execute("UPDATE audit_events SET actor_id='someone-else'")
    assert not verify_chain(connection)


def test_failure_mid_approval_rolls_everything_back(env, monkeypatch):
    client, _, database = env
    before = version(client)

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(totals, "upsert_day_total", broken)
    with pytest.raises(RuntimeError):
        client.post("/exceptions/X-1/decisions", json=approve_body(client), headers=auth())
    monkeypatch.undo()
    for table in ("decisions", "corrections", "audit_events"):
        assert database.scalar(f"SELECT count(*) FROM {table}")[0] == 0
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


# ---- A-06 bulk decisions


def test_bulk_decisions_are_independent_per_item(env):
    client, *_ = env
    good = approve_body(client, key="bulk-key-1")
    items = [
        {**good, "exception_id": "X-1"},
        # No totals for E-002: insufficient evidence, so this item fails on its own.
        {
            **approve_body(client, key="bulk-key-2", evidence_version=version(client, "X-2")),
            "exception_id": "X-2",
        },
        {**approve_body(client, key="bulk-key-3"), "exception_id": "X-3"},  # another manager's
        {**good, "idempotency_key": "bulk-key-4", "exception_id": "X-1"},  # now stale
    ]
    response = client.post("/exceptions/bulk-decisions", json={"items": items}, headers=auth())
    assert response.status_code == 200, response.text
    results = response.json()
    assert [(r["exception_id"], r["status_code"]) for r in results] == [
        ("X-1", 200),
        ("X-2", 422),
        ("X-3", 404),
        ("X-1", 409),
    ]
    assert results[0]["result"]["status"] == "resolved"
    overtime = next(c for c in results[1]["checks"] if c["code"] == "OVERTIME_RISK")
    assert overtime["outcome"] == "insufficient_evidence"
    assert audit_types(client) == ["DECISION_APPROVED"]
    assert audit_types(client, "X-2") == ["APPROVAL_BLOCKED"]


def test_bulk_request_validation(env):
    client, *_ = env
    item = {**approve_body(client, key="same-key-1"), "exception_id": "X-1"}
    duplicate_keys = client.post(
        "/exceptions/bulk-decisions",
        json={"items": [item, {**item, "exception_id": "X-2"}]},
        headers=auth(),
    )
    assert duplicate_keys.status_code == 422
    assert (
        client.post("/exceptions/bulk-decisions", json={"items": []}, headers=auth()).status_code
        == 422
    )
    too_many = [{**item, "idempotency_key": f"key-{i:04d}"} for i in range(51)]
    assert (
        client.post(
            "/exceptions/bulk-decisions", json={"items": too_many}, headers=auth()
        ).status_code
        == 422
    )
    assert client.post("/exceptions/bulk-decisions", json={"items": [item]}).status_code == 401
    assert audit_types(client) == []


# ---- AI proposal endpoint, escalation state and the effective timecard


def propose(client, exception_id="X-1"):
    return client.post(f"/exceptions/{exception_id}/proposal", headers=auth())


def test_proposal_is_eligible_persisted_and_audited(env):
    client, _, database = env
    response = propose(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "eligible", result["reasons"]
    assert result["proposal"]["actions"][0]["punch_type"] == "out"
    assert result["validation"]["passed"] and len(result["validation"]["checks"]) == 6
    assert result["evidence_version"] == version(client)
    assert result["policy_version"] == "2025.1"
    # The draft is stored with its model trace, and proposing changes no state.
    stored = database.scalar(
        "SELECT status, policy_pack_id, requested_by FROM proposals WHERE exception_id=?", ("X-1",)
    )
    assert stored == ("eligible", "IN-KA", "M-1")
    trace = database.scalar("SELECT provider, attempts FROM llm_traces")
    assert trace[0] == "mock" and trace[1] >= 1
    assert audit_types(client) == ["PROPOSAL_GENERATED"]
    event = client.get("/exceptions/X-1/audit", headers=auth()).json()[0]
    assert event["actor_type"] == "ai" and event["payload"]["status"] == "eligible"
    assert client.get("/exceptions", headers=auth()).json()["items"][0]["status"] == "open"
    # A manager can then approve exactly what was drafted.
    body = {
        "decision": "approve",
        "actions": result["proposal"]["actions"],
        "evidence_version": result["evidence_version"],
        "idempotency_key": "after-proposal-1",
    }
    approved = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert approved.status_code == 200 and approved.json()["status"] == "resolved"


def test_proposal_without_totals_escalates_and_is_recorded(env):
    client, *_ = env
    result = propose(client, "X-2").json()
    assert result["status"] == "escalated"
    assert any("OVERTIME_RISK" in r for r in result["reasons"])
    listing = {
        i["exception_id"]: i["status"]
        for i in client.get("/exceptions", headers=auth()).json()["items"]
    }
    assert listing == {"X-1": "open", "X-2": "escalated"}
    only = client.get("/exceptions?status=escalated", headers=auth()).json()
    assert [i["exception_id"] for i in only["items"]] == ["X-2"] and only["total"] == 1
    assert audit_types(client, "X-2") == ["PROPOSAL_GENERATED"]


def test_proposal_authorization_and_resolved_cases(env):
    client, *_ = env
    assert propose(client, "X-3").status_code == 404  # another manager's employee
    assert client.post("/exceptions/X-1/proposal").status_code == 401
    client.post(
        "/exceptions/X-1/decisions", json=approve_body(client, key="pre-approve-1"), headers=auth()
    )
    conflict = propose(client)
    assert conflict.status_code == 409 and "already resolved" in conflict.json()["detail"]


def test_manager_escalation_is_persisted(env):
    client, *_ = env
    body = {
        "decision": "escalate",
        "evidence_version": version(client),
        "idempotency_key": "escalate-key-1",
        "reason": "Employee disputes the recorded start time.",
    }
    response = client.post("/exceptions/X-1/decisions", json=body, headers=auth())
    assert response.status_code == 200 and response.json()["status"] == "escalated"
    assert audit_types(client) == ["DECISION_ESCALATED"]
    assert client.get("/exceptions?status=escalated", headers=auth()).json()["total"] == 1
    without_reason = {**body, "idempotency_key": "escalate-key-2", "reason": ""}
    assert (
        client.post("/exceptions/X-1/decisions", json=without_reason, headers=auth()).status_code
        == 422
    )
    with_actions = {
        **body,
        "idempotency_key": "escalate-key-3",
        "actions": approve_body(client)["actions"],
    }
    assert (
        client.post("/exceptions/X-1/decisions", json=with_actions, headers=auth()).status_code
        == 422
    )
    # Approving afterwards supersedes the escalation.
    approved = client.post(
        "/exceptions/X-1/decisions",
        json=approve_body(client, key="after-escalation-1"),
        headers=auth(),
    )
    assert approved.status_code == 200
    assert client.get("/exceptions", headers=auth()).json()["items"][0]["status"] == "resolved"


def test_effective_timecard_shows_corrections(env):
    client, *_ = env
    before = client.get("/exceptions/X-1/timecard", headers=auth()).json()
    assert len(before["raw_punches"]) == 3 and before["corrections_applied"] == []
    assert before["net_worked_hours"] is None  # unpaired until the fix is approved
    client.post(
        "/exceptions/X-1/decisions", json=approve_body(client, key="timecard-key-1"), headers=auth()
    )
    after = client.get("/exceptions/X-1/timecard", headers=auth()).json()
    assert len(after["raw_punches"]) == 3  # raw evidence unchanged
    assert len(after["effective_punches"]) == 4 and after["net_worked_hours"] == 8.0
    assert after["corrections_applied"][0]["type"] == "add_punch"
    assert client.get("/exceptions/X-3/timecard", headers=auth()).status_code == 404
