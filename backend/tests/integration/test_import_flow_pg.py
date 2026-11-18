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


# ---- employee notes: import, attach window, evidence

NOTE_TUESDAY = "I left at 6:00 pm on Thursday but forgot to punch out."


def notes_csv(*rows):
    import csv
    import io

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["employee_id", "submitted_at", "text"])
    writer.writerows(rows)
    return out.getvalue()


def thursday_exception(client):
    assert post_import(client, shifts_csv(), "shifts").status_code == 200
    assert post_import(client, punches_csv()).status_code == 200
    return "EX-E-001-2026-11-12-MISSING_PUNCH"


def test_note_attaches_only_inside_the_window_and_changes_the_evidence(flow):
    client, _, dsn = flow
    exception = thursday_exception(client)
    before = client.get(f"/exceptions/{exception}", headers=AUTH).json()
    assert before["notes"] == []
    content = notes_csv(
        ("E-001", "2026-11-12 19:10", NOTE_TUESDAY),  # the work date: attached
        ("E-001", "2026-11-13 08:00", "Written the next morning"),  # the day after: attached
        ("E-001", "2026-11-14 09:00", "Two days later"),  # outside the window
        ("E-001", "2026-11-11 19:00", "The evening before"),  # before the work date
    )
    result = post_import(client, content, "notes")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["inserted"] == 4 and len(body["notes_attached"][exception]) == 2
    after = client.get(f"/exceptions/{exception}", headers=AUTH).json()
    assert [n["text"] for n in after["notes"]] == [NOTE_TUESDAY, "Written the next morning"]
    # Notes are evidence, so a draft made before them is correctly stale.
    assert after["evidence_version"] != before["evidence_version"]
    events = client.get(f"/exceptions/{exception}/audit", headers=AUTH).json()
    assert [e["event_type"] for e in events][-1] == "EVIDENCE_ATTACHED"
    assert sql(dsn, "SELECT count(*) FROM employee_notes") == [(4,)]


def test_note_import_is_idempotent_and_atomic(flow):
    client, _, dsn = flow
    exception = thursday_exception(client)
    content = notes_csv(("E-001", "2026-11-12 19:10", NOTE_TUESDAY))
    first = post_import(client, content, "notes").json()
    again = post_import(client, content, "notes").json()
    assert first["inserted"] == 1 and again["inserted"] == 0 and again["duplicates"] == 1
    assert again["notes_attached"] == {}  # nothing new to link, no second audit event
    events = client.get(f"/exceptions/{exception}/audit", headers=AUTH).json()
    assert [e["event_type"] for e in events].count("EVIDENCE_ATTACHED") == 1
    assert sql(dsn, "SELECT count(*) FROM exception_notes") == [(1,)]


def test_note_before_the_exception_is_attached_when_detection_runs(flow):
    client, _, dsn = flow
    content = notes_csv(("E-001", "2026-11-12 19:10", NOTE_TUESDAY))
    assert post_import(client, content, "notes").json()["notes_attached"] == {}
    assert sql(dsn, "SELECT count(*) FROM exception_notes") == [(0,)]
    exception = thursday_exception(client)  # detection now raises it and links the waiting note
    case = client.get(f"/exceptions/{exception}", headers=AUTH).json()
    assert [n["text"] for n in case["notes"]] == [NOTE_TUESDAY]


