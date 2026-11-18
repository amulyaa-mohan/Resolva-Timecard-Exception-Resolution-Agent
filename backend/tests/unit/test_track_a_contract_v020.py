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
        ("I left at 18:06", 12, False),  # 6 min past the stated time, and it would add pay
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


def test_evidenced_early_departure_is_referred_to_the_manager(policy):
    # The note supports 17:50, 10 min before the shift end (tolerance 7). The fix is
    # evidenced and its only remainder is a warning, so it escalates rather than blocking.
    case = case_with(notes=("I left at 17:50",))
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    result = validator(case, [out_at(17, 50, ref)], policy)
    failed = {c.code: c.outcome for c in result.checks if not c.passed}
    assert not result.passed
    assert failed == {ExceptionCode.SCHEDULE_DEVIATION: RuleOutcome.INSUFFICIENT_EVIDENCE}


def test_evidenced_late_clock_out_is_not_a_deviation(policy):
    # Audit A5: policy KA-9 defines deviations as late arrival / early departure only;
    # staying 10 min longer is extra time for OVERTIME_RISK, not a schedule deviation.
    case = case_with(notes=("I left at 18:10",))
    ref = EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    result = validator(case, [out_at(18, 10, ref)], policy)
    assert result.passed, [c.reason for c in result.checks if not c.passed]


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


# ---- adjust_punch (item 7) and unsupported action types


def complete_day(events, code, notes=()):
    data = case_with(notes=notes).model_dump()
    data["punches"] = [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id="E-001",
            ts=datetime(2026, 11, 12, h, m, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, h, m) in enumerate(events)
    ]
    data["code"] = code
    data["severity"] = "problem" if code == ExceptionCode.SPREAD_OVER_BREACH else "warning"
    return CaseContext.model_validate(data)


DAY = [("in", 9, 0), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 18, 0)]


def adjust(punch_id, hour, minute, note="N-0"):
    return ProposedAction(
        type=ActionType.ADJUST_PUNCH,
        punch_id=punch_id,
        new_ts=datetime(2026, 11, 12, hour, minute, tzinfo=IST),
        evidence_ref=None if note is None else EvidenceRef(kind=EvidenceKind.NOTE, id=note),
    )


def late_case(note="I actually arrived at 9:05, the kiosk was down"):
    events = [("in", 9, 25), *DAY[1:]]  # recorded 25 min late
    return complete_day(events, ExceptionCode.SCHEDULE_DEVIATION, notes=(note,))


def test_adjust_backed_by_employee_note_resolves(policy):
    result = validator(late_case(), [adjust("P-0", 9, 5)], policy)
    assert result.passed, [c.reason for c in result.checks if not c.passed]


@pytest.mark.parametrize(
    "action,needle",
    [
        (adjust("P-0", 9, 0, note=None), "note evidence_ref"),  # schedule alone is not proof
        (adjust("P-0", 9, 12), "adds no unclaimed paid time"),  # note says 9:05
        (adjust("P-9", 9, 5), "own punches"),  # not in this case
        (adjust("P-0", 9, 5, note="N-404"), "does not resolve"),
        (adjust("P-0", 9, 15), "adds no unclaimed paid time"),  # 10 min from the note
    ],
)
def test_adjust_rejections(action, needle, policy):
    result = validator(late_case(), [action], policy)
    assert not result.passed and needle in result.checks[0].reason
    assert {c.outcome for c in result.checks} == {RuleOutcome.VIOLATION}


def test_adjust_window_and_type_and_duplicates(policy):
    far = late_case("I came in at 8:30")
    assert "further than" in validator(far, [adjust("P-0", 8, 30)], policy).checks[0].reason
    retyped = adjust("P-0", 9, 5).model_copy(update={"punch_type": PunchType.OUT})
    assert "type" in validator(late_case(), [retyped], policy).checks[0].reason
    twice = [adjust("P-0", 9, 5), adjust("P-0", 9, 6)]
    assert "same punch" in validator(late_case(), twice, policy).checks[0].reason


def test_evidenced_fix_leaving_a_warning_goes_to_the_manager(policy):
    # Moving the clock-in still leaves the shift 30 min short at the end. Agreed with Track B:
    # an evidenced fix whose only remainder is a warning escalates instead of blocking.
    events = [("in", 9, 25), ("break_start", 13, 0), ("break_end", 14, 0), ("out", 17, 30)]
    case = complete_day(events, ExceptionCode.SCHEDULE_DEVIATION, notes=("arrived 9:05",))
    result = validator(case, [adjust("P-0", 9, 5)], policy)
    failed = {c.code: c.outcome for c in result.checks if not c.passed}
    assert not result.passed  # still never approvable on its own
    assert failed == {ExceptionCode.SCHEDULE_DEVIATION: RuleOutcome.INSUFFICIENT_EVIDENCE}
    assert "manager review" in next(
        c.reason for c in result.checks if c.code == ExceptionCode.SCHEDULE_DEVIATION
    )
    # A problem-severity remainder still blocks, evidenced or not.
    spread = complete_day(
        [("in", 6, 0), ("break_start", 10, 0), ("break_end", 11, 0), ("out", 18, 30)],
        ExceptionCode.SPREAD_OVER_BREACH,
        notes=("I started at 6:05",),
    )
    blocked = validator(spread, [adjust("P-0", 6, 5)], policy)
    assert blocked.checks[4].outcome == RuleOutcome.VIOLATION


