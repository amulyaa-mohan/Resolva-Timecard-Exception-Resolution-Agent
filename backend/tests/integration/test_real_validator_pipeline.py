"""Track B pipeline + Track A real validator. Scripted provider: proves gates, not model quality."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from app.ai.pipeline import generate_proposal
from app.ai.providers import MockProvider
from app.attendance.context import build_verified_case
from app.core.contracts import CaseContext, ExceptionCode, GateStatus, PunchRecord, PunchSource
from app.rules.engine import AggregateEvidence
from app.rules.validator import make_validator, validate_correction
from tests.factories import IST, make_case

KA8 = "IN-KA@2025.1#KA-8"
KA8_QUOTE = "Every working period must have a clock-in and a matching clock-out."
COMPLETE = AggregateEvidence(
    work_date_complete=True,
    week_other_worked_hours=0,
    week_remaining_scheduled_hours=0,
    quarter_other_overtime_hours=0,
    week_start=date(2026, 11, 9),
    quarter_start=date(2026, 10, 1),
    as_of=datetime(2026, 11, 13, 6, 0, tzinfo=UTC),
)


def evidenced_case(with_break=True) -> CaseContext:
    base = make_case()
    times = [("in", 9)] + ([("break_start", 13), ("break_end", 14)] if with_break else [])
    punches = [
        PunchRecord(
            punch_id=f"P-{i}",
            employee_id="E-001",
            ts=datetime(2026, 11, 12, hour, 0, tzinfo=IST),
            type=kind,
            source=PunchSource.KIOSK,
        ).model_dump()
        for i, (kind, hour) in enumerate(times)
    ]
    case = CaseContext.model_validate({**base.model_dump(), "punches": punches})
    return build_verified_case(case, correction_revision=0)


def proposal(new_ts="2026-11-12T18:00:00+05:30", punch_type="out") -> str:
    return json.dumps(
        {
            "exception_id": "X-1",
            "decision": "propose",
            "actions": [{"type": "add_punch", "punch_type": punch_type, "new_ts": new_ts}],
            "rationale": "Clock-out missing; scheduled end.",
            "citations": [{"chunk_id": KA8, "quote": KA8_QUOTE}],
            "confidence": 0.9,
            "missing_information": [],
        }
    )


def run(case, policy, settings, validator, script=None):
    return generate_proposal(
        case,
        policy,
        provider=MockProvider(script=[script or proposal()]),
        validator=validator,
        settings=settings,
    )


def test_fully_evidenced_case_is_eligible_with_real_validator(policy, settings):
    result = run(evidenced_case(), policy, settings, make_validator(lambda _: COMPLETE))
    assert result.status == GateStatus.ELIGIBLE, result.reasons
    assert result.validation.passed and len(result.validation.checks) == 6
    assert result.validation.rule_version.startswith("attendance-rules@")
    gates = {g.name: g.passed for g in result.gate_checks}
    # Track B's citation and time-grounding gates still run before the validator.
    assert gates["time_evidence"] and gates["citation_quotes_verbatim"]
    assert gates["rules_revalidation"]


def test_default_real_validator_escalates_without_aggregates(policy, settings):
    # Contract 0.2.0: missing totals are insufficient evidence -> ESCALATED, never ELIGIBLE.
    result = run(evidenced_case(), policy, settings, validate_correction)
    assert result.status == GateStatus.ESCALATED
    overtime = next(c for c in result.validation.checks if c.code == ExceptionCode.OVERTIME_RISK)
    assert overtime.outcome == "insufficient_evidence"
    assert any(ExceptionCode.OVERTIME_RISK.value in r for r in result.reasons)


@pytest.mark.parametrize(
    "source",
    [
        lambda _: None,
        lambda _: AggregateEvidence(work_date_complete=False),
        lambda _: AggregateEvidence(
            work_date_complete=True, week_other_worked_hours=0, week_remaining_scheduled_hours=None
        ),
    ],
)
def test_incomplete_aggregates_escalate(source, policy, settings):
    result = run(evidenced_case(), policy, settings, make_validator(source))
    assert result.status == GateStatus.ESCALATED
    assert "incomplete" in " ".join(result.reasons)


def test_aggregate_source_crash_escalates(policy, settings):
    def broken(_):
        raise ConnectionError("db down")

    result = run(evidenced_case(), policy, settings, make_validator(broken))
    assert result.status == GateStatus.ESCALATED
    assert "unavailable" in " ".join(result.reasons)


@pytest.mark.parametrize(
    "new_ts,status",
    [
        ("2026-11-12T18:03:00+05:30", GateStatus.ELIGIBLE),  # within 5 min of schedule end
        ("2026-11-12T18:05:00+05:30", GateStatus.ELIGIBLE),  # exactly the tolerance
        ("2026-11-12T18:06:00+05:30", GateStatus.BLOCKED),  # no evidence supports it
    ],
)
def test_evidence_tolerance_boundary_with_real_validator(new_ts, status, policy, settings):
    result = run(
        evidenced_case(), policy, settings, make_validator(lambda _: COMPLETE), proposal(new_ts)
    )
    assert result.status == status, result.reasons
    if status == GateStatus.ELIGIBLE:
        ref = result.proposal.actions[0].evidence_ref
        assert ref.kind == "schedule_end" and ref.id == "S-1"


def test_evidenced_fix_that_creates_overtime_goes_to_the_manager(policy, settings):
    # 8 h today pushes the projected week to 49 h > 48 h. Agreed 2026-11-18: overtime is a
    # warning that was really worked; an evidenced fix whose only remainder is overtime is
    # escalated for manager review (and paid), never silently approved or blocked.
    over = replace(COMPLETE, week_other_worked_hours=41)
    result = run(evidenced_case(), policy, settings, make_validator(lambda _: over))
    assert result.status == GateStatus.ESCALATED
    reasons = " ".join(result.reasons)
    assert "OVERTIME_RISK" in reasons and "manager review" in reasons
    assert "MISSING_PUNCH" not in reasons


def test_fix_leaving_meal_break_violation_is_blocked(policy, settings):
    result = run(
        evidenced_case(with_break=False), policy, settings, make_validator(lambda _: COMPLETE)
    )
    assert result.status == GateStatus.BLOCKED
    assert "MEAL_BREAK_BREACH" in " ".join(result.reasons)


def test_duplicate_clock_in_blocked(policy, settings):
    result = run(
        evidenced_case(),
        policy,
        settings,
        make_validator(lambda _: COMPLETE),
        proposal("2026-11-12T09:00:00+05:30", punch_type="in"),
    )
    assert result.status == GateStatus.BLOCKED


def test_low_confidence_still_escalates_after_real_validation(policy, settings):
    body = json.loads(proposal())
    body["confidence"] = 0.2
    result = run(
        evidenced_case(), policy, settings, make_validator(lambda _: COMPLETE), json.dumps(body)
    )
    assert result.status == GateStatus.ESCALATED
    assert result.validation.passed  # valid correction, but not eligible: separate concerns


def test_evidence_version_is_carried_through(policy, settings):
    case = evidenced_case()
    result = run(case, policy, settings, make_validator(lambda _: COMPLETE))
    assert result.evidence_version == case.evidence_version
    assert case.punches[-1].ts == datetime(2026, 11, 12, 14, 0, tzinfo=IST)
    assert len(case.punches) == 3  # the simulated clock-out never reaches the raw evidence
