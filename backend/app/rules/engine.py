"""Deterministic demo-policy checks shared by detection and correction simulation.

Every check sets RuleCheck.outcome (contract 0.2.0): PASS, VIOLATION (the timecard
breaks a rule) or INSUFFICIENT_EVIDENCE (the rule cannot be decided from the inputs).
RuleCheck.passed == (outcome == PASS).
No policy text, model outputs or detection_details are used as trusted aggregates.
"""

from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from app.attendance.context import build_verified_case
from app.core.contracts import (
    CaseContext,
    ExceptionCode,
    PolicyRules,
    PolicySnapshot,
    PunchType,
    RuleCheck,
    RuleOutcome,
)

RULE_VERSION = "attendance-rules@0.4-draft"
Outcome = RuleOutcome  # the shared contract enum


@dataclass(frozen=True)
class AggregateEvidence:
    """Trusted backend input; never populated from model/client detection_details.

    Other-day hours exclude ALL work on the case work_date. Remaining hours exclude
    the current case shift. Caller must certify the full work-date set is in case.punches.
    Quarterly totals exclude this work date's overtime. week_start/quarter_start name the
    periods the totals cover (local dates); as_of is when they were read (aware time).
    The loader must re-read them on every validation, including at approval.
    """

    work_date_complete: bool = False
    week_other_worked_hours: float | None = None
    week_remaining_scheduled_hours: float | None = None
    quarter_other_overtime_hours: float | None = None
    week_start: date | None = None
    quarter_start: date | None = None
    as_of: datetime | None = None

    def __post_init__(self):
        for value in (
            self.week_other_worked_hours,
            self.week_remaining_scheduled_hours,
            self.quarter_other_overtime_hours,
        ):
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError("aggregates must be finite and nonnegative")
        if self.as_of is not None and self.as_of.utcoffset() is None:
            raise ValueError("aggregate as_of must be timezone-aware")
        if self.quarter_start is not None and self.quarter_start.day != 1:
            raise ValueError("quarter_start must be the first day of a month")


def instant(value: datetime) -> datetime:
    return value.astimezone(UTC)


def hours(start: datetime, end: datetime) -> float:
    return (instant(end) - instant(start)).total_seconds() / 3600


def blocked_checks(
    reason: str, outcome: Outcome = Outcome.INSUFFICIENT_EVIDENCE
) -> list[RuleCheck]:
    return [
        RuleCheck(code=code, passed=outcome == Outcome.PASS, reason=reason, outcome=outcome)
        for code in ExceptionCode
    ]


def _aggregate_gap(
    aggregates: AggregateEvidence, case: CaseContext, rules: PolicyRules
) -> str | None:
    """Why the totals cannot be used for this work date, or None when they can."""
    a = aggregates
    if not a.work_date_complete or a.week_other_worked_hours is None:
        return "work-date or weekly worked totals missing"
    if a.week_remaining_scheduled_hours is None:
        return "remaining scheduled hours missing"
    if a.week_start is None or a.as_of is None:
        return "aggregate period or as-of time missing"
    if a.week_start.weekday() != rules.week_start.number:
        return f"weekly totals do not start on the policy week start ({rules.week_start.value})"
    if not a.week_start <= case.work_date < a.week_start + timedelta(days=7):
        return "weekly totals cover a different week"
    if rules.quarterly_ot_cap_hours is not None:
        if a.quarter_other_overtime_hours is None or a.quarter_start is None:
            return "quarterly overtime total missing"
        months = (case.work_date.year - a.quarter_start.year) * 12 + (
            case.work_date.month - a.quarter_start.month
        )
        if (a.quarter_start.month - rules.quarter_start_month) % 3:
            return "quarterly total does not start on a policy quarter boundary"
        if not 0 <= months <= 2:
            return "quarterly total covers a different quarter"
    return None


def _describe(aggregates: AggregateEvidence, net_hours: float, quarterly: bool) -> str:
    """Record exactly which totals a decision used (agreed with Track B)."""
    a = aggregates
    text = (
        f"day {net_hours:.2f} h; week from {a.week_start}: "
        f"{a.week_other_worked_hours:.2f} h other worked + "
        f"{a.week_remaining_scheduled_hours:.2f} h remaining scheduled"
    )
    if quarterly:
        text += f"; quarter from {a.quarter_start}: {a.quarter_other_overtime_hours:.2f} h other OT"
    return f"{text}; totals as of {instant(a.as_of).isoformat()}"


