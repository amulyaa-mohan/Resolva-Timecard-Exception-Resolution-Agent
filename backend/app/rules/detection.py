"""Exception detection from punches (pure). Uses the same rule functions as the validator.

Work-date convention (shared with build_verified_case): a work date is the local date its
clock-in happened. A session stays open until every clock-in is paired, so an overnight
clock-out belongs to the previous day; a punch with no open session uses its own local date.
Only VIOLATION outcomes become exceptions. INSUFFICIENT_EVIDENCE is reported, not raised as
an exception, because it is not yet known to be a problem (e.g. a shift still running).
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.contracts import (
    CaseContext,
    EmployeeContext,
    ExceptionCode,
    PolicySnapshot,
    PunchRecord,
    PunchType,
    RuleOutcome,
    ScheduledShift,
    Severity,
)
from app.rules.engine import AggregateEvidence, evaluate_rule_outcomes, instant


@dataclass(frozen=True)
class Finding:
    code: ExceptionCode
    outcome: RuleOutcome
    reason: str


def group_by_work_date(punches: list[PunchRecord], timezone: str) -> dict[date, list[PunchRecord]]:
    zone = ZoneInfo(timezone)
    groups: dict[date, list[PunchRecord]] = {}
    session: date | None = None
    open_ins = 0
    for punch in sorted(punches, key=lambda p: instant(p.ts)):
        local = punch.ts.astimezone(zone).date()
        if punch.type == PunchType.IN:
            if open_ins == 0:
                session = local
            open_ins += 1
        key = session if open_ins > 0 else local
        if punch.type == PunchType.OUT and open_ins > 0:
            open_ins -= 1
            key = session
        groups.setdefault(key, []).append(punch)
    return groups


def shift_for(
    shifts: list[ScheduledShift], work_date: date, timezone: str
) -> ScheduledShift | None:
    """The single shift starting on the work date; None when there is none or several."""
    zone = ZoneInfo(timezone)
    matches = [s for s in shifts if s.start.astimezone(zone).date() == work_date]
    return matches[0] if len(matches) == 1 else None


def detect(
    employee: EmployeeContext,
    work_date: date,
    punches: list[PunchRecord],
    schedule: ScheduledShift | None,
    policy: PolicySnapshot,
    *,
    as_of: datetime,
    aggregates: AggregateEvidence | None = None,
) -> list[Finding]:
    """Every rule's outcome for one employee work date (non-pass outcomes only)."""
    case = CaseContext(
        exception_id="detection",
        code=ExceptionCode.MISSING_PUNCH,
        severity=Severity.PROBLEM,
        employee=employee,
        work_date=work_date,
        rule_version="detection",
        punches=punches,
        schedule=schedule,
        evidence_version="detection",
        as_of=as_of,
    )
    return [
        Finding(check.code, outcome, check.reason)
        for check, outcome in evaluate_rule_outcomes(case, policy, aggregates)
        if outcome != RuleOutcome.PASS
    ]


def violations(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.outcome == RuleOutcome.VIOLATION]
