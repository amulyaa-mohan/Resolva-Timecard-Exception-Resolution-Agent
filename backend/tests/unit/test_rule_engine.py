from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.contracts import (
    ActionType,
    CaseContext,
    ExceptionCode,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
)
from app.rules.engine import AggregateEvidence, evaluate_rules
from app.rules.validator import validate_correction
from tests.factories import make_case


def completed(events=None):
    original = make_case()
    if events is None:
        events = [("in", 9, 0), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 18, 0)]
    punches = [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id=original.employee.employee_id,
            ts=original.schedule.start.replace(hour=h, minute=m),
            type=kind,
            source=PunchSource.KIOSK,
        )
        for i, (kind, h, m) in enumerate(events)
    ]
    return CaseContext.model_validate({**original.model_dump(), "punches": punches})


def checks(case, policy, **aggregate_overrides):
    fields = dict(
        work_date_complete=True,
        week_other_worked_hours=0,
        week_remaining_scheduled_hours=0,
        quarter_other_overtime_hours=0,
        week_start=date(2026, 11, 9),
        quarter_start=date(2026, 10, 1),
        as_of=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
    )
    fields.update(aggregate_overrides)
    return {c.code: c for c in evaluate_rules(case, policy, AggregateEvidence(**fields))}


def test_complete_evidence_all_six_pass(policy):
    outcomes = checks(completed(), policy)
    assert len(outcomes) == 6 and all(c.passed for c in outcomes.values())


@pytest.mark.parametrize(
    "events,code",
    [
        ([("in", 9, 0)], ExceptionCode.MISSING_PUNCH),
        (
            [("in", 9, 0), ("in", 10, 0), ("out", 17, 0), ("out", 18, 0)],
            ExceptionCode.OVERLAPPING_SHIFT,
        ),
        ([("in", 9, 0), ("out", 18, 0)], ExceptionCode.MEAL_BREAK_BREACH),
        ([("in", 9, 0), ("out", 23, 0)], ExceptionCode.SPREAD_OVER_BREACH),
        ([("in", 9, 8), ("out", 18, 0)], ExceptionCode.SCHEDULE_DEVIATION),
    ],
)
def test_real_violations(events, code, policy):
    assert not checks(completed(events), policy)[code].passed


@pytest.mark.parametrize("start,end,expected", [(14, 15, True), (15, 16, False)])
def test_break_deadline_boundary(start, end, expected, policy):
    case = completed(
        [("in", 9, 0), ("break_start", start, 0), ("break_end", end, 0), ("out", 18, 0)]
    )
    assert checks(case, policy)[ExceptionCode.MEAL_BREAK_BREACH].passed is expected


@pytest.mark.parametrize("minutes,expected", [(59, False), (60, True)])
def test_break_duration_boundary(minutes, expected, policy):
    case = completed(
        [
            ("in", 9, 0),
            ("break_start", 13, 0),
            ("break_end", 13 + minutes // 60, minutes % 60),
            ("out", 18, 0),
        ]
    )
    assert checks(case, policy)[ExceptionCode.MEAL_BREAK_BREACH].passed is expected


@pytest.mark.parametrize("minute,expected", [(7, True), (8, False)])
def test_schedule_tolerance(minute, expected, policy):
    case = completed([("in", 9, minute), ("out", 18, 0)])
    assert checks(case, policy)[ExceptionCode.SCHEDULE_DEVIATION].passed is expected


@pytest.mark.parametrize(
    "other,remaining,expected", [(40, 0, True), (40, 0.01, False), (41, 0, False)]
)
def test_weekly_projected_hours(other, remaining, expected, policy):
    assert (
        checks(
            completed(),
            policy,
            week_other_worked_hours=other,
            week_remaining_scheduled_hours=remaining,
        )[ExceptionCode.OVERTIME_RISK].passed
        is expected
    )


@pytest.mark.parametrize("quarter,expected", [(50, True), (50.01, False)])
def test_quarter_boundary(quarter, expected, policy):
    assert (
        checks(completed(), policy, quarter_other_overtime_hours=quarter)[
            ExceptionCode.OVERTIME_RISK
        ].passed
        is expected
    )


def test_daily_boundary(policy):
    # Nine net hours vs nine hours plus one minute.
    for minute, expected in [(0, True), (1, False)]:
        case = completed(
            [("in", 9, 0), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 19, minute)]
        )
        assert checks(case, policy)[ExceptionCode.OVERTIME_RISK].passed is expected


