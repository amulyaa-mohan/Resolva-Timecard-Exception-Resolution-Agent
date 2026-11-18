"""Real validator with a trusted aggregate source: eligibility, boundaries and failure modes."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.contracts import (
    ActionType,
    CaseContext,
    ExceptionCode,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
    ScheduledShift,
)
from app.rules.engine import AggregateEvidence, evaluate_rules
from app.rules.validator import make_validator, validate_correction
from tests.factories import IST, make_case

COMPLETE = dict(
    work_date_complete=True,
    week_other_worked_hours=0,
    week_remaining_scheduled_hours=0,
    quarter_other_overtime_hours=0,
    week_start=date(2026, 11, 9),
    quarter_start=date(2026, 10, 1),
    as_of=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
)


def aggregates(**overrides):
    return AggregateEvidence(**{**COMPLETE, **overrides})


def missing_out(start=None, end=None, events=None, tz="Asia/Kolkata", jurisdiction="IN-KA"):
    """A case whose only defect is a missing clock-out. Times are (kind, aware datetime)."""
    base = make_case()
    zone = IST if tz == "Asia/Kolkata" else ZoneInfo(tz)
    start = start or datetime(2026, 11, 12, 9, 0, tzinfo=zone)
    end = end or datetime(2026, 11, 12, 18, 0, tzinfo=zone)
    if events is None:
        events = [
            ("in", start),
            ("break_start", start + timedelta(hours=4)),
            ("break_end", start + timedelta(hours=5)),
        ]
    punches = [
        PunchRecord(
            punch_id=f"P-{i}", employee_id="E-001", ts=ts, type=kind, source=PunchSource.KIOSK
        )
        for i, (kind, ts) in enumerate(events)
    ]
    data = base.model_dump()
    data.update(
        punches=[p.model_dump() for p in punches],
        work_date=start.astimezone(zone).date(),
        schedule=ScheduledShift(
            shift_id="S-1", employee_id="E-001", start=start, end=end, planned_break_min=60
        ).model_dump(),
    )
    data["employee"].update(timezone=tz, jurisdiction=jurisdiction)
    return CaseContext.model_validate(data)


def add(kind, ts, **extra):
    return ProposedAction(type=ActionType.ADD_PUNCH, punch_type=kind, new_ts=ts, **extra)


def by_code(result):
    return {c.code: c for c in result.checks}


def test_fully_evidenced_correction_passes_all_six(policy):
    case = missing_out()
    result = make_validator(lambda _: aggregates())(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    assert result.passed and len(result.checks) == 6
    assert all(c.passed for c in result.checks)


def test_default_validator_still_fails_closed_on_overtime_only(policy):
    case = missing_out()
    result = validate_correction(case, [add(PunchType.OUT, case.schedule.end)], policy)
    failed = [c.code for c in result.checks if not c.passed]
    assert not result.passed and failed == [ExceptionCode.OVERTIME_RISK]
    assert "incomplete" in by_code(result)[ExceptionCode.OVERTIME_RISK].reason


@pytest.mark.parametrize(
    "source,needle",
    [
        (lambda _: None, "incomplete"),
        (lambda _: aggregates(work_date_complete=False), "incomplete"),
        (lambda _: aggregates(week_remaining_scheduled_hours=None), "incomplete"),
        (lambda _: aggregates(quarter_other_overtime_hours=None), "incomplete"),
    ],
)
def test_missing_aggregate_evidence_is_not_zero(source, needle, policy):
    case = missing_out()
    result = make_validator(source)(case, [add(PunchType.OUT, case.schedule.end)], policy)
    overtime = by_code(result)[ExceptionCode.OVERTIME_RISK]
    assert not result.passed and not overtime.passed and needle in overtime.reason


def test_aggregate_source_failure_or_wrong_type_blocks_everything(policy):
    case = missing_out()
    action = [add(PunchType.OUT, case.schedule.end)]

    def broken(_):
        raise RuntimeError("db down")

    for source in (broken, lambda _: {"week_other_worked_hours": 0}):
        result = make_validator(source)(case, action, policy)
        assert not result.passed and not any(c.passed for c in result.checks)
    assert "unavailable" in make_validator(broken)(case, action, policy).checks[0].reason


@pytest.mark.parametrize(
    "week_other,quarter_other,ok",
    [
        (40, 0, True),  # 8 h today + 40 = 48: exactly the weekly limit is allowed
        (40.01, 0, False),  # adjacent: one more second-scale fraction exceeds it
        (0, 50, True),  # quarter cap reached but not exceeded (no overtime today)
        (0, 50.01, False),
    ],
)
def test_weekly_and_quarterly_boundaries_after_correction(week_other, quarter_other, ok, policy):
    case = missing_out()
    source = lambda _: aggregates(  # noqa: E731
        week_other_worked_hours=week_other, quarter_other_overtime_hours=quarter_other
    )
    result = make_validator(source)(case, [add(PunchType.OUT, case.schedule.end)], policy)
    assert result.passed is ok
    if not ok:
        failed = [c.code for c in result.checks if not c.passed]
        assert failed == [ExceptionCode.OVERTIME_RISK]
        assert by_code(result)[ExceptionCode.MISSING_PUNCH].passed


def test_correction_that_resolves_pairing_but_creates_meal_break_violation(policy):
    start = datetime(2026, 11, 12, 9, 0, tzinfo=IST)
    case = missing_out(events=[("in", start)])  # no break recorded
    result = make_validator(lambda _: aggregates())(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    codes = by_code(result)
    assert not result.passed
    assert codes[ExceptionCode.MISSING_PUNCH].passed
    assert not codes[ExceptionCode.MEAL_BREAK_BREACH].passed
    # 9:00-18:00 unbroken is 9 h net: exactly the inclusive daily limit, so only the break fails.
    assert codes[ExceptionCode.OVERTIME_RISK].passed
    assert [c for c, v in codes.items() if not v.passed] == [ExceptionCode.MEAL_BREAK_BREACH]


def test_detection_and_validation_use_identical_checks(policy):
    case = missing_out()
    source = lambda _: aggregates(week_other_worked_hours=12.5)  # noqa: E731
    result = make_validator(source)(case, [add(PunchType.OUT, case.schedule.end)], policy)
    manual = CaseContext.model_validate(
        {
            **case.model_dump(),
            "punches": [
                *case.model_dump()["punches"],
                PunchRecord(
                    punch_id="detected-out",
                    employee_id="E-001",
                    ts=case.schedule.end,
                    type=PunchType.OUT,
                    source=PunchSource.KIOSK,
                ).model_dump(),
            ],
        }
    )
    assert result.checks == evaluate_rules(manual, policy, source(case))


def test_raw_evidence_is_not_mutated(policy):
    case = missing_out()
    snapshot = case.model_dump_json()
    make_validator(lambda _: aggregates())(case, [add(PunchType.OUT, case.schedule.end)], policy)
    assert case.model_dump_json() == snapshot and len(case.punches) == 3


def test_overnight_shift_validates_on_shift_start_date(policy):
    start = datetime(2026, 11, 12, 22, 0, tzinfo=IST)
    case = missing_out(start=start, end=start + timedelta(hours=8))
    result = make_validator(lambda _: aggregates())(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    assert result.passed, [c.reason for c in result.checks if not c.passed]


def test_local_date_differs_from_utc_date(policy):
    # 00:30 IST on 12 Nov is 19:00 UTC on 11 Nov; the local date governs scope.
    start = datetime(2026, 11, 11, 19, 0, tzinfo=UTC)
    case = missing_out(start=start, end=start + timedelta(hours=8))
    assert case.work_date.isoformat() == "2026-11-12"
    result = make_validator(lambda _: aggregates())(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    assert result.passed


def test_clock_in_from_another_local_date_blocks(policy):
    start = datetime(2026, 11, 12, 9, 0, tzinfo=IST)
    stray = datetime(2026, 11, 11, 23, 0, tzinfo=IST)
    case = missing_out(
        events=[("in", stray), ("out", stray + timedelta(minutes=30)), ("in", start)]
    )
    result = make_validator(lambda _: aggregates())(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    assert not result.passed and not any(c.passed for c in result.checks)
    assert "work date" in result.checks[0].reason


def test_dst_fall_back_uses_elapsed_hours(registry):
    us = registry.get("US-FED", "2025.1")  # 8 h daily, 30 min meal before 5 h
    zone = ZoneInfo("America/New_York")
    start = datetime(2026, 10, 31, 22, 0, tzinfo=zone)
    end = datetime(2026, 11, 1, 5, 0, tzinfo=zone)  # 8 elapsed hours across fall-back
    events = [
        ("in", start),
        ("break_start", start + timedelta(hours=4)),
        ("break_end", start + timedelta(hours=4, minutes=30)),
    ]
    case = missing_out(
        start=start, end=end, events=events, tz="America/New_York", jurisdiction="US-FED"
    )
    week = dict(week_start=date(2026, 10, 26), quarter_start=None)
    ok = make_validator(lambda _: aggregates(quarter_other_overtime_hours=None, **week))
    result = ok(case, [add(PunchType.OUT, end)], us)
    # 8 h elapsed minus 30 min break = 7.5 h: wall-clock (7 h) would understate it.
    assert result.passed, [c.reason for c in result.checks if not c.passed]
    later = make_validator(lambda _: aggregates(week_other_worked_hours=32.51, **week))
    assert not later(case, [add(PunchType.OUT, end)], us).passed


@pytest.mark.parametrize(
    "actions,needle",
    [
        ("none", "one missing-punch action"),
        ("two", "one missing-punch action"),
        ("adjust", "clock-in/clock-out"),
        ("target", "existing punch"),
        ("break", "clock-in/clock-out"),
        ("early", "verified evidence"),
        ("outside", "inference window"),
    ],
)
def test_unsupported_actions_and_invalid_targets(actions, needle, policy):
    case = missing_out()
    end = case.schedule.end
    actions = {
        "none": [],
        "two": [add(PunchType.OUT, end), add(PunchType.OUT, end)],
        "adjust": [ProposedAction(type=ActionType.ADJUST_PUNCH, punch_id="P-0", new_ts=end)],
        "target": [add(PunchType.OUT, end, punch_id="P-0")],
        "break": [add(PunchType.BREAK_END, end)],
        "early": [add(PunchType.OUT, end - timedelta(minutes=3))],
        "outside": [add(PunchType.OUT, end + timedelta(minutes=31))],
    }[actions]
    result = make_validator(lambda _: aggregates())(case, actions, policy)
    assert not result.passed and not any(c.passed for c in result.checks)
    assert needle in result.checks[0].reason


def test_cross_employee_evidence_blocks(policy):
    case = missing_out()
    data = case.model_dump()
    data["punches"][1]["employee_id"] = "E-999"
    tampered = CaseContext.model_validate(data)
    result = make_validator(lambda _: aggregates())(
        tampered, [add(PunchType.OUT, case.schedule.end)], policy
    )
    assert not result.passed and not any(c.passed for c in result.checks)
    assert "cross-employee" in result.checks[0].reason


# ---- Agreed with Track B (2026-11-18): reload per run, record totals, three outcomes.


def test_totals_are_reloaded_on_every_validation(policy):
    case = missing_out()
    action = [add(PunchType.OUT, case.schedule.end)]
    reads = [aggregates(), aggregates(week_other_worked_hours=41)]
    calls = []

    def source(c):
        calls.append(c.exception_id)
        return reads[len(calls) - 1]

    validator = make_validator(source)
    assert validator(case, action, policy).passed  # at proposal time
    assert not validator(case, action, policy).passed  # at approval: totals changed
    assert calls == ["X-1", "X-1"]


def test_reason_records_totals_period_and_as_of(policy):
    case = missing_out()
    result = make_validator(lambda _: aggregates(week_other_worked_hours=12.5))(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    reason = by_code(result)[ExceptionCode.OVERTIME_RISK].reason
    for fragment in (
        "day 8.00 h",
        "2026-11-09",
        "12.50 h other worked",
        "2026-10-01",
        "2026-11-13T06:00:00+00:00",
    ):
        assert fragment in reason


@pytest.mark.parametrize(
    "overrides,needle",
    [
        (dict(week_start=None), "period or as-of"),
        (dict(as_of=None), "period or as-of"),
        (dict(week_start=date(2026, 11, 2)), "different week"),  # last week
        (dict(week_start=date(2026, 11, 13)), "different week"),  # starts after work date
        (dict(quarter_start=date(2026, 7, 1)), "different quarter"),
        (dict(quarter_start=None), "quarterly overtime total missing"),
    ],
)
def test_wrong_or_missing_periods_are_insufficient(overrides, needle, policy):
    case = missing_out()
    result = make_validator(lambda _: aggregates(**overrides))(
        case, [add(PunchType.OUT, case.schedule.end)], policy
    )
    overtime = by_code(result)[ExceptionCode.OVERTIME_RISK]
    assert not result.passed and needle in overtime.reason


def test_week_window_edges(policy):
    # Containment only. Weekday alignment (Friday 6 Nov accepted here) is checked once
    # contract 0.2.0 adds the policy week_start field; update this test then.
    case = missing_out()  # Thursday 2026-11-12
    action = [add(PunchType.OUT, case.schedule.end)]
    for start, ok in [
        (date(2026, 11, 12), True),
        (date(2026, 11, 6), True),
        (date(2026, 11, 5), False),
    ]:
        assert (
            make_validator(lambda _, s=start: aggregates(week_start=s))(case, action, policy).passed
            is ok
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(as_of=datetime(2026, 11, 13, 6, 0)),  # naive
        dict(quarter_start=date(2026, 11, 1)),  # not a calendar quarter start
        dict(quarter_start=date(2026, 10, 2)),
    ],
)
def test_invalid_aggregate_metadata_rejected(kwargs):
    with pytest.raises(ValueError):
        aggregates(**kwargs)


def outcomes(case, policy, agg=None):
    from app.rules.engine import evaluate_rule_outcomes

    return {c.code: o for c, o in evaluate_rule_outcomes(case, policy, agg)}


def test_outcomes_distinguish_violation_from_insufficient_evidence(policy):
    from app.rules.engine import Outcome

    unpaired = outcomes(missing_out(), policy, aggregates())
    assert unpaired[ExceptionCode.MISSING_PUNCH] == Outcome.VIOLATION
    assert {o for c, o in unpaired.items() if c != ExceptionCode.MISSING_PUNCH} == {
        Outcome.INSUFFICIENT_EVIDENCE
    }
    start = datetime(2026, 11, 12, 9, 0, tzinfo=IST)
    no_break = missing_out(events=[("in", start), ("out", start + timedelta(hours=9))])
    got = outcomes(no_break, policy, aggregates())
    assert got[ExceptionCode.MEAL_BREAK_BREACH] == Outcome.VIOLATION
    assert got[ExceptionCode.MISSING_PUNCH] == Outcome.PASS
    assert outcomes(no_break, policy)[ExceptionCode.OVERTIME_RISK] == (
        Outcome.INSUFFICIENT_EVIDENCE
    )
    late = missing_out(
        events=[("in", start + timedelta(minutes=8)), ("out", start + timedelta(hours=4))]
    )
    assert outcomes(late, policy, aggregates())[ExceptionCode.SCHEDULE_DEVIATION] == (
        Outcome.VIOLATION
    )


def test_passed_always_matches_outcome(policy):
    from app.rules.engine import Outcome, evaluate_rule_outcomes

    start = datetime(2026, 11, 12, 9, 0, tzinfo=IST)
    cases = [
        missing_out(),
        missing_out(events=[("in", start), ("out", start + timedelta(hours=13))]),
        missing_out(events=[("in", start), ("in", start + timedelta(hours=1))]),
    ]
    for case in cases:
        for agg in (None, aggregates()):
            for check, outcome in evaluate_rule_outcomes(case, policy, agg):
                assert check.passed == (outcome == Outcome.PASS)