def test_two_adjustments_fix_spread(policy):
    events = [("in", 6, 0), ("break_start", 10, 0), ("break_end", 11, 0), ("out", 18, 20)]
    case = complete_day(
        events, ExceptionCode.SPREAD_OVER_BREACH, notes=("I started at 6:25 and left 18:05",)
    )
    # 6:00-18:20 is 12h20 > 12h; the note's times give 11h40.
    result = validator(case, [adjust("P-0", 6, 25), adjust("P-3", 18, 5)], policy)
    failed = {c.code: c.reason for c in result.checks if not c.passed}
    assert ExceptionCode.SPREAD_OVER_BREACH not in failed  # the targeted rule is fixed
    # The day still has warnings (7 h after the break, 10h40 net). They were already open and
    # this correction does not change them, so they no longer block it (decided 2026-11-18).
    # An early start is not a deviation (audit A5).
    assert result.passed
    assert {ExceptionCode.MEAL_BREAK_BREACH, ExceptionCode.OVERTIME_RISK}.isdisjoint(failed)
    assert ExceptionCode.SCHEDULE_DEVIATION not in failed


@pytest.mark.parametrize(
    "code,action_type",
    [
        (ExceptionCode.SCHEDULE_DEVIATION, ActionType.ACKNOWLEDGE),
        (ExceptionCode.MEAL_BREAK_BREACH, ActionType.FLAG_PREMIUM),
        (ExceptionCode.OVERTIME_RISK, ActionType.SUGGEST_SCHEDULE_SWAP),
    ],
)
def test_actions_without_agreed_semantics_are_refused(code, action_type, policy):
    case = complete_day(DAY, code)
    action = ProposedAction(type=action_type)
    result = validator(case, [action], policy)
    assert not result.passed and "not supported yet" in result.checks[0].reason


def test_action_not_allowed_for_code(policy):
    result = validator(late_case(), [out_at(18, 0)], policy)
    assert "not allowed for SCHEDULE_DEVIATION" in result.checks[0].reason


# ---- pay integrity: a stated time may only be rounded away from extra pay


@pytest.mark.parametrize(
    "stated,punch_type,hour,minute,ok",
    [
        # Track B's example: the note says 09:05, so 09:00 would pay 5 minutes nobody claimed.
        ("I was at the gate at 9:05", PunchType.IN, 9, 0, False),
        ("I was at the gate at 9:05", PunchType.IN, 9, 5, True),
        ("I was at the gate at 9:05", PunchType.IN, 9, 8, True),  # later start: no extra pay
        ("I was at the gate at 9:05", PunchType.IN, 9, 11, False),  # beyond the tolerance
        ("I left at 18:05", PunchType.OUT, 18, 8, False),  # later clock-out would add pay
        ("I left at 18:05", PunchType.OUT, 18, 5, True),
        ("I left at 18:05", PunchType.OUT, 18, 2, True),
    ],
)
def test_stated_time_rounding_never_adds_paid_time(stated, punch_type, hour, minute, ok, policy):
    case = case_with(notes=(stated,))
    if punch_type == PunchType.IN:
        # Build a case missing its clock-in instead of its clock-out.
        data = case.model_dump()
        data["punches"] = [p for p in data["punches"] if p["type"] != "in"]
        data["punches"].append(
            PunchRecord(
                punch_id="P-out",
                employee_id="E-001",
                ts=datetime(2026, 11, 12, 18, 0, tzinfo=IST),
                type=PunchType.OUT,
                source=PunchSource.KIOSK,
            ).model_dump()
        )
        case = CaseContext.model_validate(data)
    action = ProposedAction(
        type=ActionType.ADD_PUNCH,
        punch_type=punch_type,
        new_ts=datetime(2026, 11, 12, hour, minute, tzinfo=IST),
        evidence_ref=EvidenceRef(kind=EvidenceKind.NOTE, id="N-0"),
    )
    result = validator(case, [action], policy)
    missing = next(c for c in result.checks if c.code == ExceptionCode.MISSING_PUNCH)
    assert missing.passed is ok, missing.reason


def test_schedule_anchor_keeps_both_directions(policy):
    """The schedule is the agreed time, not a claim, so either side stays acceptable."""
    ref = EvidenceRef(kind=EvidenceKind.SCHEDULE_END, id="S-1")
    for minute, ok in [(3, True), (57, True), (6, False)]:
        hour = 18 if minute < 30 else 17
        assert validator(case_with(), [out_at(hour, minute, ref)], policy).passed is ok