def _pair(events: list) -> tuple[list, list, bool, bool, bool, bool]:
    """FIFO work pairing and break pairing over time-sorted punches.

    Returns (work, breaks, missing, break_invalid, overlap, only_open_in). only_open_in
    means the sole pairing gap is clock-ins still awaiting a clock-out. Shared by the six
    checks and by net_worked_hours so recorded totals use identical pairing.
    """
    work, breaks, pending = [], [], deque()
    missing = False
    break_start = None
    break_invalid = False
    for punch in events:
        if punch.type == PunchType.IN:
            pending.append(punch.ts)
        elif punch.type == PunchType.OUT:
            if pending:
                work.append((pending.popleft(), punch.ts))
            else:
                missing = True
        elif punch.type == PunchType.BREAK_START:
            if break_start is not None:
                break_invalid = True
            break_start = punch.ts
        elif break_start is None:
            break_invalid = True
        else:
            breaks.append((break_start, punch.ts))
            break_start = None
    only_open_in = bool(pending) and not missing
    missing = missing or bool(pending)
    break_invalid = break_invalid or break_start is not None
    overlap = any(
        instant(right[0]) < instant(left[1]) for left, right in zip(work, work[1:], strict=False)
    )
    # A break must belong to exactly one worked interval, never overlapping shifts.
    for start, end in breaks:
        if sum(instant(ws) <= instant(start) < instant(end) <= instant(we) for ws, we in work) != 1:
            break_invalid = True
    return work, breaks, missing, break_invalid, overlap, only_open_in


def net_worked_hours(punches: list) -> float | None:
    """Net paired work minus breaks, or None when the punches cannot be paired cleanly."""
    events = sorted(punches, key=lambda p: instant(p.ts))
    if len({instant(p.ts) for p in events}) != len(events):
        return None
    work, breaks, missing, break_invalid, overlap, _ = _pair(events)
    if missing or break_invalid or overlap or not work:
        return None
    return sum(hours(s, e) for s, e in work) - sum(hours(s, e) for s, e in breaks)


