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


# ------------------------------------------------------------------ overtime remainder (agreed)


def test_evidenced_fix_leaving_only_overtime_is_reviewable(policy):
    # A spread-over fixed to the stated 06:30 still has 10 h worked of 9 (live demo).
    from app.core.contracts import EvidenceKind, EvidenceRef

    base = make_case(notes=("I only started at 06:30 when the gate opened.",))
    shift = base.schedule.model_copy(
        update={
            "start": datetime(2026, 11, 12, 6, 30, tzinfo=IST),
            "end": datetime(2026, 11, 12, 18, 30, tzinfo=IST),
            "planned_break_min": 120,
        }
    )
    case = base.model_copy(
        update={
            "code": ExceptionCode.SPREAD_OVER_BREACH,
            "severity": "problem",
            "schedule": shift,
            "as_of": datetime(2026, 11, 13, 12, tzinfo=IST),
            "punches": [  # two proper rests, so only the 10 h of work remains (> 9 h)
                _punch("P-1", IN, 6, 0),
                _punch("x", BS, 11, 0),
                _punch("y", BE, 12, 0),
                _punch("x2", BS, 15, 30),
                _punch("y2", BE, 16, 30),
                _punch("P-2", OUT, 18, 30),
            ],
        }
    )
    fix = ProposedAction(
        type="adjust_punch",
        punch_id="P-1",
        new_ts=datetime(2026, 11, 12, 6, 30, tzinfo=IST),
        evidence_ref=EvidenceRef(kind=EvidenceKind.NOTE, id="N-0"),
    )
    result = make_validator(lambda c: TOTALS)(case, [fix], policy)
    failed = {c.code: c for c in result.checks if not c.passed}
    assert set(failed) == {ExceptionCode.OVERTIME_RISK}
    assert failed[ExceptionCode.OVERTIME_RISK].outcome == RuleOutcome.INSUFFICIENT_EVIDENCE
    assert "manager review" in failed[ExceptionCode.OVERTIME_RISK].reason


def test_evidenced_fix_leaving_several_warnings_is_reviewable(policy):
    # Live demo: the stated 06:30 start is also 30 min after the scheduled 06:00, so overtime
    # AND a late start remain. Both are warnings, so the manager reviews it.
    from app.core.contracts import EvidenceKind, EvidenceRef

    base = make_case(notes=("I only started at 06:30 when the gate opened.",))
    shift = base.schedule.model_copy(
        update={
            "start": datetime(2026, 11, 12, 6, 0, tzinfo=IST),
            "end": datetime(2026, 11, 12, 18, 30, tzinfo=IST),
            "planned_break_min": 120,
        }
    )
    case = base.model_copy(
        update={
            "code": ExceptionCode.SPREAD_OVER_BREACH,
            "severity": "problem",
            "schedule": shift,
            "as_of": datetime(2026, 11, 13, 12, tzinfo=IST),
            "punches": [
                _punch("P-1", IN, 6, 0),
                _punch("x", BS, 11, 0),
                _punch("y", BE, 12, 0),
                _punch("x2", BS, 15, 30),
                _punch("y2", BE, 16, 30),
                _punch("P-2", OUT, 18, 30),
            ],
        }
    )
    fix = ProposedAction(
        type="adjust_punch",
        punch_id="P-1",
        new_ts=datetime(2026, 11, 12, 6, 30, tzinfo=IST),
        evidence_ref=EvidenceRef(kind=EvidenceKind.NOTE, id="N-0"),
    )
    result = make_validator(lambda c: TOTALS)(case, [fix], policy)
    failed = {c.code: c.outcome for c in result.checks if not c.passed}
    assert failed == {
        ExceptionCode.OVERTIME_RISK: RuleOutcome.INSUFFICIENT_EVIDENCE,
        ExceptionCode.SCHEDULE_DEVIATION: RuleOutcome.INSUFFICIENT_EVIDENCE,
    }


def test_a_problem_remainder_still_blocks_even_with_warnings(policy):
    # The fix leaves a problem-severity failure (spread still 13.5 h): it must keep blocking.
    from app.core.contracts import EvidenceKind, EvidenceRef

    base = make_case(notes=("I only started at 06:30.",))
    case = base.model_copy(
        update={
            "code": ExceptionCode.SPREAD_OVER_BREACH,
            "severity": "problem",
            "as_of": datetime(2026, 11, 13, 12, tzinfo=IST),
            "punches": [_punch("P-1", IN, 6, 0), _punch("P-2", OUT, 20, 0)],  # 14 h spread
        }
    )
    fix = ProposedAction(
        type="adjust_punch",
        punch_id="P-1",
        new_ts=datetime(2026, 11, 12, 6, 30, tzinfo=IST),
        evidence_ref=EvidenceRef(kind=EvidenceKind.NOTE, id="N-0"),
    )
    result = make_validator(lambda c: TOTALS)(case, [fix], policy)
    outcomes = {c.code: c.outcome for c in result.checks if not c.passed}
    # 06:30-20:00 is still 13.5 h of spread (problem): nothing becomes reviewable.
    assert outcomes[ExceptionCode.SPREAD_OVER_BREACH] == RuleOutcome.VIOLATION
    assert RuleOutcome.VIOLATION in set(outcomes.values())
