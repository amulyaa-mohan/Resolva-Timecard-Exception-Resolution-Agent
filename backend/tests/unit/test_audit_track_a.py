"""Regression tests for the Track A findings of the 2026-11-18 backend audit (A1, A4-A6).

Fixed by Track B with the repository owner's authorisation; see docs/shared/AUDIT_2026-11-18.md.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.contracts import (
    ActionType,
    ExceptionCode,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
    RuleOutcome,
)
from app.rules.engine import AggregateEvidence, evaluate_rule_outcomes
from app.rules.validator import make_validator
from tests.factories import IST, make_case

TOTALS = AggregateEvidence(
    work_date_complete=True,
    week_other_worked_hours=16,
    week_remaining_scheduled_hours=8,
    quarter_other_overtime_hours=0,
    week_start=date(2026, 11, 9),
    quarter_start=date(2026, 10, 1),
    as_of=datetime(2026, 11, 13, 12, tzinfo=IST),
)
IN, OUT, BS, BE = PunchType.IN, PunchType.OUT, PunchType.BREAK_START, PunchType.BREAK_END


def _punch(pid, kind, h, m):
    return PunchRecord(
        punch_id=pid,
        employee_id="E-001",
        ts=datetime(2026, 11, 12, h, m, tzinfo=IST),
        type=kind,
        source=PunchSource.KIOSK,
    )


def outcomes(punches, policy, **update):
    case = make_case().model_copy(
        update={"punches": punches, "as_of": datetime(2026, 11, 13, 12, tzinfo=IST), **update}
    )
    return {c.code: o for c, o in evaluate_rule_outcomes(case, policy, TOTALS)}


# ------------------------------------------------------------------ A1 meal-break loophole


@pytest.mark.parametrize(
    ("label", "punches", "expected"),
    [
        ("no break", [("a", IN, 9, 0), ("b", OUT, 18, 0)], RuleOutcome.VIOLATION),
        (
            "60-min break",
            [("a", IN, 9, 0), ("x", BS, 13, 0), ("y", BE, 14, 0), ("b", OUT, 18, 0)],
            RuleOutcome.PASS,
        ),
        (
            "1-min clock-out/in split (the loophole)",
            [("a", IN, 9, 0), ("b", OUT, 13, 0), ("c", IN, 13, 1), ("d", OUT, 18, 0)],
            RuleOutcome.VIOLATION,
        ),
        (
            "59-min split is still too short",
            [("a", IN, 9, 0), ("b", OUT, 13, 0), ("c", IN, 13, 59), ("d", OUT, 18, 0)],
            RuleOutcome.VIOLATION,
        ),
        (
            "60-min clock-out/in split is a real rest",
            [("a", IN, 9, 0), ("b", OUT, 13, 0), ("c", IN, 14, 0), ("d", OUT, 18, 0)],
            RuleOutcome.PASS,
        ),
        (
            "short day split by a short gap stays under 5 h",
            [("a", IN, 9, 0), ("b", OUT, 11, 0), ("c", IN, 11, 5), ("d", OUT, 13, 30)],
            RuleOutcome.PASS,
        ),
    ],
)
def test_a1_gap_between_sessions_counts_as_rest_only_when_long_enough(
    label, punches, expected, policy
):
    built = [_punch(*p) for p in punches]
    assert outcomes(built, policy)[ExceptionCode.MEAL_BREAK_BREACH] == expected, label


# ------------------------------------------------------------------ A4 unsupported fix types


@pytest.mark.parametrize(
    ("code", "action_type"),
    [
        (ExceptionCode.MEAL_BREAK_BREACH, ActionType.ADD_BREAK),
        (ExceptionCode.MEAL_BREAK_BREACH, ActionType.FLAG_PREMIUM),
        (ExceptionCode.OVERTIME_RISK, ActionType.ACKNOWLEDGE),
    ],
)
def test_a4_unsupported_fix_types_escalate_instead_of_block(code, action_type, policy):
    case = make_case().model_copy(update={"code": code})
    action = ProposedAction(type=action_type)
    result = make_validator(lambda c: TOTALS)(case, [action], policy)
    assert not result.passed
    assert {c.outcome for c in result.checks} == {RuleOutcome.INSUFFICIENT_EVIDENCE}
    assert "not supported yet" in result.checks[0].reason


# ------------------------------------------------------------------ A5 schedule deviations


@pytest.mark.parametrize(
    ("label", "first_in", "last_out", "expected"),
    [
        ("on time", (9, 0), (18, 0), RuleOutcome.PASS),
        ("late arrival 20 min", (9, 20), (18, 0), RuleOutcome.VIOLATION),
        ("early departure 20 min", (9, 0), (17, 40), RuleOutcome.VIOLATION),
        ("early arrival 20 min is not a deviation", (8, 40), (18, 0), RuleOutcome.PASS),
        ("late departure 20 min is not a deviation", (9, 0), (18, 20), RuleOutcome.PASS),
        ("late within tolerance (7 min)", (9, 7), (18, 0), RuleOutcome.PASS),
    ],
)
def test_a5_only_late_arrival_and_early_departure_deviate(
    label, first_in, last_out, expected, policy
):
    punches = [
        _punch("a", IN, *first_in),
        _punch("x", BS, 13, 0),
        _punch("y", BE, 14, 0),
        _punch("b", OUT, *last_out),
    ]
    assert outcomes(punches, policy)[ExceptionCode.SCHEDULE_DEVIATION] == expected, label


# ------------------------------------------------------------------ A6 policy end date


def test_a6_effective_to_is_exclusive_like_the_registry(policy):
    punches = [_punch("a", IN, 9, 0), _punch("x", BS, 13, 0), _punch("y", BE, 14, 0)]
    punches.append(_punch("b", OUT, 18, 0))
    work_date = make_case().work_date
    ending_today = policy.model_copy(update={"effective_to": work_date})
    ending_tomorrow = policy.model_copy(update={"effective_to": work_date + timedelta(days=1)})
    blocked = outcomes(punches, ending_today)
    assert set(blocked.values()) == {RuleOutcome.INSUFFICIENT_EVIDENCE}
    assert outcomes(punches, ending_tomorrow)[ExceptionCode.MISSING_PUNCH] == RuleOutcome.PASS