def evaluate_rule_outcomes(
    case: CaseContext, policy: PolicySnapshot, aggregates: AggregateEvidence | None = None
) -> list[tuple[RuleCheck, Outcome]]:
    """Evaluate a CLOSED work-date context; active-shift detection needs as_of contract.

    FIFO pairing preserves overlapping work intervals for detection instead of hiding
    a second clock-in. Ambiguous equal instants are rejected. Breaks must be observed.
    """
    aggregates = aggregates or AggregateEvidence()

    def blocked(reason: str) -> list[tuple[RuleCheck, Outcome]]:
        return [(c, Outcome.INSUFFICIENT_EVIDENCE) for c in blocked_checks(reason)]

    try:
        case = build_verified_case(case, correction_revision=0)
        policy = PolicySnapshot.model_validate(policy.model_dump())
        if (
            policy.status != "active"
            or policy.jurisdiction != case.employee.jurisdiction
            or case.work_date < policy.effective_from
            or (policy.effective_to is not None and case.work_date > policy.effective_to)
        ):
            return blocked("Applicable active policy evidence is missing or inconsistent.")
        rules = policy.rules
        if any(isinstance(v, float) and not isfinite(v) for v in rules.model_dump().values()):
            return blocked("Policy contains non-finite thresholds.")
    except (ValueError, KeyError) as exc:
        return blocked(f"Invalid context: {exc}")
    events = sorted(case.punches, key=lambda p: instant(p.ts))
    if not events:
        return blocked("Attendance evidence missing; absence is not a completed timecard.")
    # Simultaneous boundaries can be valid, but draft contracts cannot disambiguate them.
    if len({instant(p.ts) for p in events}) != len(events):
        return blocked("Ambiguous simultaneous punches require clarification.")
    # work_date is the local shift-start date (build_verified_case convention). A clock-in
    # on another local date belongs to another work-date context; counting it here would
    # double-count it against that day's totals. Overnight clock-outs remain in scope.
    zone = ZoneInfo(case.employee.timezone)
    if any(
        p.type == PunchType.IN and p.ts.astimezone(zone).date() != case.work_date for p in events
    ):
        return blocked("Clock-in outside the case's local work date; scope is ambiguous.")
    work, breaks, missing, break_invalid, overlap, only_open_in = _pair(events)
    complete = not missing and bool(work)
    # A shift still running at as_of is not missing a clock-out yet (contract 0.2.0).
    still_open = (
        only_open_in
        and case.as_of is not None
        and case.schedule is not None
        and instant(case.as_of) < instant(case.schedule.end)
    )
    net_hours = sum(hours(s, e) for s, e in work) - sum(hours(s, e) for s, e in breaks)
    ok, bad, unknown = Outcome.PASS, Outcome.VIOLATION, Outcome.INSUFFICIENT_EVIDENCE
    unpaired = "Cannot evaluate: work punches are unpaired."

    if complete:
        missing_punch = (ok, "Work punches paired.")
    elif still_open:
        missing_punch = (unknown, "Shift still open at evaluation time; not yet missing.")
    else:
        missing_punch = (bad, "Unmatched or missing work punch.")
    if not complete:
        overlapping = (unknown, unpaired)
    elif overlap:
        overlapping = (bad, "Overlapping work intervals.")
    else:
        overlapping = (ok, "No work intervals overlap.")

    if not complete or overlap:
        meal = (unknown, "Cannot evaluate breaks without paired, non-overlapping work.")
    elif break_invalid:
        meal = (bad, "Break punches unpaired or outside a single worked interval.")
    else:
        meal = (ok, "Observed breaks meet demo policy.")
        for start, end in work:
            cursor = start
            for bs, be in breaks:
                if instant(start) <= instant(bs) and instant(be) <= instant(end):
                    if hours(cursor, bs) > rules.rest_after_hours:
                        meal = (bad, "Required break missing, short or late.")
                    if hours(bs, be) * 60 >= rules.rest_minutes:
                        cursor = be
            if hours(cursor, end) > rules.rest_after_hours:
                meal = (bad, "Required break missing, short or late.")

    quarterly = rules.quarterly_ot_cap_hours is not None
    gap = _aggregate_gap(aggregates, case, rules)
    if not complete or overlap or break_invalid:
        overtime = (unknown, "Cannot evaluate hours: worked or break intervals are invalid.")
    elif gap:
        overtime = (unknown, f"Overtime evidence incomplete: {gap}.")
    else:
        used = _describe(aggregates, net_hours, quarterly)
        projected = (
            net_hours
            + aggregates.week_other_worked_hours
            + aggregates.week_remaining_scheduled_hours
        )
        within = net_hours <= rules.daily_regular_hours and projected <= rules.weekly_regular_hours
        if quarterly:
            within = within and (
                aggregates.quarter_other_overtime_hours
                + max(0, net_hours - rules.daily_regular_hours)
                <= rules.quarterly_ot_cap_hours
            )
        overtime = (
            (ok, f"Within configured hour limits ({used}).")
            if within
            else (bad, f"Configured daily, weekly or quarterly hour limit exceeded ({used}).")
        )

    if not complete:
        spread = (unknown, unpaired)
    elif rules.max_spread_hours is not None and (
        hours(work[0][0], max((e for _, e in work), key=instant)) > rules.max_spread_hours
    ):
        spread = (bad, "Spread exceeds the configured maximum.")
    else:
        spread = (ok, "Within configured spread.")

    if case.schedule is None:
        schedule = (unknown, "No schedule to compare against.")
    elif not complete:
        schedule = (unknown, unpaired)
    else:
        tolerance = rules.late_tolerance_min * 60
        inside = (
            abs((instant(work[0][0]) - instant(case.schedule.start)).total_seconds()) <= tolerance
            and abs((instant(work[-1][1]) - instant(case.schedule.end)).total_seconds())
            <= tolerance
        )
        schedule = (
            (ok, "Within schedule tolerance.") if inside else (bad, "Outside schedule tolerance.")
        )

    values = {
        ExceptionCode.MISSING_PUNCH: missing_punch,
        ExceptionCode.OVERLAPPING_SHIFT: overlapping,
        ExceptionCode.MEAL_BREAK_BREACH: meal,
        ExceptionCode.OVERTIME_RISK: overtime,
        ExceptionCode.SPREAD_OVER_BREACH: spread,
        ExceptionCode.SCHEDULE_DEVIATION: schedule,
    }
    return [
        (
            RuleCheck(code=code, passed=outcome == Outcome.PASS, reason=reason, outcome=outcome),
            outcome,
        )
        for code, (outcome, reason) in values.items()
    ]


def evaluate_rules(
    case: CaseContext, policy: PolicySnapshot, aggregates: AggregateEvidence | None = None
) -> list[RuleCheck]:
    """Six RuleChecks for the shared 0.1 contract; outcomes via evaluate_rule_outcomes."""
    return [check for check, _ in evaluate_rule_outcomes(case, policy, aggregates)]