def test_notes_are_scoped_and_never_touch_resolved_exceptions(flow):
    client, app, dsn = flow
    exception = thursday_exception(client)
    other = notes_csv(("E-002", "2026-11-12 19:10", "Not my employee"))
    refused = post_import(client, other, "notes")
    assert refused.status_code == 422 and refused.json()["title"] == "Import has invalid rows"
    assert sql(dsn, "SELECT count(*) FROM employee_notes") == [(0,)]
    case = client.get(f"/exceptions/{exception}", headers=AUTH).json()
    approve = {
        "decision": "approve",
        "actions": [
            {"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}
        ],
        "evidence_version": case["evidence_version"],
        "idempotency_key": "notes-approve-key",
    }
    assert (
        client.post(f"/exceptions/{exception}/decisions", json=approve, headers=AUTH).status_code
        == 200
    )
    late = post_import(client, notes_csv(("E-001", "2026-11-12 20:00", "Afterwards")), "notes")
    assert late.json()["notes_attached"] == {}  # a resolved exception's evidence is frozen
    assert sql(dsn, "SELECT count(*) FROM exception_notes") == [(0,)]


def test_detection_details_are_stored_with_the_exception(flow):
    client, _, dsn = flow
    thursday_exception(client)
    details = sql(dsn, "SELECT detection_details FROM exceptions")[0][0]
    assert details["missing_type"] == "out" and details["unmatched_punch_id"].startswith("PI-")
    assert details["reason"]  # the human-readable sentence is kept alongside the facts
    case = client.get("/exceptions/EX-E-001-2026-11-12-MISSING_PUNCH", headers=AUTH).json()
    assert case["detection_details"]["missing_type"] == "out"


@pytest.mark.parametrize(
    "content,fmt",
    [
        ("a,b\n1\x00,2\n", "csv"),
        ("[" * 50_000 + "]" * 50_000, "json"),
        ("employee_id\n" + "x" * 200_000 + "\n", "csv"),
    ],
)
def test_hostile_import_bodies_are_422_not_500(flow, content, fmt):
    client, _, dsn = flow
    for path in ("/imports/preview", "/imports"):
        response = client.post(path, json={"format": fmt, "content": content}, headers=AUTH)
        assert response.status_code == 422, (path, response.status_code)
        assert response.headers["content-type"].startswith("application/problem+json")
    assert sql(dsn, "SELECT count(*) FROM punches") == [(0,)]


def test_oversized_request_is_refused_before_parsing(flow):
    client, *_ = flow
    huge = "employee_id\n" + ("x" * 100 + "\n") * 25_000  # about 2.5 MB
    response = client.post(
        "/imports/preview", json={"format": "csv", "content": huge}, headers=AUTH
    )
    assert response.status_code == 422


# ---- audit: lifecycle of detection


def test_a_retry_after_a_failed_detection_still_detects(flow, monkeypatch):
    """The import commits before detection runs. If detection then fails, a retry sees every punch
    as already imported, and must still re-run detection for those dates."""
    client, _, _ = flow
    assert post_import(client, shifts_csv(), "shifts").status_code == 200
    import app.attendance.imports_router as router_module
    import app.attendance.ingest as ingest_module

    def boom(*args, **kwargs):
        raise RuntimeError("detection crashed")

    monkeypatch.setattr(ingest_module, "run_detection", boom)
    with pytest.raises(RuntimeError):
        post_import(client, punches_csv())
    monkeypatch.undo()
    assert router_module and client.get("/exceptions", headers=AUTH).json()["total"] == 0
    retry = post_import(client, punches_csv()).json()
    assert retry["inserted"] == 0 and retry["duplicates"] == 15
    assert retry["detected_exception_ids"] == ["EX-E-001-2026-11-12-MISSING_PUNCH"]


def test_an_exception_is_cleared_when_later_data_fixes_it(flow):
    client, _, dsn = flow
    exception = thursday_exception(client)
    assert client.get("/exceptions", headers=AUTH).json()["total"] == 1
    fixed = "employee_id,timestamp,type,source_event_id\nE-001,2026-11-12 18:00,out,k-12-4\n"
    again = post_import(client, fixed).json()
    assert again["inserted"] == 1
    listing = client.get("/exceptions", headers=AUTH).json()
    assert listing["total"] == 0, "the punch-out arrived, so there is nothing left to resolve"
    events = client.get(f"/exceptions/{exception}/audit", headers=AUTH).json()
    assert [e["event_type"] for e in events][-1] == "EXCEPTION_CLEARED"
    assert sql(dsn, "SELECT status FROM exceptions") == [("dismissed",)]
    # The integrity check agrees that "dismissed" is a legitimate, consistent status.
    from app.attendance.maintenance import verify
    from app.attendance.postgres import PostgresBackend

    with PostgresBackend(dsn).transaction(immediate=False) as connection:
        assert [f for f in verify(connection) if f.level == "problem"] == []
    # It can be asked for by status, for anyone auditing what cleared itself.
    dismissed = client.get("/exceptions?status=dismissed", headers=AUTH).json()
    assert [i["exception_id"] for i in dismissed["items"]] == [exception]


def test_a_cleared_exception_comes_back_if_the_problem_returns(flow):
    client, _, dsn = flow
    exception = thursday_exception(client)
    fixed = "employee_id,timestamp,type,source_event_id\nE-001,2026-11-12 18:00,out,k-12-4\n"
    post_import(client, fixed)
    assert client.get("/exceptions", headers=AUTH).json()["total"] == 0
    # A second clock-in with no clock-out now exists for that day.
    again = "employee_id,timestamp,type,source_event_id\nE-001,2026-11-12 19:00,in,k-12-5\n"
    result = post_import(client, again).json()
    assert exception in result["detected_exception_ids"]
    assert client.get("/exceptions", headers=AUTH).json()["total"] == 1
    assert sql(dsn, "SELECT status FROM exceptions") == [("open",)]


# ---- audit: detection must not hold the global write lock for a whole import


def _two_employee_import(dsn):
    from app.attendance.importer import local_dates, preview_punches, preview_shifts, read_rows
    from app.attendance.ingest import commit_import
    from app.attendance.postgres import PostgresBackend

    zones = {"E-001": "Asia/Kolkata", "E-002": "Asia/Kolkata"}
    shifts, punches = (
        ["employee_id,shift_id,start,end,planned_break_min"],
        ["employee_id,timestamp,type,source_event_id"],
    )
    for employee in zones:
        shifts.append(f"{employee},S-{employee},2026-11-12 09:00,2026-11-12 18:00,60")
        punches.append(
            f"{employee},2026-11-12 09:00,in,{employee}-in"
        )  # no clock-out: an exception
    backend = PostgresBackend(dsn)
    for kind, lines, build in (("s", shifts, preview_shifts), ("p", punches, preview_punches)):
        preview = build(read_rows("\n".join(lines) + "\n", "csv"), employee_timezones=zones)
        commit_import(backend, preview, batch_id=f"B-{kind}")
    return backend, local_dates(preview, zones)


def test_detection_releases_the_write_lock_between_employees(flow, monkeypatch):
    from contextlib import contextmanager

    import psycopg

    import app.attendance.ingest as ingest_module
    from app.attendance.postgres import _WRITE_LOCK, PostgresBackend

    _, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)
    registry = app_.state.resolution_store.registry
    real, lock_was_free = PostgresBackend.transaction, []

    @contextmanager
    def watched(self, *, immediate=True):
        with real(self, immediate=immediate) as connection:
            yield connection
        # The transaction has committed. Could another writer take the lock right now?
        with psycopg.connect(dsn) as other:
            lock_was_free.append(
                other.execute("SELECT pg_try_advisory_xact_lock(%s)", (_WRITE_LOCK,)).fetchone()[0]
            )

    monkeypatch.setattr(PostgresBackend, "transaction", watched)
    created = ingest_module.run_detection(backend, registry, touched, as_of=NOW)
    assert len(created) == 2
    # One committed transaction per employee, and the lock was free after each of them. One long
    # transaction over the whole import would produce a single entry.
    assert lock_was_free == [True, True]


def test_a_failure_part_way_keeps_earlier_employees_and_a_retry_finishes(flow, monkeypatch):
    import app.attendance.ingest as ingest_module

    _, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)
    registry = app_.state.resolution_store.registry
    real = ingest_module._detect_employee

    def crash_on_second(c, registry, employee_id, dates, as_of):
        if employee_id == "E-002":
            raise RuntimeError("detection crashed on the second employee")
        return real(c, registry, employee_id, dates, as_of)

    monkeypatch.setattr(ingest_module, "_detect_employee", crash_on_second)
    with pytest.raises(RuntimeError):
        ingest_module.run_detection(backend, registry, touched, as_of=NOW)
    assert sql(dsn, "SELECT employee_id FROM exceptions") == [("E-001",)]  # first one survived
    monkeypatch.undo()
    created = ingest_module.run_detection(backend, registry, touched, as_of=NOW)
    assert created == ["EX-E-002-2026-11-12-MISSING_PUNCH"]  # only the missing one is new
