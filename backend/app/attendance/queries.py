"""Shared exception-list query shapes, so every store answers the same question.

An exception's status is derived, never stored twice: an approval outranks an escalation,
and anything else is open. `exceptions.status` in PostgreSQL mirrors this for operators
reading the database by hand; the integrity script checks the two agree.
"""

from dataclasses import dataclass
from datetime import date

from app.core.contracts import ExceptionCode, Severity

MAX_PAGE = 100


def status_expression(table: str = "e") -> str:
    """SQL giving resolved / escalated / open for one exception row."""
    return (
        "CASE WHEN EXISTS (SELECT 1 FROM decisions d "
        f"WHERE d.exception_id = {table}.exception_id AND d.decision = 'approve') THEN 'resolved' "
        "WHEN EXISTS (SELECT 1 FROM escalations s "
        f"WHERE s.exception_id = {table}.exception_id) THEN 'escalated' ELSE 'open' END"
    )


@dataclass(frozen=True)
class ExceptionFilter:
    """Filters for the manager's exception list. None means "no filter on this field"."""

    code: ExceptionCode | None = None
    severity: Severity | None = None
    status: str | None = None
    employee_id: str | None = None
    exception_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    offset: int = 0
    limit: int = 50

    def matches(self, *, code, severity, status, employee_id, exception_id, work_date) -> bool:
        """The same predicate as the SQL below, for stores that cannot filter in SQL."""
        return (
            (self.code is None or code == self.code)
            and (self.severity is None or severity == self.severity)
            and (self.status is None or status == self.status)
            and (self.employee_id is None or employee_id == self.employee_id)
            and (self.exception_id is None or exception_id == self.exception_id)
            and (self.date_from is None or work_date >= self.date_from)
            and (self.date_to is None or work_date <= self.date_to)
        )


def sort_key(severity, work_date, exception_id) -> tuple:
    """Problems first, then oldest work date, then id. Mirrors the SQL ORDER BY."""
    return (severity != Severity.PROBLEM, work_date, exception_id)


def where_clauses(filters: ExceptionFilter) -> tuple[list[str], list]:
    """SQL conditions and their parameters, against the derived view `q`."""
    conditions, params = [], []
    for column, value in (
        ("code", filters.code.value if filters.code else None),
        ("severity", filters.severity.value if filters.severity else None),
        ("status", filters.status),
        ("employee_id", filters.employee_id),
        ("exception_id", filters.exception_id),
    ):
        if value is not None:
            conditions.append(f"q.{column} = ?")
            params.append(value)
    if filters.date_from is not None:
        conditions.append("q.work_date >= ?")
        params.append(filters.date_from)
    if filters.date_to is not None:
        conditions.append("q.work_date <= ?")
        params.append(filters.date_to)
    return conditions, params
