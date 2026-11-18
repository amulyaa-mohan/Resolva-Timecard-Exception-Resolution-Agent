"""Track A adoption of contract 0.2.0: outcomes, evidence_ref tolerance, as_of, policy calendar."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.attendance.context import CaseService, build_verified_case
from app.core.contracts import (
    ActionType,
    CaseContext,
    EmployeeNote,
    EvidenceKind,
    EvidenceRef,
    ExceptionCode,
    PolicySnapshot,
    ProposedAction,
    PunchRecord,
    PunchSource,
    PunchType,
    RuleOutcome,
)
from app.resolution import totals
from app.rules.engine import AggregateEvidence, evaluate_rules
from app.rules.validator import make_validator, validate_correction
from tests.factories import IST, make_case

TOTALS = AggregateEvidence(
    work_date_complete=True,
    week_other_worked_hours=0,
    week_remaining_scheduled_hours=0,
    quarter_other_overtime_hours=0,
    week_start=date(2026, 11, 9),
    quarter_start=date(2026, 10, 1),
    as_of=datetime(2026, 11, 13, tzinfo=UTC),
)
validator = make_validator(lambda _: TOTALS)


def case_with(*, notes=(), history=(), as_of=None) -> CaseContext:
    data = make_case().model_dump()
    data["punches"] = [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id="E-001",
            ts=datetime(2026, 11, 12, h, 0, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, h) in enumerate([("in", 9), ("break_start", 13), ("break_end", 14)])
    ]
    data["notes"] = [
        EmployeeNote(note_id=f"N-{i}", text=t, submitted_at=datetime(2026, 11, 13, tzinfo=IST))
        for i, t in enumerate(notes)
    ]
    data["punch_history"] = [p.model_dump() for p in history]
    data["as_of"] = as_of
    return CaseContext.model_validate(data)


def out_at(hour, minute, ref=None):
    return ProposedAction(
        type=ActionType.ADD_PUNCH,
        punch_type=PunchType.OUT,
        new_ts=datetime(2026, 11, 12, hour, minute, tzinfo=IST),
        evidence_ref=ref,
    )


def outcomes(result):
    return {c.code: c.outcome for c in result.checks}


# ---- outcome on every RuleCheck


def test_outcome_is_set_and_matches_passed(policy):
    for check in validate_correction(case_with(), [out_at(18, 0)], policy).checks:
        assert check.passed == (check.outcome == RuleOutcome.PASS)
    result = validate_correction(case_with(), [out_at(18, 0)], policy)
    assert outcomes(result)[ExceptionCode.OVERTIME_RISK] == RuleOutcome.INSUFFICIENT_EVIDENCE
    assert outcomes(result)[ExceptionCode.MISSING_PUNCH] == RuleOutcome.PASS


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda d: d.update(schedule=None), RuleOutcome.INSUFFICIENT_EVIDENCE),
        (
            lambda d: d.update(code=ExceptionCode.OVERTIME_RISK, severity="warning"),
            RuleOutcome.VIOLATION,
        ),  # unsupported correction type stays a violation
    ],
)
def test_validator_rejections_carry_the_right_outcome(mutate, expected, policy):
    data = case_with().model_dump()
    mutate(data)
    result = validator(CaseContext.model_validate(data), [out_at(18, 0)], policy)
    assert {c.outcome for c in result.checks} == {expected}


def test_inactive_policy_is_insufficient_evidence(policy):
    retired = PolicySnapshot.model_validate({**policy.model_dump(), "status": "retired"})
    checks = evaluate_rules(case_with(), retired, TOTALS)
    assert {c.outcome for c in checks} == {RuleOutcome.INSUFFICIENT_EVIDENCE}


# ---- evidence_ref and evidence_tolerance_min


def schedule_end(shift="S-1"):
    return EvidenceRef(kind=EvidenceKind.SCHEDULE_END, id=shift)


@pytest.mark.parametrize(
    "minute,ref,ok",
    [
        (0, None, True),  # exact schedule time needs no ref
        (3, None, False),  # strict without a ref
        (5, schedule_end(), True),  # exactly evidence_tolerance_min (5)
        (6, schedule_end(), False),  # one minute over
        (3, schedule_end("S-OTHER"), False),  # ref to another shift
        (3, EvidenceRef(kind=EvidenceKind.SCHEDULE_START, id="S-1"), False),  # wrong boundary
    ],
)
def test_schedule_ref_tolerance(minute, ref, ok, policy):
    assert validator(case_with(), [out_at(18, minute, ref)], policy).passed is ok


@pytest.mark.parametrize(
    "note,minute,ok",
    [
        ("I left at 6:05 pm, forgot to punch out", 5, True),
        ("I left at 18:06", 2, True),  # 4 min from the stated time
        ("I left at 18:06", 0, False),  # 6 min from the note it cites (schedule ref would pass)
        ("I left at 18:06", 12, False),  # 6 min from the stated time
        ("I left a bit late", 5, False),  # no stated time
    ],
)
def test_note_ref(note, minute, ok, policy):
    case = case_with(notes=(note,))
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    assert validator(case, [out_at(18, minute, ref)], policy).passed is ok


def test_unknown_note_ref_blocked(policy):
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-404")
    result = validator(case_with(notes=("left at 18:10",)), [out_at(18, 10, ref)], policy)
    assert not result.passed and "does not resolve" in result.checks[0].reason


def history_punch(punch_id, day, kind="out", hour=18, minute=8):
    return PunchRecord(
        punch_id=punch_id,
        employee_id="E-001",
        ts=datetime(2026, 11, day, hour, minute, tzinfo=IST),  # default 18:08
        type=kind,
        source=PunchSource.KIOSK,
    )


@pytest.mark.parametrize(
    "punch,ok",
    [
        (history_punch("H-1", 5), True),  # previous Thursday, clock-out at 18:08
        (history_punch("H-1", 4), False),  # a Wednesday: not the same weekday
        (history_punch("H-1", 5, kind="in"), False),  # a clock-in cannot anchor a clock-out
    ],
)
def test_history_ref(punch, ok, policy):
    case = case_with(history=(punch,))
    ref = EvidenceRef(kind=EvidenceKind.HISTORY_PUNCH, id="H-1")
    assert validator(case, [out_at(18, 5, ref)], policy).passed is ok  # 3 min from 18:08


def test_evidenced_late_clock_out_still_flags_schedule_deviation(policy):
    # The note supports 18:10, but 10 min past the shift end exceeds late_tolerance_min (7):
    # the fix would introduce a schedule deviation, so it is not eligible as-is.
    case = case_with(notes=("I left at 18:10",))
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    result = validator(case, [out_at(18, 10, ref)], policy)
    failed = {c.code: c.outcome for c in result.checks if not c.passed}
    assert failed == {ExceptionCode.SCHEDULE_DEVIATION: RuleOutcome.VIOLATION}


def test_ref_still_bounded_by_inference_window(policy):
    case = case_with(notes=("left at 18:40",))  # outside the 30 min missing-punch window
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    result = validator(case, [out_at(18, 40, ref)], policy)
    assert not result.passed and "inference window" in result.checks[0].reason


# ---- as_of


def test_punch_after_as_of_is_a_violation(policy):
    case = case_with(as_of=datetime(2026, 11, 12, 17, 0, tzinfo=IST))
    result = validator(case, [out_at(18, 0)], policy)
    assert not result.passed and "as_of" in result.checks[0].reason
    assert {c.outcome for c in result.checks} == {RuleOutcome.VIOLATION}


def test_open_shift_is_not_yet_missing(policy):
    still_running = case_with(as_of=datetime(2026, 11, 12, 17, 0, tzinfo=IST))
    after_end = case_with(as_of=datetime(2026, 11, 12, 18, 30, tzinfo=IST))
    open_check = evaluate_rules(still_running, policy, TOTALS)[0]
    late_check = evaluate_rules(after_end, policy, TOTALS)[0]
    assert open_check.code == ExceptionCode.MISSING_PUNCH
    assert open_check.outcome == RuleOutcome.INSUFFICIENT_EVIDENCE
    assert late_check.outcome == RuleOutcome.VIOLATION
    assert evaluate_rules(case_with(), policy, TOTALS)[0].outcome == RuleOutcome.VIOLATION


def test_as_of_is_not_part_of_evidence_version():
    plain = build_verified_case(case_with(), correction_revision=0)
    timed = build_verified_case(
        case_with(as_of=datetime(2026, 11, 13, tzinfo=UTC)), correction_revision=0
    )
    assert plain.evidence_version == timed.evidence_version


def test_case_service_sets_server_as_of():
    now = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)

    class Repo:
        def load_for_manager(self, exception_id, manager_id):
            return case_with(as_of=datetime(1999, 1, 1, tzinfo=UTC)), 0  # ignored

    built = CaseService(Repo(), clock=lambda: now).build_case_context("X-1", manager_id="M-1")
    assert built.as_of == now


# ---- policy calendar


@pytest.mark.parametrize(
    "day,start_weekday,expected",
    [
        (date(2026, 11, 12), 0, date(2026, 11, 9)),  # Monday weeks
        (date(2026, 11, 12), 6, date(2026, 11, 8)),  # Sunday weeks
        (date(2026, 11, 8), 6, date(2026, 11, 8)),  # the start day itself
    ],
)
def test_policy_week_start(day, start_weekday, expected):
    assert totals.week_start(day, start_weekday) == expected


@pytest.mark.parametrize(
    "day,start_month,bounds",
    [
        (date(2026, 11, 12), 1, (date(2026, 10, 1), date(2027, 1, 1))),
        (date(2026, 3, 31), 1, (date(2026, 1, 1), date(2026, 4, 1))),
        (date(2026, 1, 15), 2, (date(2025, 11, 1), date(2026, 2, 1))),  # Feb/May/Aug/Nov
        (date(2026, 4, 1), 4, (date(2026, 4, 1), date(2026, 7, 1))),
    ],
)
def test_policy_quarter_bounds(day, start_month, bounds):
    assert totals.quarter_bounds(day, start_month) == bounds


def test_week_start_comes_from_policy(policy):
    sunday_policy = PolicySnapshot.model_validate(
        {**policy.model_dump(), "rules": {**policy.rules.model_dump(), "week_start": "sunday"}}
    )
    case = case_with()
    monday_totals = validator(case, [out_at(18, 0)], sunday_policy)
    assert not monday_totals.passed
    sunday = make_validator(
        lambda _: AggregateEvidence(**{**TOTALS.__dict__, "week_start": date(2026, 11, 8)})
    )
    assert sunday(case, [out_at(18, 0)], sunday_policy).passed
    assert timedelta(0) <= case.work_date - date(2026, 11, 8) < timedelta(days=7)
