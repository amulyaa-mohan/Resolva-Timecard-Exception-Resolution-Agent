"""Structured detection_details: the facts agreed with Track B, derived from the same evidence."""

from datetime import UTC, date, datetime

import pytest

from app.core.contracts import (
    EmployeeContext,
    ExceptionCode,
    PunchRecord,
    PunchSource,
    RuleOutcome,
    ScheduledShift,
)
from app.rules.detection import detect, violations
from app.rules.engine import AggregateEvidence
from app.rules.explain import explain
from tests.factories import IST

EMPLOYEE = EmployeeContext(
    employee_id="E-001", location_id="BLR-01", jurisdiction="IN-KA", timezone="Asia/Kolkata"
)
DAY = date(2026, 11, 12)
LATE = datetime(2026, 11, 13, tzinfo=UTC)
ALLOWED = {
    ExceptionCode.MISSING_PUNCH: {"unmatched_punch_id", "missing_type"},
    ExceptionCode.OVERLAPPING_SHIFT: {"overlapping_punch_ids"},
    ExceptionCode.MEAL_BREAK_BREACH: {"worked_min_before_break", "break_min"},
    ExceptionCode.OVERTIME_RISK: {"day_hours", "projected_week_hours", "limit_hours", "limit_kind"},
    ExceptionCode.SPREAD_OVER_BREACH: {"spread_hours"},
    ExceptionCode.SCHEDULE_DEVIATION: {"boundary", "minutes_off"},
}


def day(*events):
    """Punches from (type, 'HH:MM') pairs on the work date; ids are P-0, P-1, ... in order."""
    return [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id="E-001",
            ts=datetime.combine(DAY, datetime.strptime(clock, "%H:%M").time(), tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        )
        for i, (kind, clock) in enumerate(events)
    ]


def shift(start="09:00", end="18:00"):
    begin = datetime.combine(DAY, datetime.strptime(start, "%H:%M").time(), tzinfo=IST)
    finish = datetime.combine(DAY, datetime.strptime(end, "%H:%M").time(), tzinfo=IST)
    return ScheduledShift(
        shift_id="S-1", employee_id="E-001", start=begin, end=finish, planned_break_min=60
    )


