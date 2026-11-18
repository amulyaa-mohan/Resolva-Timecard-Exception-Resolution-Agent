"""Contract 0.2.0-draft: rule outcomes, evidence refs, policy calendar fields, as_of."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.ai.evidence import anchor_times, missing_evidence
from app.ai.pipeline import build_messages, case_facts, generate_proposal
from app.ai.providers import MockProvider
from app.core.contracts import (
    CONTRACT_VERSION,
    EvidenceKind,
    EvidenceRef,
    ExceptionCode,
    GateStatus,
    PolicyRules,
    ProposedAction,
    RuleCheck,
    RuleOutcome,
    ValidationResult,
    Weekday,
)
from app.retrieval.hybrid import retrieve
from tests.factories import make_case, passing_validator

KA8 = "IN-KA@2025.1#KA-8"
KA8_QUOTE = "Every working period must have a clock-in and a matching clock-out."


def proposal(new_ts="2026-11-12T18:00:00+05:30", evidence_ref=None) -> str:
    action = {"type": "add_punch", "punch_type": "out", "new_ts": new_ts}
    if evidence_ref is not None:
        action["evidence_ref"] = evidence_ref
    return json.dumps(
        {
            "exception_id": "X-1",
            "decision": "propose",
            "actions": [action],
            "rationale": "Clock-out missing; infer from schedule.",
            "citations": [{"chunk_id": KA8, "quote": KA8_QUOTE}],
            "confidence": 0.9,
            "missing_information": [],
        }
    )


def run(case, policy, settings, script=None, validator=passing_validator):
    provider = MockProvider(script=script) if script else MockProvider()
    return generate_proposal(
        case, policy, provider=provider, validator=validator, settings=settings
    )


def validator_with(*outcomes: RuleOutcome):
    def validate(case, actions, policy):
        checks = [
            RuleCheck(code=case.code, passed=o == RuleOutcome.PASS, reason=o.value, outcome=o)
            for o in outcomes
        ]
        return ValidationResult(
            passed=all(c.passed for c in checks), checks=checks, rule_version="t"
        )

    return validate


# ------------------------------------------------------------------ contract shape


def test_version_bumped():
    assert CONTRACT_VERSION == "0.2.0-draft"


def test_rule_check_outcome_is_derived_from_passed_for_existing_callers():
    assert RuleCheck(code="MISSING_PUNCH", passed=True, reason="r").outcome == RuleOutcome.PASS
    failed = RuleCheck(code="MISSING_PUNCH", passed=False, reason="r")
    assert failed.outcome == RuleOutcome.VIOLATION
    explicit = RuleCheck(
        code="MISSING_PUNCH", passed=False, reason="r", outcome="insufficient_evidence"
    )
    assert explicit.outcome == RuleOutcome.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("passed", "outcome"), [(True, "violation"), (True, "insufficient_evidence"), (False, "pass")]
)
def test_rule_check_rejects_inconsistent_outcome(passed, outcome):
    with pytest.raises(ValidationError):
        RuleCheck(code="MISSING_PUNCH", passed=passed, reason="r", outcome=outcome)


def test_validation_result_cannot_pass_with_failing_or_missing_checks():
    failing = RuleCheck(code="MISSING_PUNCH", passed=False, reason="r")
    with pytest.raises(ValidationError):
        ValidationResult(passed=True, checks=[failing], rule_version="t")
    with pytest.raises(ValidationError):
        ValidationResult(passed=True, checks=[], rule_version="t")
    assert not ValidationResult(passed=False, checks=[], rule_version="t").passed


def test_policy_calendar_and_tolerance_fields(registry):
    for pack in ("IN-KA", "US-FED"):
        rules = registry.get(pack, "2025.1").rules
        assert rules.evidence_tolerance_min == 5
        assert rules.week_start == Weekday.MONDAY and rules.week_start.number == 0
        assert rules.quarter_start_month == 1
    base = registry.get("IN-KA", "2025.1").rules.model_dump()
    for field, bad in [
        ("quarter_start_month", 13),
        ("quarter_start_month", 0),
        ("week_start", "funday"),
        ("evidence_tolerance_min", -1),
        ("evidence_tolerance_min", 61),
    ]:
        with pytest.raises(ValidationError):
            PolicyRules(**{**base, field: bad})
    missing = {k: v for k, v in base.items() if k != "week_start"}
    with pytest.raises(ValidationError):
        PolicyRules(**missing)


def test_weekday_index_matches_python():
    assert [d.number for d in Weekday] == list(range(7))
    assert Weekday.SUNDAY.number == 6
    assert Weekday.MONDAY.index("d") == 3  # str methods are not shadowed


def test_case_as_of_must_be_timezone_aware():
    case = make_case()
    assert case.as_of is None
    with pytest.raises(ValidationError):
        type(case).model_validate({**case.model_dump(), "as_of": "2026-11-12T20:00:00"})


# ------------------------------------------------------------------ evidence refs


def test_eligible_proposal_carries_the_schedule_evidence_ref(case, policy, settings):
    result = run(case, policy, settings)
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    ref = result.proposal.actions[0].evidence_ref
    assert ref == EvidenceRef(kind=EvidenceKind.SCHEDULE_END, id="S-1")


def test_validator_receives_the_anchored_actions(case, policy, settings):
    seen = []

    def spy(case, actions, policy):
        seen.extend(actions)
        return passing_validator(case, actions, policy)

    run(case, policy, settings, validator=spy)
    assert seen and seen[0].evidence_ref is not None


def test_note_time_is_anchored_to_that_note():
    case = make_case(notes=("Forgot to punch out, left at 18:10.",))
    action = ProposedAction.model_validate_json(
        '{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T18:10:00+05:30"}'
    )
    anchored, problems = anchor_times(case, [action], timedelta(minutes=5))
    assert not problems
    assert anchored[0].evidence_ref == EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")


def test_history_time_is_anchored_to_that_punch():
    base = make_case()
    week_ago = base.punches[0].model_copy(
        update={
            "punch_id": "H-1",
            "type": "out",
            "ts": base.schedule.end - timedelta(days=7) + timedelta(minutes=20),
        }
    )
    case = base.model_copy(update={"punch_history": [week_ago]})
    action = ProposedAction.model_validate_json(
        '{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T18:20:00+05:30"}'
    )
    anchored, problems = anchor_times(case, [action], timedelta(minutes=5))
    assert not problems
    assert anchored[0].evidence_ref == EvidenceRef(kind=EvidenceKind.HISTORY_PUNCH, id="H-1")


def test_model_supplied_ref_that_does_not_support_the_time_blocks(case, policy, settings):
    # The time matches the schedule end, but the model claims a note that does not exist.
    fake = {"kind": "note", "id": "N-99"}
    result = run(case, policy, settings, script=[proposal(evidence_ref=fake)])
    assert result.status == GateStatus.BLOCKED
    assert any("does not support" in r for r in result.reasons)


def test_model_supplied_ref_that_matches_is_kept(case, policy, settings):
    ref = {"kind": "schedule_end", "id": "S-1"}
    result = run(case, policy, settings, script=[proposal(evidence_ref=ref)])
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert result.proposal.actions[0].evidence_ref.kind == EvidenceKind.SCHEDULE_END


def test_tolerance_comes_from_the_policy(case, policy, settings):
    off_by_3 = [proposal("2026-11-12T18:03:00+05:30")]
    assert run(case, policy, settings, script=off_by_3).status == GateStatus.ELIGIBLE
    strict_rules = policy.rules.model_copy(update={"evidence_tolerance_min": 0})
    strict = policy.model_copy(update={"rules": strict_rules})
    result = run(case, strict, settings, script=off_by_3)
    assert result.status == GateStatus.BLOCKED
    assert any("not supported" in r for r in result.reasons)


# ------------------------------------------------------------------ rule outcomes


def test_insufficient_evidence_escalates_and_keeps_the_proposal(case, policy, settings):
    validator = validator_with(RuleOutcome.PASS, RuleOutcome.INSUFFICIENT_EVIDENCE)
    result = run(case, policy, settings, validator=validator)
    assert result.status == GateStatus.ESCALATED
    assert result.proposal is not None and result.validation is not None
    assert any("Not enough evidence" in r for r in result.reasons)


def test_violation_blocks_even_with_insufficient_evidence(case, policy, settings):
    validator = validator_with(RuleOutcome.INSUFFICIENT_EVIDENCE, RuleOutcome.VIOLATION)
    result = run(case, policy, settings, validator=validator)
    assert result.status == GateStatus.BLOCKED
    assert any("fails rule validation" in r for r in result.reasons)


def test_all_pass_is_eligible(case, policy, settings):
    result = run(case, policy, settings, validator=validator_with(RuleOutcome.PASS))
    assert result.status == GateStatus.ELIGIBLE


# ------------------------------------------------------------------ as_of


def test_closing_punch_after_as_of_is_blocked(case, policy, settings):
    open_shift = case.model_copy(update={"as_of": case.schedule.end - timedelta(hours=2)})
    result = run(open_shift, policy, settings)
    assert result.status == GateStatus.BLOCKED
    assert any("after the evaluation time" in r for r in result.reasons)


def test_closing_punch_before_as_of_is_fine(case, policy, settings):
    later = case.model_copy(update={"as_of": case.schedule.end + timedelta(hours=3)})
    assert run(later, policy, settings).status == GateStatus.ELIGIBLE


def test_as_of_is_stated_in_the_facts_block(case, policy, settings):
    later = case.model_copy(update={"as_of": case.schedule.end + timedelta(hours=3)})
    retrieved = retrieve(later, policy, top_k=4).clauses
    user = build_messages(later, retrieved, settings.prompts_dir, "propose_v2", policy)[1].content
    assert "Evaluation time (now): Thu 2026-11-12 21:00" in user


def test_other_codes_are_not_anchored():
    case = make_case().model_copy(update={"code": ExceptionCode.SCHEDULE_DEVIATION})
    assert anchor_times(case, [], timedelta(minutes=5)) == ([], [])


# ------------------------------------------------------------------ verification regressions


def _to_utc(case):
    d = case.model_dump()
    for p in d["punches"] + d["punch_history"]:
        p["ts"] = p["ts"].astimezone(UTC)
    if d["schedule"]:
        for k in ("start", "end"):
            d["schedule"][k] = d["schedule"][k].astimezone(UTC)
    return type(case).model_validate(d)


def test_utc_stored_timestamps_behave_like_local_ones(policy, settings):
    # A database usually returns UTC; notes and the model still work in the employee's zone.
    consistent = _to_utc(make_case(notes=("Forgot to punch out, left at 18:10.",)))
    assert missing_evidence(consistent, policy) == []
    conflicting = _to_utc(make_case(notes=("I actually left at 21:30.",)))
    assert "21:30" in missing_evidence(conflicting, policy)[0]
    action = ProposedAction.model_validate_json(
        '{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T12:40:00+00:00"}'
    )
    anchored, problems = anchor_times(consistent, [action], timedelta(minutes=5))
    assert not problems and anchored[0].evidence_ref.kind == EvidenceKind.NOTE
    facts = case_facts(_to_utc(make_case()), policy)
    assert "Thu 2026-11-12 09:00 (UTC+0530) to Thu 2026-11-12 18:00 (UTC+0530)" in facts
    result = run(_to_utc(make_case()), policy, settings)
    assert result.status == GateStatus.ELIGIBLE, result.reasons


def test_overnight_note_time_on_the_next_day_is_anchored():
    base = make_case(notes=("Left at 06:05 in the morning.",))
    shift = base.schedule.model_copy(
        update={
            "start": base.schedule.start.replace(hour=22),
            "end": base.schedule.start.replace(hour=6) + timedelta(days=1),
        }
    )
    case = base.model_copy(update={"schedule": shift})
    action = ProposedAction.model_validate_json(
        '{"type":"add_punch","punch_type":"out","new_ts":"2026-11-13T06:05:00+05:30"}'
    )
    anchored, problems = anchor_times(case, [action], timedelta(minutes=5))
    assert not problems
    assert anchored[0].evidence_ref.kind in {EvidenceKind.SCHEDULE_END, EvidenceKind.NOTE}


def test_dst_zone_schedule_anchor():
    # US-FED, 2026-11-01 is the US fall-back date; offsets differ across the day.
    tz = ZoneInfo("America/Los_Angeles")
    base = make_case()
    employee = base.employee.model_copy(update={"timezone": "America/Los_Angeles"})
    shift = base.schedule.model_copy(
        update={
            "start": datetime(2026, 11, 1, 0, 30, tzinfo=tz),
            "end": datetime(2026, 11, 1, 9, 0, tzinfo=tz),
        }
    )
    case = base.model_copy(
        update={
            "employee": employee,
            "schedule": shift,
            "work_date": date(2026, 11, 1),
            "notes": [],
            "punches": [
                base.punches[0].model_copy(update={"ts": datetime(2026, 11, 1, 0, 31, tzinfo=tz)})
            ],
        }
    )
    ok = ProposedAction(type="add_punch", punch_type="out", new_ts=shift.end.astimezone(UTC))
    anchored, problems = anchor_times(case, [ok], timedelta(minutes=5))
    assert not problems and anchored[0].evidence_ref.kind == EvidenceKind.SCHEDULE_END
    hour_off = ok.model_copy(update={"new_ts": shift.end - timedelta(hours=1)})
    assert anchor_times(case, [hour_off], timedelta(minutes=5))[1]


def test_punch_exactly_at_as_of_is_allowed_one_second_later_is_not(case):
    action = ProposedAction(type="add_punch", punch_type="out", new_ts=case.schedule.end)
    at = case.model_copy(update={"as_of": case.schedule.end})
    assert anchor_times(at, [action], timedelta(minutes=5))[1] == []
    before = case.model_copy(update={"as_of": case.schedule.end - timedelta(seconds=1)})
    assert "after the evaluation time" in anchor_times(before, [action], timedelta(minutes=5))[1][0]


def test_right_id_wrong_kind_is_rejected(case):
    action = ProposedAction(
        type="add_punch",
        punch_type="out",
        new_ts=case.schedule.end,
        evidence_ref=EvidenceRef(kind=EvidenceKind.SCHEDULE_START, id="S-1"),
    )
    assert "does not support" in anchor_times(case, [action], timedelta(minutes=5))[1][0]


def test_unverified_model_ref_never_reaches_the_validator_for_unanchored_actions():
    case = make_case().model_copy(update={"code": ExceptionCode.OVERTIME_RISK})
    action = ProposedAction(
        type="acknowledge", evidence_ref=EvidenceRef(kind=EvidenceKind.NOTE, id="N-99")
    )
    anchored, problems = anchor_times(case, [action], timedelta(minutes=5))
    assert problems == [] and anchored[0].evidence_ref is None


# ------------------------------------------------------------------ adjust_punch (Track A A-05)

_LATE = "2026-11-12T09:20:00+05:30"


def _late_arrival(note: str | None = "I was at the gate at 09:05, the kiosk was down."):
    """SCHEDULE_DEVIATION: clock-in recorded 09:20 for a 09:00 start."""
    base = make_case(notes=(note,) if note else ())
    punch = base.punches[0].model_copy(update={"ts": datetime.fromisoformat(_LATE)})
    return base.model_copy(update={"code": ExceptionCode.SCHEDULE_DEVIATION, "punches": [punch]})


def _adjust(hhmm: str, **extra) -> ProposedAction:
    return ProposedAction(
        type="adjust_punch",
        punch_id=extra.pop("punch_id", "P-1"),
        new_ts=datetime.fromisoformat(f"2026-11-12T{hhmm}:00+05:30"),
        **extra,
    )


def test_adjustment_to_a_stated_time_is_anchored_to_the_note():
    anchored, problems = anchor_times(_late_arrival(), [_adjust("09:05")], timedelta(minutes=5))
    assert problems == []
    assert anchored[0].evidence_ref == EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")
    assert anchored[0].punch_type is None  # the model's action is not rewritten beyond the ref


def test_adjustment_to_the_scheduled_time_is_refused():
    # A late arrival must not be quietly moved to the scheduled start.
    case = _late_arrival(note=None)
    _, problems = anchor_times(case, [_adjust("09:00")], timedelta(minutes=5))
    assert "not a time the employee stated" in problems[0]
    ref = EvidenceRef(kind=EvidenceKind.SCHEDULE_START, id="S-1")
    _, problems = anchor_times(case, [_adjust("09:00", evidence_ref=ref)], timedelta(minutes=5))
    assert "does not support" in problems[0]


def test_adjustment_from_history_is_refused():
    case = _late_arrival(note=None)
    habit = case.punches[0].model_copy(
        update={"punch_id": "H-1", "ts": datetime.fromisoformat("2026-11-05T09:05:00+05:30")}
    )
    case = case.model_copy(update={"punch_history": [habit]})
    _, problems = anchor_times(case, [_adjust("09:05")], timedelta(minutes=5))
    assert problems and "not a time the employee stated" in problems[0]


def test_adjustment_must_target_this_cases_punch():
    _, problems = anchor_times(
        _late_arrival(), [_adjust("09:05", punch_id="P-other")], timedelta(minutes=5)
    )
    assert "not one of this case's punches" in problems[0]


def test_adjustment_after_as_of_is_refused():
    case = _late_arrival(note="Clocked in at 23:00.")
    case = case.model_copy(update={"as_of": datetime.fromisoformat("2026-11-12T20:00:00+05:30")})
    _, problems = anchor_times(case, [_adjust("23:00")], timedelta(minutes=5))
    assert "after the evaluation time" in problems[0]


def test_adjustment_through_the_pipeline_reaches_the_validator_with_a_note_ref(policy, settings):
    seen = []

    def spy(case, actions, policy):
        seen.extend(actions)
        return passing_validator(case, actions, policy)

    body = {
        "exception_id": "X-1",
        "decision": "propose",
        "actions": [
            {"type": "adjust_punch", "punch_id": "P-1", "new_ts": "2026-11-12T09:05:00+05:30"}
        ],
        "rationale": "Employee states 09:05; kiosk was down.",
        "citations": [{"chunk_id": KA8, "quote": KA8_QUOTE}],
        "confidence": 0.9,
        "missing_information": [],
    }
    result = run(_late_arrival(), policy, settings, script=[json.dumps(body)], validator=spy)
    assert any(c.name == "time_evidence" and c.passed for c in result.gate_checks), result.reasons
    assert seen and seen[0].evidence_ref == EvidenceRef(kind=EvidenceKind.NOTE, id="N-0")


def test_rule_check_accepts_json_booleans():
    check = RuleCheck.model_validate_json('{"code":"MISSING_PUNCH","passed":"true","reason":"r"}')
    assert check.passed and check.outcome == RuleOutcome.PASS
    with pytest.raises(ValidationError):
        RuleCheck.model_validate({"code": "MISSING_PUNCH", "passed": "maybe", "reason": "r"})


def test_proposal_json_round_trips_with_evidence_ref(case, policy, settings):
    result = run(case, policy, settings)
    again = type(result).model_validate_json(result.model_dump_json())
    assert again.proposal.actions[0].evidence_ref == result.proposal.actions[0].evidence_ref


def test_null_note_from_the_model_is_treated_as_empty():
    action = ProposedAction.model_validate_json(
        '{"type":"add_punch","punch_type":"out","new_ts":"2026-11-12T18:00:00+05:30","note":null}'
    )
    assert action.note == ""
    with pytest.raises(ValidationError):
        ProposedAction.model_validate({"type": "add_punch", "punch_type": "out", "note": 5})
