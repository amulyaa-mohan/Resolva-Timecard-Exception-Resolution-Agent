"""PostgreSQL persistence: migrations, authorized case loading, decision backend.

Schema: backend/database/migrations/*.sql, applied in order by apply_migrations and
recorded with checksums in schema_migrations (an edited, already-applied file is refused).
Requires the optional dependency: pip install -e "./backend[postgres]".
"""

import hashlib
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.attendance.context import build_verified_case
from app.attendance.repository import CaseAccessDenied
from app.core.config import BACKEND_DIR
from app.core.contracts import CaseContext

MIGRATIONS_DIR = BACKEND_DIR / "database" / "migrations"
# One advisory lock serializes writing transactions: no double approvals, no forked audit chain.
_WRITE_LOCK = 7_402_113


def _psycopg():
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            'PostgreSQL support needs: pip install -e "./backend[postgres]"'
        ) from exc
    return psycopg


class PgConnection:
    """Accepts the `?` placeholders shared with the SQLite code."""

    def __init__(self, connection):
        self.raw = connection

    def execute(self, sql: str, params=()):
        return self.raw.execute(sql.replace("%", "%%").replace("?", "%s"), tuple(params))


def apply_migrations(dsn: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in one transaction each; return the versions applied."""
    psycopg = _psycopg()
    applied = []
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, "
            "checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        connection.commit()
        done = dict(connection.execute("SELECT version, checksum FROM schema_migrations"))
        for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if path.stem in done:
                if done[path.stem] != checksum:
                    raise RuntimeError(f"applied migration {path.name} was edited; add a new one")
                continue
            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (path.stem, checksum),
                )
            applied.append(path.stem)
    return applied


class PostgresBackend:
    """ResolutionStore backend over the normalized schema."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    @contextmanager
    def transaction(self, *, immediate: bool = True):
        psycopg = _psycopg()
        with psycopg.connect(self.dsn) as raw:  # commits on success, rolls back on error
            if immediate:
                raw.execute("SELECT pg_advisory_xact_lock(%s)", (_WRITE_LOCK,))
            yield PgConnection(raw)

    def load_case(self, connection, exception_id: str, manager_id: str, *, lock: bool):
        row = connection.execute(
            "SELECT e.exception_id, e.code, e.severity, e.work_date, e.rule_version, "
            "e.detection_details, e.correction_revision, e.shift_id, emp.employee_id, "
            "emp.location_id, emp.jurisdiction, emp.timezone, emp.worker_category "
            "FROM exceptions e JOIN employees emp ON emp.employee_id = e.employee_id "
            "WHERE e.exception_id = ? AND EXISTS (SELECT 1 FROM manager_assignments a "
            "WHERE a.employee_id = e.employee_id AND a.manager_id = ? "
            "AND a.valid_from <= now() AND (a.valid_to IS NULL OR a.valid_to > now()))"
            + (" FOR UPDATE OF e" if lock else ""),
            (exception_id, manager_id),
        ).fetchone()
        if row is None:
            raise CaseAccessDenied("case unavailable for this manager")
        (exc_id, code, severity, work_date, rule_version, details, revision, shift_id) = row[:8]
        employee = dict(
            zip(
                ("employee_id", "location_id", "jurisdiction", "timezone", "worker_category"),
                row[8:],
                strict=True,
            )
        )
        punch_cols = "p.punch_id, p.employee_id, p.ts, p.type, p.source, p.device_id"

        def punch(r):
            keys = ("punch_id", "employee_id", "ts", "type", "source", "device_id")
            return dict(zip(keys, r, strict=True))

        punches = [
            punch(r)
            for r in connection.execute(
                f"SELECT {punch_cols} FROM exception_punches ep "
                "JOIN punches p ON p.punch_id = ep.punch_id WHERE ep.exception_id = ? ORDER BY p.ts",
                (exc_id,),
            )
        ]
        zone = ZoneInfo(employee["timezone"])
        day_start = datetime.combine(work_date, time(0), tzinfo=zone)
        history = [
            punch(r)
            for r in connection.execute(
                f"SELECT {punch_cols} FROM punches p WHERE p.employee_id = ? "
                "AND p.ts >= ? AND p.ts < ? AND NOT EXISTS (SELECT 1 FROM exception_punches ep "
                "WHERE ep.exception_id = ? AND ep.punch_id = p.punch_id) ORDER BY p.ts",
                (employee["employee_id"], day_start - timedelta(days=7), day_start, exc_id),
            )
        ]
        notes = [
            dict(zip(("note_id", "text", "submitted_at"), r, strict=True))
            for r in connection.execute(
                "SELECT n.note_id, n.text, n.submitted_at FROM exception_notes en "
                "JOIN employee_notes n ON n.note_id = en.note_id WHERE en.exception_id = ? "
                "ORDER BY n.submitted_at, n.note_id",
                (exc_id,),
            )
        ]
        schedule = None
        if shift_id is not None:
            shift = connection.execute(
                "SELECT shift_id, employee_id, start_at, end_at, planned_break_min "
                "FROM scheduled_shifts WHERE shift_id = ?",
                (shift_id,),
            ).fetchone()
            keys = ("shift_id", "employee_id", "start", "end", "planned_break_min")
            schedule = dict(zip(keys, shift, strict=True))
        case = CaseContext.model_validate(
            {
                "exception_id": exc_id,
                "code": code,
                "severity": severity,
                "employee": employee,
                "work_date": work_date,
                "rule_version": rule_version,
                "punches": punches,
                "punch_history": history,
                "schedule": schedule,
                "notes": notes,
                "detection_details": details or {},
                "evidence_version": "computed-by-build_verified_case",
            }
        )
        return case, revision

    def mark_escalated(self, connection, exception_id: str) -> None:
        connection.execute(
            "UPDATE exceptions SET status = 'escalated' WHERE exception_id = ? AND status = 'open'",
            (exception_id,),
        )

    def mark_resolved(self, connection, exception_id: str, old: int, new: int) -> None:
        updated = connection.execute(
            "UPDATE exceptions SET correction_revision = ?, status = 'resolved' "
            "WHERE exception_id = ? AND correction_revision = ?",
            (new, exception_id, old),
        ).rowcount
        if updated != 1:
            from app.resolution.store import DecisionConflict

            raise DecisionConflict("evidence revision changed during the decision")


class PostgresCaseRepository:
    """CaseRepository (load_for_manager / list_for_manager) plus trusted provisioning."""

    def __init__(self, dsn: str):
        self.backend = PostgresBackend(dsn)

    def load_for_manager(self, exception_id: str, manager_id: str) -> tuple[CaseContext, int]:
        with self.backend.transaction(immediate=False) as connection:
            return self.backend.load_case(connection, exception_id, manager_id, lock=False)

    def list_for_manager(self, manager_id: str) -> list[CaseContext]:
        with self.backend.transaction(immediate=False) as connection:
            ids = [
                r[0]
                for r in connection.execute(
                    "SELECT e.exception_id FROM exceptions e WHERE EXISTS (SELECT 1 FROM "
                    "manager_assignments a WHERE a.employee_id = e.employee_id "
                    "AND a.manager_id = ? AND a.valid_from <= now() "
                    "AND (a.valid_to IS NULL OR a.valid_to > now())) ORDER BY e.exception_id",
                    (manager_id,),
                )
            ]
            cases = []
            for exception_id in ids:
                case, revision = self.backend.load_case(
                    connection, exception_id, manager_id, lock=False
                )
                cases.append(build_verified_case(case, correction_revision=revision))
            return cases

    def display_names(self, employee_ids: list[str]) -> dict[str, str]:
        """Employee id -> full name, for display only. Missing names are simply absent."""
        if not employee_ids:
            return {}
        with self.backend.transaction(immediate=False) as c:
            marks = ",".join("?" * len(employee_ids))
            return {
                row[0]: row[1]
                for row in c.execute(
                    f"SELECT employee_id, full_name FROM employees "
                    f"WHERE employee_id IN ({marks}) AND full_name IS NOT NULL",
                    employee_ids,
                )
            }

    def seed_case(self, case: CaseContext, *, manager_id: str, manager_timezone: str = "UTC"):
        """Trusted provisioning of synthetic data. Idempotent; refuses to change evidence."""
        if not manager_id.strip():
            raise ValueError("manager identity required")
        case = build_verified_case(case, correction_revision=0)
        e = case.employee
        with self.backend.transaction() as c:
            c.execute(
                "INSERT INTO managers VALUES (?, ?) ON CONFLICT DO NOTHING",
                (manager_id, manager_timezone),
            )
            c.execute(
                "INSERT INTO employees (employee_id, location_id, jurisdiction, timezone, "
                "worker_category) VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (e.employee_id, e.location_id, e.jurisdiction, e.timezone, e.worker_category),
            )
            owner = c.execute(
                "SELECT manager_id FROM manager_assignments WHERE employee_id = ? "
                "AND valid_to IS NULL",
                (e.employee_id,),
            ).fetchall()
            if not owner:
                c.execute(
                    "INSERT INTO manager_assignments (manager_id, employee_id, valid_from) "
                    "VALUES (?, ?, now() - interval '1 second')",
                    (manager_id, e.employee_id),
                )
            elif {r[0] for r in owner} != {manager_id}:
                raise ValueError("seed cannot reassign employee")
            if c.execute(
                "SELECT 1 FROM exceptions WHERE exception_id = ?", (case.exception_id,)
            ).fetchone():
                existing, revision = self.backend.load_case(
                    c, case.exception_id, manager_id, lock=False
                )
                current = build_verified_case(existing, correction_revision=0)
                if revision != 0 or current.evidence_version != case.evidence_version:
                    raise ValueError("seed cannot overwrite evidence")
                return
            # Ids are global: an existing row with the same id must be the same record.
            if case.schedule is not None:
                s = case.schedule
                c.execute(
                    "INSERT INTO scheduled_shifts VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (s.shift_id, s.employee_id, s.start, s.end, s.planned_break_min),
                )
                stored = c.execute(
                    "SELECT employee_id, start_at, end_at FROM scheduled_shifts WHERE shift_id = ?",
                    (s.shift_id,),
                ).fetchone()
                if stored != (s.employee_id, s.start, s.end):
                    raise ValueError(f"shift {s.shift_id} already exists with other data")
            for p in [*case.punches, *case.punch_history]:
                c.execute(
                    "INSERT INTO punches (punch_id, employee_id, ts, type, source, device_id, "
                    "source_event_id) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (
                        p.punch_id,
                        p.employee_id,
                        p.ts,
                        p.type.value,
                        p.source.value,
                        p.device_id,
                        p.punch_id,
                    ),
                )
                stored = c.execute(
                    "SELECT employee_id, ts, type FROM punches WHERE punch_id = ?", (p.punch_id,)
                ).fetchone()
                if stored != (p.employee_id, p.ts, p.type.value):
                    raise ValueError(f"punch {p.punch_id} already exists with other data")
            for n in case.notes:
                c.execute(
                    "INSERT INTO employee_notes VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                    (n.note_id, e.employee_id, n.text, n.submitted_at),
                )
            from psycopg.types.json import Jsonb

            c.execute(
                "INSERT INTO exceptions (exception_id, employee_id, shift_id, code, severity, "
                "work_date, rule_version, detection_details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    case.exception_id,
                    e.employee_id,
                    case.schedule.shift_id if case.schedule else None,
                    case.code.value,
                    case.severity.value,
                    case.work_date,
                    case.rule_version,
                    Jsonb(case.detection_details),
                ),
            )
            for p in case.punches:
                c.execute(
                    "INSERT INTO exception_punches VALUES (?, ?)", (case.exception_id, p.punch_id)
                )
            for n in case.notes:
                c.execute(
                    "INSERT INTO exception_notes VALUES (?, ?)", (case.exception_id, n.note_id)
                )
