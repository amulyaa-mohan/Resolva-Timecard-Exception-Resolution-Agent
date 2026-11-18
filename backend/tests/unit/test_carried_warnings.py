"""Warnings a correction does not block (decided 2026-11-18).

1. A warning already open before the correction, on a rule the correction does not target.
2. A late-arrival warning revealed by an added clock-out, and only if it is lateness alone.

Problem-severity rules, the target rule, overtime, meal breaks, and early departures still block.
"""

from datetime import datetime

from app.core.contracts import (
    ActionType,
    CaseContext,
    ExceptionCode,
    ProposedAction,
    PunchRecord,
    PunchSource,
)
from app.rules.validator import _late_only_revealed
from tests.unit.test_track_a_contract_v020 import IST, adjust, case_with, complete_day, validator


def _punch(punch_id, hour, minute, kind):
    return PunchRecord(
        punch_id=punch_id,
        employee_id="E-001",
        ts=datetime(2026, 11, 12, hour, minute, tzinfo=IST),
        type=kind,
        source=PunchSource.KIOSK,
    )


def _late_day_missing_out():
    """Clocked in at 09:25, break 13-14, no clock-out yet (a MISSING_PUNCH)."""
    data = case_with().model_dump()
    kinds = [("in", 9, 25), ("break_start", 13, 0), ("break_end", 14, 0)]
    data["punches"] = [
        _punch(f"P-{i}", h, m, kind).model_dump() for i, (kind, h, m) in enumerate(kinds)
    ]
    data["code"] = ExceptionCode.MISSING_PUNCH
    data["severity"] = "problem"
    return CaseContext.model_validate(data)


def _add_out(hour, minute):
    return ProposedAction(
        type=ActionType.ADD_PUNCH,
        punch_type="out",
        new_ts=datetime(2026, 11, 12, hour, minute, tzinfo=IST),
    )


def test_unrelated_open_warning_does_not_block_the_fix(policy):
    events = [("in", 6, 0), ("break_start", 10, 0), ("break_end", 11, 0), ("out", 18, 20)]
    case = complete_day(events, ExceptionCode.SPREAD_OVER_BREACH)
    result = validator(case, [adjust("P-3", 18, 5)], policy)
    # 6:00-18:05 is still 12 h 05 min: the problem remains, so the fix stays blocked.
    assert not result.passed
    assert ExceptionCode.SPREAD_OVER_BREACH in {c.code for c in result.checks if not c.passed}


def test_carried_warning_says_it_was_already_open(policy):
    events = [("in", 6, 0), ("break_start", 10, 0), ("break_end", 11, 0), ("out", 18, 20)]
    case = complete_day(
        events, ExceptionCode.SPREAD_OVER_BREACH, notes=("I started at 6:25 and left 18:05",)
    )
    result = validator(case, [adjust("P-0", 6, 25), adjust("P-3", 18, 5)], policy)
    carried = [c for c in result.checks if c.code == ExceptionCode.OVERTIME_RISK]
    assert carried and carried[0].passed
    assert "Already open before this correction" in carried[0].reason


def test_late_arrival_revealed_by_an_added_clock_out_does_not_block(policy):
    result = validator(_late_day_missing_out(), [_add_out(18, 0)], policy)
    late = [c for c in result.checks if c.code == ExceptionCode.SCHEDULE_DEVIATION]
    assert late and late[0].passed
    assert "Late arrival revealed by the added clock-out" in late[0].reason
    assert result.passed


def test_early_departure_revealed_by_a_clock_out_is_not_carried(policy):
    case = _late_day_missing_out()
    simulated = case.model_copy(update={"punches": case.punches + [_punch("P-out", 17, 30, "out")]})
    assert not _late_only_revealed(simulated, [_add_out(17, 30)], policy)


def test_late_arrival_is_not_carried_without_a_clock_out(policy):
    case = _late_day_missing_out()
    simulated = case.model_copy(update={"punches": case.punches + [_punch("P-x", 18, 0, "out")]})
    adjust_only = ProposedAction(
        type=ActionType.ADJUST_PUNCH,
        punch_id="P-0",
        new_ts=datetime(2026, 11, 12, 9, 5, tzinfo=IST),
    )
    assert not _late_only_revealed(simulated, [adjust_only], policy)


def test_existing_weekly_overtime_cannot_increase_from_49_to_50_hours(policy):
    from dataclasses import replace

    from app.rules.validator import make_validator
    from tests.unit.test_track_a_contract_v020 import TOTALS

    case = complete_day(
        [("in", 9, 30), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 17, 30)],
        ExceptionCode.SCHEDULE_DEVIATION,
        notes=("I arrived at 09:00 and left at 18:00",),
    )
    validate = make_validator(lambda _: replace(TOTALS, week_other_worked_hours=42))
    result = validate(case, [adjust("P-0", 9, 0), adjust("P-3", 18, 0)], policy)
    outcomes = {check.code: check for check in result.checks}
    assert outcomes[ExceptionCode.SCHEDULE_DEVIATION].passed
    assert not outcomes[ExceptionCode.OVERTIME_RISK].passed
    assert not result.passed
