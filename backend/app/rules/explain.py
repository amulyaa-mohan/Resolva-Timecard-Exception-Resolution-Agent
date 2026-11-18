"""Structured facts about why a rule fired (agreed with Track B, 2026-11-18).

`detection_details` feeds the model's <facts> block and the manager's explanation. These values
describe a violation the engine has already found; they never decide one. Keys are scalar
(contract `DetailValue`) and use the names Track B asked for. Everything is derived from the
same punches, schedule, policy and totals the rule engine used.

Key names per code (all values are str / int / float / bool):
  MISSING_PUNCH       unmatched_punch_id, missing_type ("in" | "out")
  OVERLAPPING_SHIFT   overlapping_punch_ids (comma-separated)
  MEAL_BREAK_BREACH   worked_min_before_break, break_min
  OVERTIME_RISK       day_hours, projected_week_hours, limit_hours, limit_kind
  SPREAD_OVER_BREACH  spread_hours
  SCHEDULE_DEVIATION  boundary ("start" | "end"), minutes_off
"""

from collections import deque

from app.core.contracts import (
    DetailValue,
    ExceptionCode,
    PolicySnapshot,
    PunchRecord,
    PunchType,
    ScheduledShift,
)
from app.rules.engine import AggregateEvidence, hours, instant, net_worked_hours

Details = dict[str, DetailValue]


def _ordered(punches: list[PunchRecord]) -> list[PunchRecord]:
    return sorted(punches, key=lambda p: instant(p.ts))


def _pairs(punches: list[PunchRecord]):
    """FIFO work pairing with ids, mirroring the rule engine. Returns (pairs, loose_ins, loose_outs)."""
    pending: deque[PunchRecord] = deque()
    pairs: list[tuple[PunchRecord, PunchRecord]] = []
    loose_outs: list[PunchRecord] = []
    for punch in _ordered(punches):
        if punch.type == PunchType.IN:
            pending.append(punch)
        elif punch.type == PunchType.OUT:
            if pending:
                pairs.append((pending.popleft(), punch))
            else:
                loose_outs.append(punch)
    return pairs, list(pending), loose_outs


def _round(value: float, places: int = 2) -> float:
    return round(value, places)


def _missing_punch(punches: list[PunchRecord]) -> Details:
    _, loose_ins, loose_outs = _pairs(punches)
    if loose_ins:
        return {"unmatched_punch_id": loose_ins[0].punch_id, "missing_type": "out"}
    if loose_outs:
        return {"unmatched_punch_id": loose_outs[0].punch_id, "missing_type": "in"}
    return {}


def _overlap(punches: list[PunchRecord]) -> Details:
    pairs, _, _ = _pairs(punches)
    for (in_a, out_a), (in_b, out_b) in zip(pairs, pairs[1:], strict=False):
        if instant(in_b.ts) < instant(out_a.ts):
            ids = [in_a.punch_id, out_a.punch_id, in_b.punch_id, out_b.punch_id]
            return {"overlapping_punch_ids": ",".join(ids)}
    return {}


def _meal_break(punches: list[PunchRecord], policy: PolicySnapshot) -> Details:
    """Longest stretch worked without a qualifying rest, and the longest break recorded."""
    rules = policy.rules
    pairs, _, _ = _pairs(punches)
    if not pairs:
        return {}
    events = _ordered(punches)
    breaks, started = [], None
    for punch in events:
        if punch.type == PunchType.BREAK_START:
            started = punch
        elif punch.type == PunchType.BREAK_END and started is not None:
            breaks.append((started.ts, punch.ts))
            started = None
    longest_break = max((hours(s, e) * 60 for s, e in breaks), default=0.0)
    # Same walk as the rule: a rest of at least rest_minutes, a break or a gap between work
    # intervals, restarts the count.
    worst, cursor, previous_end = 0.0, None, None
    for start, end in ((i.ts, o.ts) for i, o in pairs):
        if cursor is None or hours(previous_end, start) * 60 >= rules.rest_minutes:
            cursor = start
        previous_end = end
        for break_start, break_end in breaks:
            if instant(start) <= instant(break_start) and instant(break_end) <= instant(end):
                worst = max(worst, hours(cursor, break_start))
                if hours(break_start, break_end) * 60 >= rules.rest_minutes:
                    cursor = break_end
        worst = max(worst, hours(cursor, end))
    return {
        "worked_min_before_break": round(worst * 60),
        "break_min": round(longest_break),
    }


