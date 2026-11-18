"""Codex review of 15688ba, findings 1 and 4 (PostgreSQL).

Finding 1: a missing clock-out that arrives after a draft proposal was made dismisses the
exception. The draft's evidence must become stale, so it cannot be approved.

Finding 4: an employee revoked between the preview and the commit must not be imported.

Skipped unless TEST_DATABASE_URL names a disposable *_test database.
"""

import pytest

from app.attendance.importer import local_dates
from app.attendance.ingest import commit_import, run_detection
from tests.integration.test_import_flow_pg import _two_employee_import, flow, sql  # noqa: F401
from tests.integration.test_resolution_api import NOW

ZONES = {"E-001": "Asia/Kolkata"}
LATE_OUT = "employee_id,timestamp,type,source_event_id\nE-001,2026-11-12 18:00,out,E-001-late-out\n"


def _late_out_preview():
    from app.attendance.importer import preview_punches, read_rows

    return preview_punches(read_rows(LATE_OUT, "csv"), employee_timezones=ZONES)


def test_commit_refuses_an_assignment_revoked_after_preview(flow):  # noqa: F811
    from app.attendance.ingest import ImportNotAuthorized, commit_import
    from app.attendance.postgres import PostgresBackend

    _, _, dsn = flow
    preview = _late_out_preview()  # the preview-time check passed
    sql(
        dsn,
        "UPDATE manager_assignments SET valid_to = now() "
        "WHERE manager_id = 'M-1' AND employee_id = 'E-001'",
    )
    with pytest.raises(ImportNotAuthorized):
        commit_import(PostgresBackend(dsn), preview, batch_id="B-revoked", manager_id="M-1")
    stored = sql(dsn, "SELECT count(*) FROM punches WHERE source_event_id = 'E-001-late-out'")
    assert stored[0][0] == 0


def test_commit_still_imports_while_the_assignment_holds(flow):  # noqa: F811
    from app.attendance.ingest import commit_import
    from app.attendance.postgres import PostgresBackend

    _, _, dsn = flow
    added = commit_import(
        PostgresBackend(dsn), _late_out_preview(), batch_id="B-ok", manager_id="M-1"
    )
    assert added == 1


def test_dismissal_makes_a_drafted_proposal_stale(flow):  # noqa: F811
    from app.attendance.context import CaseService
    from app.attendance.importer import local_dates
    from app.attendance.ingest import commit_import, run_detection
    from app.attendance.postgres import PostgresCaseRepository

    _, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)  # both employees have a missing clock-out
    run_detection(backend, app_.state.resolution_store.registry, touched, as_of=NOW)
    exc_id = sql(
        dsn,
        "SELECT exception_id FROM exceptions WHERE employee_id = %s AND status = 'open'",
        ("E-001",),
    )[0][0]
    service = CaseService(PostgresCaseRepository(dsn))
    drafted_against = service.build_case_context(exc_id, manager_id="M-1").evidence_version

    # The clock-out arrives while the draft is being written.
    preview = _late_out_preview()
    commit_import(backend, preview, batch_id="B-late", manager_id="M-1")
    run_detection(
        backend,
        app_.state.resolution_store.registry,
        local_dates(preview, ZONES),
        as_of=NOW,
    )

    status = sql(dsn, "SELECT status FROM exceptions WHERE exception_id = %s", (exc_id,))
    assert status[0][0] == "dismissed"
    current = service.build_case_context(exc_id, manager_id="M-1").evidence_version
    assert current != drafted_against, "dismissal must change evidence so the draft is stale"


NOTE_CSV = "employee_id,submitted_at,text\nE-001,2026-11-12 19:00,Kiosk was down, got in at 9:05.\n"


def test_note_import_after_revocation_is_403_and_writes_nothing(flow, monkeypatch):  # noqa: F811
    """The race: the preview saw E-001 assigned, the manager is revoked, then the commit runs.

    The preview's view is frozen to the pre-revocation state, so only the commit-time recheck
    can refuse the import.
    """
    from app.attendance import ingest as ingest_module
    from app.attendance.postgres import PostgresBackend
    from tests.integration.test_import_flow_pg import AUTH

    client, app_, dsn = flow
    stale_view = ingest_module.assigned_employees(PostgresBackend(dsn), "M-1")
    assert "E-001" in stale_view
    monkeypatch.setattr(ingest_module, "assigned_employees", lambda backend, manager_id: stale_view)
    sql(
        dsn,
        "UPDATE manager_assignments SET valid_to = now() "
        "WHERE manager_id = 'M-1' AND employee_id = 'E-001'",
    )
    body = {"kind": "notes", "format": "csv", "content": NOTE_CSV, "mapping": {}}
    response = client.post("/imports", json=body, headers=AUTH)
    assert response.status_code == 403, response.text
    assert sql(dsn, "SELECT count(*) FROM employee_notes WHERE employee_id = 'E-001'")[0][0] == 0
    assert sql(dsn, "SELECT count(*) FROM exception_notes")[0][0] == 0


def test_dismissed_exception_takes_no_proposal_and_no_approval(flow):  # noqa: F811
    from tests.integration.test_import_flow_pg import AUTH

    client, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)
    run_detection(backend, app_.state.resolution_store.registry, touched, as_of=NOW)
    exc_id = sql(dsn, "SELECT exception_id FROM exceptions WHERE employee_id = 'E-001'")[0][0]
    # The clock-out arrives and the rule now passes: the exception is dismissed.
    preview = _late_out_preview()
    commit_import(backend, preview, batch_id="B-dismiss", manager_id="M-1")
    run_detection(
        backend, app_.state.resolution_store.registry, local_dates(preview, ZONES), as_of=NOW
    )
    assert (
        sql(dsn, "SELECT status FROM exceptions WHERE exception_id = %s", (exc_id,))[0][0]
        == "dismissed"
    )

    proposal = client.post(f"/exceptions/{exc_id}/proposal", headers=AUTH)
    assert proposal.status_code == 409, proposal.text
    assert sql(dsn, "SELECT count(*) FROM proposals WHERE exception_id = %s", (exc_id,))[0][0] == 0

    version = client.get(f"/exceptions/{exc_id}", headers=AUTH).json()["evidence_version"]
    body = {
        "decision": "approve",
        "actions": [
            {"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}
        ],
        "evidence_version": version,
        "idempotency_key": "dismissed-approve",
    }
    approval = client.post(f"/exceptions/{exc_id}/decisions", json=body, headers=AUTH)
    assert approval.status_code == 409, approval.text
    assert (
        sql(dsn, "SELECT count(*) FROM corrections WHERE exception_id = %s", (exc_id,))[0][0] == 0
    )
