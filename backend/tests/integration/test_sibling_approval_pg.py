"""The late-arrival fix on a day whose clock-out was approved first (PostgreSQL).

One employee, one day (Thu 12 Nov, IST, shift 09:00-18:00 with a 60 min break):
- clocked in late at 09:25, no clock-out, and a note saying the true arrival was 09:05.

The system raises a MISSING_PUNCH first. A schedule deviation is only judged on a complete day
(engine.py: complete = no missing punch), so the late-arrival exception appears on the next
detection run, after the clock-out is approved. The test follows that real order: approve the
clock-out, re-run detection, then approve the late-arrival fix against fresh evidence.

The stale-request 409 across same-day exceptions is covered by
test_effective_window_pg.py::test_same_day_correction_updates_other_open_cases.

Skipped unless TEST_DATABASE_URL names a disposable *_test database.
"""

from pathlib import Path

import pytest

from app.attendance.importer import (
    local_dates,
    preview_notes,
    preview_punches,
    preview_shifts,
    read_rows,
)
from app.attendance.ingest import commit_import, import_notes, run_detection
from app.attendance.postgres import PostgresBackend
from app.policies.registry import PolicyRegistry
from tests.integration.test_import_flow_pg import AUTH, flow, sql  # noqa: F401
from tests.integration.test_resolution_api import NOW

ZONES = {"E-001": "Asia/Kolkata"}
SHIFTS = (
    "employee_id,shift_id,start,end,planned_break_min\n"
    "E-001,S-E-001,2026-11-12 09:00,2026-11-12 18:00,60\n"
)
PUNCHES = (
    "employee_id,timestamp,type,source_event_id\n"
    "E-001,2026-11-12 09:25,in,E-001-in-late\n"
    "E-001,2026-11-12 13:00,break_start,E-001-break-start\n"
    "E-001,2026-11-12 14:00,break_end,E-001-break-end\n"
)
NOTES = (
    "employee_id,submitted_at,text\nE-001,2026-11-12 19:00,Kiosk was down and I got in at 9:05.\n"
)
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _version(client, exception_id):
    return client.get(f"/exceptions/{exception_id}", headers=AUTH).json()["evidence_version"]


def _decide(client, exception_id, *, actions, evidence_version, key):
    return client.post(
        f"/exceptions/{exception_id}/decisions",
        json={
            "decision": "approve",
            "source": "manager_edit",
            "reason": "Reviewed against the schedule and the employee's note.",
            "actions": actions,
            "evidence_version": evidence_version,
            "idempotency_key": key,
        },
        headers=AUTH,
    )


@pytest.fixture
def day(flow):  # noqa: F811
    client, app_, dsn = flow
    backend = PostgresBackend(dsn)
    registry = PolicyRegistry.from_directory(BACKEND_DIR / "policies")
    commit_import(
        backend,
        preview_shifts(read_rows(SHIFTS, "csv"), employee_timezones=ZONES),
        batch_id="B-shift",
        manager_id="M-1",
    )
    punches = preview_punches(read_rows(PUNCHES, "csv"), employee_timezones=ZONES)
    commit_import(backend, punches, batch_id="B-punch", manager_id="M-1")
    run_detection(backend, registry, local_dates(punches, ZONES), as_of=NOW)
    notes = preview_notes(read_rows(NOTES, "csv"), employee_timezones=ZONES)
    import_notes(backend, notes, as_of=NOW, manager_id="M-1")
    return client, dsn, backend, registry, punches


def _codes(dsn):
    return dict(
        sql(
            dsn,
            "SELECT code, exception_id FROM exceptions WHERE employee_id = 'E-001' "
            "AND work_date = '2026-11-12'",
        )
    )


def test_late_arrival_fix_completes_once_the_clock_out_is_approved(day):
    client, dsn, backend, registry, punches = day

    # While the clock-out is missing, only the missing punch is raised.
    assert set(_codes(dsn)) == {"MISSING_PUNCH"}
    missing = _codes(dsn)["MISSING_PUNCH"]
    first = _decide(
        client,
        missing,
        actions=[{"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}],
        evidence_version=_version(client, missing),
        key="late-missing-out",
    )
    assert first.status_code == 200, first.text

    # The next import touching the day re-runs detection on the now-complete day.
    run_detection(backend, registry, local_dates(punches, ZONES), as_of=NOW)
    late = _codes(dsn)["SCHEDULE_DEVIATION"]

    late_in = sql(dsn, "SELECT punch_id FROM punches WHERE source_event_id = 'E-001-in-late'")[0][0]
    note = sql(dsn, "SELECT note_id FROM employee_notes WHERE employee_id = 'E-001'")[0][0]
    fix = [
        {
            "type": "adjust_punch",
            "punch_id": late_in,
            "new_ts": "2026-11-12T09:05:00+05:30",
            "evidence_ref": {"kind": "note", "id": note},
        }
    ]
    refreshed = _decide(
        client, late, actions=fix, evidence_version=_version(client, late), key="late-fix"
    )
    assert refreshed.status_code == 200, refreshed.text

    corrections = sql(dsn, "SELECT count(*) FROM corrections WHERE exception_id = %s", (late,))
    assert corrections[0][0] == 1
    approvals = sql(
        dsn,
        "SELECT count(*) FROM audit_events WHERE exception_id = %s AND event_type = 'DECISION_APPROVED'",
        (late,),
    )
    assert approvals[0][0] == 1
    worked = sql(
        dsn,
        "SELECT worked_hours FROM day_totals WHERE employee_id = 'E-001' AND work_date = '2026-11-12'",
    )[0][0]
    # 09:05 to 18:00 less the 60 min break: 7 h 55 min.
    assert abs(float(worked) - (7 + 55 / 60)) < 1e-6
