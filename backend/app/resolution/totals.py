"""Trusted weekly/quarterly totals for the validator, read from stored day totals.

Day totals are written only by trusted server code: demo provisioning today, the import
pipeline (A-05) later, and approved corrections. Never by HTTP clients or models.
Calendar from the policy (contract 0.2.0): rules.week_start and rules.quarter_start_month,
both on the employee's local dates (demo packs: Monday weeks, calendar quarters).
"""

import sqlite3
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.contracts import CaseContext, PolicySnapshot
from app.rules.engine import AggregateEvidence

SCHEMA = """
CREATE TABLE IF NOT EXISTS day_totals (
    employee_id TEXT NOT NULL,
    work_date TEXT NOT NULL,
    worked_hours REAL NOT NULL CHECK (worked_hours >= 0),
    scheduled_hours REAL NOT NULL CHECK (scheduled_hours >= 0),
    evidence_final INTEGER NOT NULL CHECK (evidence_final IN (0, 1)),
    complete INTEGER NOT NULL CHECK (complete IN (0, 1)),
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (employee_id, work_date),
    CHECK (evidence_final OR NOT complete)
);
"""


def week_start(day: date, start_weekday: int = 0) -> date:
    """The policy week containing `day`; start_weekday uses date.weekday() (Monday = 0)."""
    return day - timedelta(days=(day.weekday() - start_weekday) % 7)


def _add_months(year: int, month: int, months: int) -> date:
    index = year * 12 + (month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def quarter_bounds(day: date, start_month: int = 1) -> tuple[date, date]:
    """[first day of the policy quarter containing `day`, first day of the next one)."""
    start = _add_months(day.year, day.month, -((day.month - start_month) % 3))
    return start, _add_months(start.year, start.month, 3)


def load_aggregates(
    connection: sqlite3.Connection,
    case: CaseContext,
    policy: PolicySnapshot,
    now: datetime,
) -> AggregateEvidence | None:
    """Totals as of `now`, or None when any required day is missing or incomplete.

    The work date must be evidence-final (its punches are all in; its hours come from the
    case itself, so they may still be unpaired). Every other past day must be complete:
    final AND its hours known. An unpaired other day is unknown, never zero. A day that is today
    or later counts its scheduled hours as remaining work. The case work date is excluded
    from every sum: the rules engine computes it from the case's own punches.
    """
    work_date = case.work_date
    today = now.astimezone(ZoneInfo(case.employee.timezone)).date()
    week = week_start(work_date, policy.rules.week_start.number)
    q_start, q_end = quarter_bounds(work_date, policy.rules.quarter_start_month)
    first, last = min(week, q_start), max(week + timedelta(days=7), q_end)
    rows = {
        (r[0] if isinstance(r[0], date) else date.fromisoformat(r[0])): (
            r[1],
            r[2],
            bool(r[3]),
            bool(r[4]),
        )
        for r in connection.execute(
            "SELECT work_date, worked_hours, scheduled_hours, complete, evidence_final "
            "FROM day_totals "
            "WHERE employee_id=? AND work_date>=? AND work_date<?",
            (case.employee.employee_id, first.isoformat(), last.isoformat()),
        )
    }
    current = rows.get(work_date)
    if current is None or not current[3]:
        return None  # the work date's evidence is not final
    week_other = remaining = 0.0
    for offset in range(7):
        day = week + timedelta(days=offset)
        if day == work_date:
            continue
        row = rows.get(day)
        if row is None:
            return None
        worked, scheduled, complete, _final = row
        if complete:
            week_other += worked
        elif day < today:
            return None  # a finished day without complete evidence
        else:
            remaining += scheduled
    quarter_ot = 0.0
    if policy.rules.quarterly_ot_cap_hours is not None:
        day = q_start
        while day < q_end and day < today:
            if day != work_date:
                row = rows.get(day)
                if row is None or not row[2]:
                    return None
                quarter_ot += max(0.0, row[0] - policy.rules.daily_regular_hours)
            day += timedelta(days=1)
    return AggregateEvidence(
        work_date_complete=True,
        week_other_worked_hours=week_other,
        week_remaining_scheduled_hours=remaining,
        quarter_other_overtime_hours=quarter_ot,
        week_start=week,
        quarter_start=q_start,
        as_of=now.astimezone(UTC),
    )


def upsert_day_total(
    connection: sqlite3.Connection,
    *,
    employee_id: str,
    work_date: date,
    worked_hours: float,
    scheduled_hours: float,
    complete: bool,
    source: str,
    evidence_final: bool | None = None,
    now: datetime,
) -> None:
    """Trusted server-side write only (provisioning, imports, approved corrections).

    evidence_final defaults to `complete` (a complete day is necessarily final)."""
    final = complete if evidence_final is None else evidence_final
    connection.execute(
        "INSERT INTO day_totals (employee_id, work_date, worked_hours, scheduled_hours, "
        "evidence_final, complete, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(employee_id, work_date) DO UPDATE SET worked_hours=excluded.worked_hours, "
        "scheduled_hours=excluded.scheduled_hours, complete=excluded.complete, "
        "evidence_final=excluded.evidence_final, "
        "source=excluded.source, updated_at=excluded.updated_at",
        (
            employee_id,
            work_date.isoformat(),
            worked_hours,
            scheduled_hours,
            bool(final),
            bool(complete),
            source,
            now.astimezone(UTC).isoformat(),
        ),
    )
