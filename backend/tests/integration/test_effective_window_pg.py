"""Codex finding 3 (PostgreSQL): the timecard window applies to effective punch times.

An approved adjust_punch can move a punch recorded outside a work day into it, or a punch
recorded inside it out of it. Skipped unless TEST_DATABASE_URL names a *_test database.
"""

import json
from datetime import datetime, timedelta

import pytest

from tests.factories import IST
from tests.integration.test_import_flow_pg import _two_employee_import, flow, sql  # noqa: F401
from tests.integration.test_resolution_api import NOW

ZONES = {"E-001": "Asia/Kolkata"}
PUNCHES = (
    "employee_id,timestamp,type,source_event_id\n"
    "E-001,2026-11-11 23:50,out,E-001-before-midnight\n"
    "E-001,2026-11-12 09:30,out,E-001-mid-morning\n"
)
DAY_LO = datetime(2026, 11, 12, 0, 0, tzinfo=IST)
DAY_HI = DAY_LO + timedelta(days=1)


def _punch_id(dsn, source_event_id):
    return sql(dsn, "SELECT punch_id FROM punches WHERE source_event_id = %s", (source_event_id,))[
        0
    ][0]


@pytest.fixture
def corrected(flow):  # noqa: F811
    from app.attendance.importer import preview_punches, read_rows
    from app.attendance.ingest import commit_import, run_detection

    _, app_, dsn = flow
    backend, touched = _two_employee_import(dsn)
    run_detection(backend, app_.state.resolution_store.registry, touched, as_of=NOW)
    preview = preview_punches(read_rows(PUNCHES, "csv"), employee_timezones=ZONES)
    commit_import(backend, preview, batch_id="B-window", manager_id="M-1")
    exc_id = sql(
        dsn,
        "SELECT exception_id FROM exceptions WHERE employee_id = %s",
        ("E-001",),
    )[0][0]
    return backend, dsn, exc_id


def _approve_with(dsn, exc_id, actions):
    sql(
        dsn,
        "INSERT INTO decisions VALUES (%s, %s, 'M-1', 'approve', 'manager_edit', 'v', %s, "
        "'h', '{}'::jsonb, now())",
        ("DEC-window", exc_id, "IDEM-window"),
    )
    sql(
        dsn,
        "INSERT INTO corrections VALUES ('COR-window', 'DEC-window', %s, 'E-001', "
        "%s::jsonb, now())",
        (exc_id, json.dumps(actions)),
    )


def _effective_ids(backend):
    from app.attendance.ingest import _effective_punches

    with backend.transaction(immediate=False) as c:
        return {p.punch_id for p in _effective_punches(c, "E-001", DAY_LO, DAY_HI)}


def test_punch_recorded_before_the_day_but_adjusted_into_it_is_loaded(corrected):
    backend, dsn, exc_id = corrected
    moved = _punch_id(dsn, "E-001-before-midnight")
    _approve_with(
        dsn,
        exc_id,
        [{"type": "adjust_punch", "punch_id": moved, "new_ts": "2026-11-12T00:10:00+05:30"}],
    )
    assert moved in _effective_ids(backend)


def test_punch_recorded_inside_the_day_but_adjusted_out_of_it_is_excluded(corrected):
    backend, dsn, exc_id = corrected
    moved = _punch_id(dsn, "E-001-mid-morning")
    _approve_with(
        dsn,
        exc_id,
        [{"type": "adjust_punch", "punch_id": moved, "new_ts": "2026-11-13T00:30:00+05:30"}],
    )
    assert moved not in _effective_ids(backend)


def test_timecard_includes_adjusted_punch_outside_exception_links(corrected):
    from app.core.config import BACKEND_DIR
    from app.policies.registry import PolicyRegistry
    from app.resolution.store import ResolutionStore

    backend, dsn, exc_id = corrected
    moved = _punch_id(dsn, "E-001-before-midnight")
    _approve_with(
        dsn,
        exc_id,
        [{"type": "adjust_punch", "punch_id": moved, "new_ts": "2026-11-12T00:10:00+05:30"}],
    )
    store = ResolutionStore(backend, PolicyRegistry.from_directory(BACKEND_DIR / "policies"))
    card = store.effective_timecard(exc_id, "M-1")
    assert moved not in {p.punch_id for p in card["raw_punches"]}
    assert moved in {p.punch_id for p in card["effective_punches"]}


def test_same_day_correction_updates_other_open_cases(corrected, flow):  # noqa: F811
    from app.attendance.context import build_verified_case

    backend, dsn, exc_id = corrected
    sql(
        dsn,
        "INSERT INTO exceptions (exception_id, employee_id, shift_id, code, severity, "
        "work_date, rule_version, detection_details) "
        "SELECT 'X-other', employee_id, shift_id, 'SCHEDULE_DEVIATION', 'warning', "
        "work_date, rule_version, detection_details FROM exceptions WHERE exception_id = %s",
        (exc_id,),
    )
    with backend.transaction(immediate=False) as c:
        before, revision = backend.load_case(c, "X-other", "M-1", lock=False)
    _approve_with(
        dsn,
        exc_id,
        [{"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}],
    )
    with backend.transaction(immediate=False) as c:
        after, same_revision = backend.load_case(c, "X-other", "M-1", lock=False)
    assert same_revision == revision
    assert any(p.punch_id == "correction:COR-window:0" for p in after.punches)
    old_version = build_verified_case(before, correction_revision=revision).evidence_version
    fresh_version = build_verified_case(after, correction_revision=revision).evidence_version
    assert old_version != fresh_version

    client, _, _ = flow
    from tests.integration.test_import_flow_pg import AUTH

    body = {
        "decision": "approve",
        "source": "manager_edit",
        "reason": "Review the updated workday",
        "actions": [
            {"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}
        ],
        "evidence_version": old_version,
        "idempotency_key": "same-day-recheck",
    }
    route = "/exceptions/X-other/decisions"
    assert client.post(route, json=body, headers=AUTH).status_code == 409
    body["evidence_version"] = fresh_version
    # The rule validator rejects an inappropriate action. The evidence guard no longer
    # permanently conflicts after the manager reloads the case.
    assert client.post(route, json=body, headers=AUTH).status_code == 422
