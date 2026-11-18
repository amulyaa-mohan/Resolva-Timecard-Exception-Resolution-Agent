"""Disposable SQLite evidence store for integration tests, not production migrations.

Use a dedicated demo/test path. The database team owns the final relational schema.
Read-only demo HTTP routes expose authorized snapshots; provisioning requires trusted server code.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.attendance.context import build_verified_case
from app.attendance.queries import ExceptionFilter, sort_key, status_expression
from app.core.contracts import CaseContext


class CaseAccessDenied(PermissionError):
    """Same result for unknown and unauthorized cases to prevent enumeration."""


class DemoCaseRepository:
    def __init__(self, path: Path):
        self.path = path
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS demo_employee_managers (
                    employee_id TEXT PRIMARY KEY, manager_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS demo_case_snapshots (
                    exception_id TEXT PRIMARY KEY,
                    employee_id TEXT NOT NULL REFERENCES demo_employee_managers(employee_id),
                    evidence_json TEXT NOT NULL, correction_revision INTEGER NOT NULL CHECK(correction_revision >= 0)
                );
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def seed_case(self, case: CaseContext, *, manager_id: str, correction_revision: int = 0):
        """Idempotent fixture provisioning; refuses to overwrite evidence or ownership."""
        if not manager_id.strip():
            raise ValueError("manager identity required")
        case = build_verified_case(case, correction_revision=correction_revision)
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO demo_employee_managers VALUES (?, ?)",
                (case.employee.employee_id, manager_id),
            )
            assigned = connection.execute(
                "SELECT manager_id FROM demo_employee_managers WHERE employee_id=?",
                (case.employee.employee_id,),
            ).fetchone()[0]
            if assigned != manager_id:
                raise ValueError("seed cannot reassign employee")
            previous = connection.execute(
                "SELECT evidence_json, correction_revision FROM demo_case_snapshots WHERE exception_id=?",
                (case.exception_id,),
            ).fetchone()
            if previous:
                old = build_verified_case(
                    CaseContext.model_validate_json(previous[0]), correction_revision=previous[1]
                )
                if old.evidence_version != case.evidence_version:
                    raise ValueError("seed cannot overwrite evidence")
                return
            connection.execute(
                "INSERT INTO demo_case_snapshots VALUES (?, ?, ?, ?)",
                (
                    case.exception_id,
                    case.employee.employee_id,
                    case.model_dump_json(),
                    correction_revision,
                ),
            )

    def load_for_manager(self, exception_id: str, manager_id: str) -> tuple[CaseContext, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.evidence_json, c.correction_revision FROM demo_case_snapshots c
                JOIN demo_employee_managers m ON m.employee_id=c.employee_id
                WHERE c.exception_id=? AND m.manager_id=?
            """,
                (exception_id, manager_id),
            ).fetchone()
        if row is None:
            raise CaseAccessDenied("case unavailable for this manager")
        return CaseContext.model_validate_json(row[0]), row[1]

    def search_exceptions(
        self, manager_id: str, filters: ExceptionFilter
    ) -> tuple[list[tuple[CaseContext, str]], int]:
        """Demo snapshots are few, so they are filtered in Python after one status query."""
        cases = self.list_for_manager(manager_id)
        status_by_id = {}
        if cases:
            with self._connect() as connection:
                marks = ",".join("?" * len(cases))
                status_by_id = dict(
                    connection.execute(
                        f"SELECT exception_id, {status_expression('e', dismissible=False)} FROM demo_case_snapshots e "
                        f"WHERE exception_id IN ({marks})",
                        [c.exception_id for c in cases],
                    ).fetchall()
                )
        matched = [
            (case, status_by_id.get(case.exception_id, "open"))
            for case in cases
            if filters.matches(
                code=case.code,
                severity=case.severity,
                status=status_by_id.get(case.exception_id, "open"),
                employee_id=case.employee.employee_id,
                exception_id=case.exception_id,
                work_date=case.work_date,
            )
        ]
        matched.sort(
            key=lambda pair: sort_key(pair[0].severity, pair[0].work_date, pair[0].exception_id)
        )
        return matched[filters.offset : filters.offset + filters.limit], len(matched)

    def display_names(self, employee_ids: list[str]) -> dict[str, str]:
        """The demo snapshot store keeps no personal data, so names are never shown."""
        return {}

    def list_for_manager(self, manager_id: str) -> list[CaseContext]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.evidence_json, c.correction_revision FROM demo_case_snapshots c
                   JOIN demo_employee_managers m ON m.employee_id=c.employee_id
                   WHERE m.manager_id=? ORDER BY c.exception_id""",
                (manager_id,),
            ).fetchall()
        return [
            build_verified_case(CaseContext.model_validate_json(row[0]), correction_revision=row[1])
            for row in rows
        ]
