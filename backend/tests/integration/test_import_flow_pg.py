"""SHARED-02 path on PostgreSQL: import -> detect -> propose -> validate -> approve -> audit.

Skipped unless TEST_DATABASE_URL names a disposable *_test database.
"""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.ai.pipeline import generate_proposal
from app.ai.providers import MockProvider
from app.attendance.access import AttendanceSettings
from app.core.contracts import CaseContext, GateStatus
from app.main import create_app
from app.resolution import totals
from app.rules.validator import make_validator
from tests.integration.test_resolution_api import _postgres_dsn

psycopg = pytest.importorskip("psycopg")
NOW = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)  # Friday 11:30 IST


def sql(dsn, statement, params=()):
    with psycopg.connect(dsn, autocommit=True) as connection:
        cursor = connection.execute(statement, params)
        return cursor.fetchall() if cursor.description else None


@pytest.fixture
def flow(tmp_path, settings):
    dsn = _postgres_dsn()
    for manager, employee in [("M-1", "E-001"), ("M-2", "E-002")]:
        sql(dsn, "INSERT INTO managers VALUES (%s, 'Asia/Kolkata')", (manager,))
        sql(
            dsn,
            "INSERT INTO employees VALUES (%s, 'BLR-01', 'IN-KA', 'Asia/Kolkata', NULL)",
            (employee,),
        )
        sql(
            dsn,
            "INSERT INTO manager_assignments (manager_id, employee_id, valid_from) "
            "VALUES (%s, %s, now() - interval '1 day')",
            (manager, employee),
        )
    # Trusted history before this week: complete 8 h weekdays since the quarter start.
    day = date(2026, 10, 1)
    while day < date(2026, 11, 9):
        weekday = day.weekday() < 5
        sql(
            dsn,
            "INSERT INTO day_totals VALUES (%s, %s, %s, %s, true, true, 'history', now())",
            ("E-001", day, 8.0 if weekday else 0.0, 8.0 if weekday else 0.0),
        )
        day += timedelta(days=1)
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps(
            [
                {
                    "manager_id": m,
                    "token_sha256": hashlib.sha256(t.encode()).hexdigest(),
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "timezone": "Asia/Kolkata",
                }
                for m, t in [("M-1", "token-one"), ("M-2", "token-two")]
            ]
        )
    )
    app = create_app(
        settings,
        attendance_settings=AttendanceSettings(
            _env_file=None, enabled=True, database_url=dsn, credentials_path=credentials
        ),
    )
    app.state.resolution_store.clock = lambda: NOW
    with TestClient(app) as client:
        yield client, app, dsn


AUTH = {"Authorization": "Bearer token-one"}


def shifts_csv():
    rows = ["employee_id,shift_id,start,end,planned_break_min"]
    for d in range(9, 16):  # Mon 9 - Sun 15 Nov
        if date(2026, 11, d).weekday() < 5:
            rows.append(f"E-001,S-{d},2026-11-{d:02d} 09:00,2026-11-{d:02d} 18:00,60")
    return "\n".join(rows) + "\n"


def punches_csv():
    rows = ["employee_id,timestamp,type,source_event_id"]
    for d in (9, 10, 11, 12):
        rows += [
            f"E-001,2026-11-{d:02d} 09:00,in,k-{d}-1",
            f"E-001,2026-11-{d:02d} 13:00,break_start,k-{d}-2",
            f"E-001,2026-11-{d:02d} 14:00,break_end,k-{d}-3",
        ]
        if d != 12:  # Thursday's clock-out is missing
            rows.append(f"E-001,2026-11-{d:02d} 18:00,out,k-{d}-4")
    return "\n".join(rows) + "\n"


def post_import(client, content, kind="punches", **extra):
    body = {"kind": kind, "format": "csv", "content": content, **extra}
    return client.post("/imports", json=body, headers=AUTH)


