"""Codex review of 15688ba, findings 1 and 4 (PostgreSQL).

Finding 1: a missing clock-out that arrives after a draft proposal was made dismisses the
exception. The draft's evidence must become stale, so it cannot be approved.

Finding 4: an employee revoked between the preview and the commit must not be imported.

Skipped unless TEST_DATABASE_URL names a disposable *_test database.
"""

import pytest

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