def _overtime(
    punches: list[PunchRecord], policy: PolicySnapshot, aggregates: AggregateEvidence | None
) -> Details:
    rules = policy.rules
    day = net_worked_hours(punches)
    if day is None:
        return {}
    details: Details = {"day_hours": _round(day)}
    if aggregates is not None and None not in (
        aggregates.week_other_worked_hours,
        aggregates.week_remaining_scheduled_hours,
    ):
        projected = (
            day + aggregates.week_other_worked_hours + aggregates.week_remaining_scheduled_hours
        )
        details["projected_week_hours"] = _round(projected)
        quarter = None
        if rules.quarterly_ot_cap_hours is not None and (
            aggregates.quarter_other_overtime_hours is not None
        ):
            quarter = aggregates.quarter_other_overtime_hours + max(
                0.0, day - rules.daily_regular_hours
            )
        if day > rules.daily_regular_hours:
            details.update(limit_hours=rules.daily_regular_hours, limit_kind="daily")
        elif projected > rules.weekly_regular_hours:
            details.update(limit_hours=rules.weekly_regular_hours, limit_kind="weekly")
        elif quarter is not None and quarter > rules.quarterly_ot_cap_hours:
            details.update(limit_hours=rules.quarterly_ot_cap_hours, limit_kind="quarterly")
    elif day > rules.daily_regular_hours:
        details.update(limit_hours=rules.daily_regular_hours, limit_kind="daily")
    return details


def _spread(punches: list[PunchRecord]) -> Details:
    pairs, _, _ = _pairs(punches)
    if not pairs:
        return {}
    first_in = min((i.ts for i, _ in pairs), key=instant)
    last_out = max((o.ts for _, o in pairs), key=instant)
    return {"spread_hours": _round(hours(first_in, last_out))}


def _deviation(
    punches: list[PunchRecord], schedule: ScheduledShift | None, policy: PolicySnapshot
) -> Details:
    """Late arrival or early departure, as KA-9 / US-6 define a schedule deviation."""
    pairs, _, _ = _pairs(punches)
    if not pairs or schedule is None:
        return {}
    first_in = min((i.ts for i, _ in pairs), key=instant)
    last_out = max((o.ts for _, o in pairs), key=instant)
    late = (instant(first_in) - instant(schedule.start)).total_seconds() / 60
    early = (instant(schedule.end) - instant(last_out)).total_seconds() / 60
    tolerance = policy.rules.late_tolerance_min
    if late > tolerance and late >= early:
        return {"boundary": "start", "minutes_off": round(late)}
    if early > tolerance:
        return {"boundary": "end", "minutes_off": round(early)}
    return {}


def explain(
    code: ExceptionCode,
    punches: list[PunchRecord],
    schedule: ScheduledShift | None,
    policy: PolicySnapshot,
    aggregates: AggregateEvidence | None = None,
) -> Details:
    """Scalar facts for one violation. Empty when nothing more specific can be said."""
    if code == ExceptionCode.MISSING_PUNCH:
        return _missing_punch(punches)
    if code == ExceptionCode.OVERLAPPING_SHIFT:
        return _overlap(punches)
    if code == ExceptionCode.MEAL_BREAK_BREACH:
        return _meal_break(punches, policy)
    if code == ExceptionCode.OVERTIME_RISK:
        return _overtime(punches, policy, aggregates)
    if code == ExceptionCode.SPREAD_OVER_BREACH:
        return _spread(punches)
    if code == ExceptionCode.SCHEDULE_DEVIATION:
        return _deviation(punches, schedule, policy)
    return {}