def test_import_detect_propose_approve(flow):
    client, app, dsn = flow
    assert post_import(client, shifts_csv(), "shifts").json()["inserted"] == 5
    first = post_import(client, punches_csv())
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["inserted"] == 15
    assert result["detected_exception_ids"] == ["EX-E-001-2026-11-12-MISSING_PUNCH"]
    # Re-import: nothing new, nothing re-detected.
    again = post_import(client, punches_csv()).json()
    assert again["inserted"] == 0 and again["duplicates"] == 15
    assert again["detected_exception_ids"] == []
    # The detected exception is a normal case for the manager and for Track B's pipeline.
    listing = client.get("/exceptions", headers=AUTH).json()
    assert [i["exception_id"] for i in listing["items"]] == ["EX-E-001-2026-11-12-MISSING_PUNCH"]
    case = CaseContext.model_validate(
        client.get("/exceptions/EX-E-001-2026-11-12-MISSING_PUNCH", headers=AUTH).json()
    )
    assert len(case.punches) == 3 and case.schedule.shift_id == "S-12"
    assert len(case.punch_history) == 12  # Mon-Wed, for same-weekday evidence
    store = app.state.resolution_store
    policy = store.registry.resolve(case.employee, case.work_date)
    from app.attendance.postgres import PgConnection

    with psycopg.connect(dsn) as raw:
        connection = PgConnection(raw)
        proposal = generate_proposal(
            case,
            policy,
            provider=MockProvider(),
            validator=make_validator(lambda c: totals.load_aggregates(connection, c, policy, NOW)),
            settings=app.state.settings,
        )
    assert proposal.status == GateStatus.ELIGIBLE, proposal.reasons
    body = {
        "decision": "approve",
        "actions": [a.model_dump(mode="json") for a in proposal.proposal.actions],
        "evidence_version": case.evidence_version,
        "idempotency_key": "flow-approve-1",
    }
    approved = client.post(f"/exceptions/{case.exception_id}/decisions", json=body, headers=AUTH)
    assert approved.status_code == 200, approved.text
    events = client.get(f"/exceptions/{case.exception_id}/audit", headers=AUTH).json()
    assert [e["event_type"] for e in events] == ["EXCEPTION_DETECTED", "DECISION_APPROVED"]
    # Detection now sees the corrected timecard and raises nothing new for Thursday.
    from app.attendance.ingest import run_detection

    assert (
        run_detection(store.backend, store.registry, {"E-001": {date(2026, 11, 12)}}, as_of=NOW)
        == []
    )
    assert sql(
        dsn,
        "SELECT worked_hours, complete FROM day_totals "
        "WHERE employee_id='E-001' AND work_date='2026-11-12'",
    ) == [(8.0, True)]


def test_import_scope_and_partial_rules(flow):
    client, _, dsn = flow
    content = "employee_id,timestamp,type\nE-001,2026-11-12 09:00,in\nE-002,2026-11-12 09:00,in\n"
    preview = client.post(
        "/imports/preview", json={"format": "csv", "content": content}, headers=AUTH
    ).json()
    assert [r["status"] for r in preview["rows"]] == ["valid", "invalid"]
    assert "not assigned" in preview["rows"][1]["error"]
    refused = post_import(client, content)
    assert refused.status_code == 422 and refused.json()["title"] == "Import has invalid rows"
    assert sql(dsn, "SELECT count(*) FROM punches") == [(0,)]
    partial = post_import(client, content, allow_partial=True).json()
    assert partial["inserted"] == 1 and partial["invalid"] == 1
    assert sql(dsn, "SELECT employee_id FROM punches") == [("E-001",)]
    unreadable = client.post(
        "/imports/preview", json={"format": "json", "content": "{bad"}, headers=AUTH
    )
    assert unreadable.status_code == 422
    bad_mapping = client.post(
        "/imports/preview",
        json={"format": "csv", "content": content, "mapping": {"salary": "x"}},
        headers=AUTH,
    )
    assert bad_mapping.status_code == 422
    assert (
        client.post("/imports/preview", json={"format": "csv", "content": content}).status_code
        == 401
    )


def test_display_fields_are_optional_and_never_affect_rules(flow):
    """Migration 0003: organization, location and employee names are display data only."""
    client, _, dsn = flow
    assert post_import(client, shifts_csv(), "shifts").status_code == 200
    first = post_import(client, punches_csv()).json()
    assert first["detected_exception_ids"]  # detection works with no names at all
    listing = client.get("/exceptions", headers=AUTH).json()["items"]
    assert listing[0]["employee_name"] is None
    sql(dsn, "INSERT INTO organizations (org_id, name) VALUES ('ORG-1', 'Demo Operations')")
    sql(
        dsn,
        "INSERT INTO locations (location_id, org_id, name, city, country, timezone) "
        "VALUES ('BLR-01', 'ORG-1', 'Bengaluru Centre', 'Bengaluru', 'India', 'Asia/Kolkata')",
    )
    sql(
        dsn,
        "UPDATE employees SET full_name = 'Aarav Sharma', job_title = 'Support Associate', "
        "pay_type = 'hourly' WHERE employee_id = 'E-001'",
    )
    named = client.get("/exceptions", headers=AUTH).json()["items"]
    assert named[0]["employee_name"] == "Aarav Sharma"
    assert named[0]["exception_id"] == listing[0]["exception_id"]  # nothing else changed
    # Reference data cannot be deleted out from under a site, and pay_type is constrained.
    with pytest.raises(psycopg.errors.IntegrityError):
        sql(dsn, "DELETE FROM organizations WHERE org_id = 'ORG-1'")
    with pytest.raises(psycopg.errors.IntegrityError, match="pay_type"):
        sql(dsn, "UPDATE employees SET pay_type = 'contractor' WHERE employee_id = 'E-001'")