def test_spread_boundary(policy):
    for minute, expected in [(0, True), (1, False)]:
        assert (
            checks(completed([("in", 9, 0), ("out", 21, minute)]), policy)[
                ExceptionCode.SPREAD_OVER_BREACH
            ].passed
            is expected
        )


def test_missing_aggregates_fail_closed_and_client_flags_do_not_help(policy):
    case = completed()
    case.detection_details.update({"week_complete": True, "quarter_hours": 0})
    overtime = next(
        c for c in evaluate_rules(case, policy) if c.code == ExceptionCode.OVERTIME_RISK
    )
    assert not overtime.passed and "incomplete" in overtime.reason


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_aggregates(value):
    with pytest.raises(ValueError):
        AggregateEvidence(week_other_worked_hours=value)


def test_invalid_break_sequence(policy):
    for events in [
        [("in", 9, 0), ("break_end", 13, 0), ("out", 18, 0)],
        [("in", 9, 0), ("out", 12, 0), ("break_start", 13, 0), ("break_end", 14, 0)],
    ]:
        assert not checks(completed(events), policy)[ExceptionCode.MEAL_BREAK_BREACH].passed


def test_wrong_policy_and_simultaneous_events_block(policy):
    retired = policy.model_copy(update={"status": "retired"})
    assert not any(c.passed for c in evaluate_rules(completed(), retired))
    assert not any(
        c.passed for c in evaluate_rules(completed([("in", 9, 0), ("out", 9, 0)]), policy)
    )


def test_overnight_and_dst_use_elapsed_instants(policy):
    case = completed()
    data = case.model_dump()
    # Overnight shift with the same elapsed durations and genuine observed break.
    for punch in data["punches"]:
        punch["ts"] += timedelta(hours=13)
    data["schedule"]["start"] += timedelta(hours=13)
    data["schedule"]["end"] += timedelta(hours=13)
    assert all(c.passed for c in checks(CaseContext.model_validate(data), policy).values())
    from zoneinfo import ZoneInfo

    from app.rules.engine import hours

    zone = ZoneInfo("America/New_York")
    assert hours(datetime(2026, 11, 1, 0, tzinfo=zone), datetime(2026, 11, 1, 3, tzinfo=zone)) == 4


def test_validator_reuses_engine_and_keeps_originals(policy):
    case = completed([("in", 9, 0), ("break_start", 13, 0), ("break_end", 14, 0)])
    original = case.model_dump_json()
    action = ProposedAction(
        type=ActionType.ADD_PUNCH, punch_type=PunchType.OUT, new_ts=case.schedule.end
    )
    result = validate_correction(case, [action], policy)
    assert not result.passed  # no trusted aggregate evidence in shared context yet
    assert next(c for c in result.checks if c.code == ExceptionCode.MISSING_PUNCH).passed
    assert not next(c for c in result.checks if c.code == ExceptionCode.OVERTIME_RISK).passed
    assert case.model_dump_json() == original


@pytest.mark.parametrize("offset", [1, 30, 31, 1440])
def test_validator_rejects_unproven_times_even_inside_window(offset, policy):
    case = make_case()
    action = ProposedAction(
        type=ActionType.ADD_PUNCH,
        punch_type=PunchType.OUT,
        new_ts=case.schedule.end + timedelta(minutes=offset),
    )
    result = validate_correction(case, [action], policy)
    assert not result.passed
    assert not any(c.passed for c in result.checks)


def test_already_resolved_and_break_actions_rejected(policy):
    case = completed()
    for kind in [PunchType.OUT, PunchType.BREAK_END]:
        result = validate_correction(
            case,
            [ProposedAction(type=ActionType.ADD_PUNCH, punch_type=kind, new_ts=case.schedule.end)],
            policy,
        )
        assert not any(c.passed for c in result.checks)


def test_offset_equivalence(policy):
    case = completed()
    converted = CaseContext.model_validate(
        {
            **case.model_dump(),
            "punches": [p.model_copy(update={"ts": p.ts.astimezone(UTC)}) for p in case.punches],
        }
    )
    assert checks(case, policy) == checks(converted, policy)