FULL = [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")]


def found(punches, schedule, policy, aggregates=None):
    findings = detect(EMPLOYEE, DAY, punches, schedule, policy, as_of=LATE, aggregates=aggregates)
    return {f.code: f for f in violations(findings)}


def totals(**overrides):
    base = dict(
        work_date_complete=True,
        week_other_worked_hours=0.0,
        week_remaining_scheduled_hours=0.0,
        quarter_other_overtime_hours=0.0,
        week_start=date(2026, 11, 9),
        quarter_start=date(2026, 10, 1),
        as_of=LATE,
    )
    return AggregateEvidence(**{**base, **overrides})


def test_missing_clock_out_names_the_dangling_clock_in(policy):
    hit = found(
        day(("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00")), shift(), policy
    )[ExceptionCode.MISSING_PUNCH]
    assert hit.details == {"unmatched_punch_id": "P-0", "missing_type": "out"}


def test_missing_clock_in_names_the_orphan_clock_out(policy):
    hit = found(
        day(("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")), shift(), policy
    )[ExceptionCode.MISSING_PUNCH]
    assert hit.details == {"unmatched_punch_id": "P-2", "missing_type": "in"}


def test_overlap_lists_the_four_punches_involved(policy):
    hit = found(
        day(("in", "09:00"), ("in", "10:00"), ("out", "17:00"), ("out", "18:00")), shift(), policy
    )[ExceptionCode.OVERLAPPING_SHIFT]
    assert hit.details == {"overlapping_punch_ids": "P-0,P-2,P-1,P-3"}


@pytest.mark.parametrize(
    "events,worked,brk",
    [
        ([("in", "09:00"), ("out", "18:00")], 540, 0),  # no break at all
        (
            [("in", "09:00"), ("break_start", "13:00"), ("break_end", "13:30"), ("out", "18:00")],
            540,
            30,
        ),  # a 30 min break does not satisfy a 60 min rest
        # Audit A1: a one-minute clock-out gap is no meal break either.
        ([("in", "09:00"), ("out", "13:00"), ("in", "13:01"), ("out", "18:00")], 540, 0),
    ],
)
def test_meal_break_reports_the_stretch_and_the_longest_break(events, worked, brk, policy):
    hit = found(day(*events), shift(), policy)[ExceptionCode.MEAL_BREAK_BREACH]
    assert hit.details == {"worked_min_before_break": worked, "break_min": brk}


def test_daily_overtime(policy):
    events = [
        ("in", "06:00"),
        ("break_start", "10:30"),
        ("break_end", "11:30"),
        ("break_start", "15:00"),
        ("break_end", "16:00"),
        ("out", "18:30"),
    ]
    hit = found(day(*events), shift("06:00", "18:30"), policy, totals())[
        ExceptionCode.OVERTIME_RISK
    ]
    assert hit.details == {
        "day_hours": 10.5,
        "projected_week_hours": 10.5,
        "limit_hours": 9,
        "limit_kind": "daily",
    }


def test_weekly_overtime_reports_the_projection(policy):
    hit = found(day(*FULL), shift(), policy, totals(week_other_worked_hours=41.0))[
        ExceptionCode.OVERTIME_RISK
    ]
    assert hit.details == {
        "day_hours": 8.0,
        "projected_week_hours": 49.0,
        "limit_hours": 48,
        "limit_kind": "weekly",
    }


def test_quarterly_overtime(policy):
    # Overtime already booked this quarter is over the 50 h cap, so even an ordinary 8 h day
    # fires the rule, and the facts say which limit it is.
    hit = found(day(*FULL), shift(), policy, totals(quarter_other_overtime_hours=50.5))[
        ExceptionCode.OVERTIME_RISK
    ]
    assert hit.details == {
        "day_hours": 8.0,
        "projected_week_hours": 8.0,
        "limit_hours": 50.0,
        "limit_kind": "quarterly",
    }
    # At the cap exactly there is no violation (the limit is inclusive).
    at_cap = found(day(*FULL), shift(), policy, totals(quarter_other_overtime_hours=50.0))
    assert ExceptionCode.OVERTIME_RISK not in at_cap


def test_spread(policy):
    events = [("in", "06:00"), ("break_start", "10:30"), ("break_end", "11:30"), ("out", "18:30")]
    hit = found(day(*events), shift("06:00", "18:30"), policy, totals())[
        ExceptionCode.SPREAD_OVER_BREACH
    ]
    assert hit.details == {"spread_hours": 12.5}


@pytest.mark.parametrize(
    "events,boundary,minutes",
    [
        (
            [("in", "09:25"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:00")],
            "start",
            25,
        ),  # late arrival
        (
            [("in", "09:00"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "17:30")],
            "end",
            30,
        ),  # early departure
    ],
)
def test_schedule_deviation_boundary_and_size(events, boundary, minutes, policy):
    hit = found(day(*events), shift(), policy, totals())[ExceptionCode.SCHEDULE_DEVIATION]
    assert hit.details == {"boundary": boundary, "minutes_off": minutes}


def test_early_arrival_and_late_departure_are_not_deviations(policy):
    """Audit A5 / KA-9: only late arrival and early departure count."""
    events = [("in", "08:30"), ("break_start", "13:00"), ("break_end", "14:00"), ("out", "18:40")]
    assert ExceptionCode.SCHEDULE_DEVIATION not in found(day(*events), shift(), policy, totals())


def test_details_exist_only_for_violations_and_use_agreed_scalar_keys(policy):
    cases = [
        (day(("in", "09:00")), None),
        (day(*FULL), shift()),
        (day(("in", "09:00"), ("out", "18:00")), shift()),
        (day(("in", "09:25"), ("out", "18:00")), shift()),
    ]
    for punches, schedule in cases:
        for finding in detect(EMPLOYEE, DAY, punches, schedule, policy, as_of=LATE):
            if finding.outcome != RuleOutcome.VIOLATION:
                assert finding.details == {}  # undecided evidence gets no invented facts
                continue
            assert set(finding.details) <= ALLOWED[finding.code]
            assert all(isinstance(v, str | int | float | bool) for v in finding.details.values())


def test_explain_is_empty_when_nothing_specific_can_be_said(policy):
    assert explain(ExceptionCode.MISSING_PUNCH, day(*FULL), shift(), policy) == {}
    assert explain(ExceptionCode.SPREAD_OVER_BREACH, [], shift(), policy) == {}
    assert explain(ExceptionCode.SCHEDULE_DEVIATION, day(*FULL), None, policy) == {}
