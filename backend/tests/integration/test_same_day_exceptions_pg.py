"""Two exceptions on one workday (PostgreSQL).

Approving one exception adds a punch to the workday. That punch belongs to the first decision,
not to the second exception's evidence, so it must not block the second approval.
Skipped unless TEST_DATABASE_URL names a disposable *_test database.
"""

import json

from tests.integration.test_import_flow_pg import _two_employee_import, flow, sql  # noqa: F401
from tests.integration.test_resolution_api import NOW


def _second_same_day_exception(dsn, first_exception_id):
    """A second open exception for E-001 on the same workday, linked to the same raw punches."""
    shift_id, work_date = sql(
        dsn,
        "SELECT shift_id, work_date FROM exceptions WHERE exception_id = %s",
        (first_exception_id,),
    )[0]
    second = "EX-E-001-SECOND"
    sql(
        dsn,
        "INSERT INTO exceptions (exception_id, employee_id, shift_id, code, severity, work_date, "
        "rule_version, detection_details) VALUES (%s, 'E-001', %s, 'SCHEDULE_DEVIATION', 'warning', "
        "%s, (SELECT rule_version FROM exceptions WHERE exception_id = %s), '{}'::jsonb)",
        (second, shift_id, work_date, first_exception_id),
    )
    sql(
        dsn,
        "INSERT INTO exception_punches (exception_id, punch_id) SELECT %s, punch_id "
        "FROM exception_punches WHERE exception_id = %s",
        (second, first_exception_id),
    )
    return second


def test_second_exception_on_the_day_sees_the_approved_correction_as_workday_punch(flow):  # noqa: F811
    """After A's approval adds a punch, B's loaded evidence is the effective workday, which
    includes that punch. Approval of B compares the workday with that same loaded evidence, so
    the comparison cannot report a mismatch caused by A's correction."""
    from app.attendance.context import CaseService
    from app.attendance.ingest import run_detection
    from app.attendance.postgres import PostgresBackend, PostgresCaseRepository

    _, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)
    run_detection(backend, app_.state.resolution_store.registry, touched, as_of=NOW)
    first = sql(dsn, "SELECT exception_id FROM exceptions WHERE employee_id = 'E-001'")[0][0]
    second = _second_same_day_exception(dsn, first)

    sql(
        dsn,
        "INSERT INTO decisions VALUES ('DEC-A', %s, 'M-1', 'approve', 'manager_edit', 'v', "
        "'IDEM-A', 'h', '{}'::jsonb, now())",
        (first,),
    )
    actions = [{"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}]
    sql(
        dsn,
        "INSERT INTO corrections VALUES ('COR-A', 'DEC-A', %s, 'E-001', %s::jsonb, now())",
        (first, json.dumps(actions)),
    )

    case = CaseService(PostgresCaseRepository(dsn)).build_case_context(second, manager_id="M-1")
    backend = PostgresBackend(dsn)
    with backend.transaction(immediate=False) as connection:
        workday = backend.effective_workday(connection, case)

    assert {p.punch_id for p in case.punches} == {p.punch_id for p in workday}
    assert "correction:COR-A:0" in {p.punch_id for p in case.punches}
