"""PostgreSQL schema, migrations and concurrency. Skipped unless TEST_DATABASE_URL is set."""

import threading
from datetime import UTC, datetime

import pytest

from app.resolution.store import DecisionConflict, DecisionRequest, ResolutionStore
from tests.integration.test_resolution_api import NOW, _postgres_dsn, evidenced, seed_totals

psycopg = pytest.importorskip("psycopg")


@pytest.fixture
def dsn():
    return _postgres_dsn()


@pytest.fixture
def seeded(dsn, registry):
    from app.attendance.postgres import PostgresBackend, PostgresCaseRepository

    repo = PostgresCaseRepository(dsn)
    repo.seed_case(evidenced(), manager_id="M-1")
    store = ResolutionStore(PostgresBackend(dsn), registry, clock=lambda: NOW)
    seed_totals(store)
    return repo, store


def run(dsn, sql, params=()):
    with psycopg.connect(dsn, autocommit=True) as connection:
        cursor = connection.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


def test_migrations_are_recorded_and_idempotent(dsn, tmp_path):
    from app.attendance.postgres import MIGRATIONS_DIR, apply_migrations

    assert apply_migrations(dsn) == []
    assert run(dsn, "SELECT version FROM schema_migrations") == [("0001_initial",)]
    edited = tmp_path / "migrations"
    edited.mkdir()
    original = (MIGRATIONS_DIR / "0001_initial.sql").read_text()
    (edited / "0001_initial.sql").write_text(original + "\n-- edited after release\n")
    with pytest.raises(RuntimeError, match="was edited"):
        apply_migrations(dsn, edited)


def test_seed_is_idempotent_and_refuses_conflicts(dsn, seeded):
    repo, _ = seeded
    repo.seed_case(evidenced(), manager_id="M-1")  # same evidence: no-op
    with pytest.raises(ValueError, match="reassign"):
        repo.seed_case(evidenced(), manager_id="M-2")
    clash = evidenced("X-7", "E-007").model_dump()
    clash["punches"][0]["punch_id"] = "X-1-P0"  # already E-001's punch
    with pytest.raises(ValueError, match="punch X-1-P0"):
        repo.seed_case(type(evidenced()).model_validate(clash), manager_id="M-1")


@pytest.mark.parametrize(
    "sql,error",
    [
        (
            "INSERT INTO punches (punch_id, employee_id, ts, type, source, source_event_id) "
            "VALUES ('dup', 'E-001', now(), 'in', 'kiosk', 'X-1-P0')",
            "punches_source_source_event_id_key",
        ),
        (
            "INSERT INTO exceptions (exception_id, employee_id, code, severity, work_date, "
            "rule_version) VALUES ('X-dup', 'E-001', 'MISSING_PUNCH', 'problem', '2026-11-12', 'r')",
            "exceptions_one_live",
        ),
        (
            "INSERT INTO punches (punch_id, employee_id, ts, type, source, source_event_id) "
            "VALUES ('bad', 'E-001', now(), 'lunch', 'kiosk', 'bad')",
            "punches_type_check",
        ),
        (
            "INSERT INTO punches (punch_id, employee_id, ts, type, source, source_event_id) "
            "VALUES ('ghost', 'E-404', now(), 'in', 'kiosk', 'ghost')",
            "punches_employee_id_fkey",
        ),
        (
            "INSERT INTO scheduled_shifts VALUES ('S-bad', 'E-001', now(), now(), 0)",
            "scheduled_shifts_check",
        ),
        ("DELETE FROM employees WHERE employee_id = 'E-001'", "fkey"),
    ],
)
def test_database_constraints(dsn, seeded, sql, error):
    with pytest.raises(psycopg.errors.IntegrityError, match=error):
        run(dsn, sql)


def test_naive_timestamps_are_not_silently_accepted_by_contracts(dsn, seeded):
    # timestamptz columns return aware datetimes; the loaded case is all-aware.
    repo, _ = seeded
    case, _ = repo.load_for_manager("X-1", "M-1")
    assert all(p.ts.tzinfo is not None for p in case.punches)
    assert case.schedule.start.utcoffset() is not None


def test_ended_assignment_removes_access(dsn, seeded):
    repo, _ = seeded
    assert repo.list_for_manager("M-1")
    run(dsn, "UPDATE manager_assignments SET valid_to = now() WHERE manager_id = 'M-1'")
    assert repo.list_for_manager("M-1") == []


def test_concurrent_approvals_only_one_wins(dsn, seeded):
    repo, store = seeded
    case, _ = repo.load_for_manager("X-1", "M-1")
    from app.attendance.context import build_verified_case

    version = build_verified_case(case, correction_revision=0).evidence_version
    outcomes, barrier = [], threading.Barrier(4)

    def approve(index):
        body = DecisionRequest(
            decision="approve",
            actions=[
                {
                    "type": "add_punch",
                    "punch_type": "out",
                    "new_ts": datetime(2026, 11, 12, 12, 30, tzinfo=UTC),
                }
            ],
            evidence_version=version,
            idempotency_key=f"race-key-{index}",
        )
        barrier.wait()
        try:
            outcomes.append(store.decide("X-1", "M-1", body).status)
        except Exception as exc:  # stale or conflict
            outcomes.append(type(exc).__name__)

    threads = [threading.Thread(target=approve, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("resolved") == 1, outcomes
    assert all(o in ("resolved", "StaleEvidence", DecisionConflict.__name__) for o in outcomes)
    assert run(dsn, "SELECT count(*) FROM decisions") == [(1,)]
    assert run(
        dsn, "SELECT status, correction_revision FROM exceptions WHERE exception_id='X-1'"
    ) == [("resolved", 1)]
    with psycopg.connect(dsn) as connection:
        from app.attendance.postgres import PgConnection
        from app.audit.events import verify_chain

        assert verify_chain(PgConnection(connection))
