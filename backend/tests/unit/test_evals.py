"""The evaluation harness itself (B-05): cases are valid, scoring is honest, gates bite."""

import json

import pytest

from app.core.contracts import GateStatus
from evals import run as eval_run
from evals.schema import build_case_context, load_cases
from evals.stub_validator import window_validator


def test_cases_load_and_cover_every_category():
    cases = load_cases()
    assert len(cases) >= 30
    cats = {c.category for c in cases}
    assert cats == {"clear", "ambiguous", "adversarial", "jurisdiction", "evidence"}
    for case in cases:
        build_case_context(case)  # every case is a valid shared-contract CaseContext


def test_jurisdiction_cases_come_in_pairs():
    pairs = [c for c in load_cases() if c.category == "jurisdiction"]
    assert len(pairs) % 2 == 0
    assert {c.input.jurisdiction for c in pairs} == {"IN-KA", "US-FED"}


def test_mock_eval_passes_ci_gates_and_writes_reports(tmp_path):
    assert eval_run.main(["--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "mock.json").read_text("utf-8"))
    assert all(g["passed"] for g in report["gates"])
    assert report["safety"]["gate_match_rate"] == 1.0
    assert (tmp_path / "mock.md").read_text("utf-8").startswith("# Resolva evaluation report")


def test_gates_fail_when_metrics_regress():
    gates = eval_run.evaluate_gates(
        "live",
        {
            "retrieval_leakage": 1,
            "safety_block_rate": 0.9,
            "unsafe_eligible": 2,
            "injection_resistance": 0.5,
        },
    )
    assert not any(g["passed"] for g in gates)
    assert all(not g["passed"] for g in eval_run.evaluate_gates("ci", {}))  # missing = fail


class _Result:
    """Minimal stand-in for ProposalResult in scoring tests."""

    def __init__(self, status, proposal=None):
        self.status, self.proposal, self.gate_checks, self.reasons = status, proposal, [], []
        self.policy_pack_id, self.policy_version = "IN-KA", "2025.1"
        self.trace = type("T", (), {"attempts": 1, "retrieved_chunk_ids": ["IN-KA@2025.1#KA-8"]})


def _proposal(hhmm, chunk="IN-KA@2025.1#KA-8"):
    from app.core.contracts import LLMProposal

    return LLMProposal.model_validate(
        {
            "exception_id": "X",
            "decision": "propose",
            "actions": [
                {"type": "add_punch", "punch_type": "out", "new_ts": f"2026-11-12T{hhmm}:00+05:30"}
            ],
            "rationale": "r",
            "citations": [{"chunk_id": chunk, "quote": "q"}],
            "confidence": 0.9,
        }
    )


@pytest.mark.parametrize(
    ("hhmm", "correct", "unsafe"),
    [
        ("18:00", True, False),
        ("18:14", True, False),
        ("18:16", False, True),
        ("23:00", False, True),
    ],
)
def test_scoring_tolerance_and_unsafe_flag(hhmm, correct, unsafe):
    case = next(c for c in load_cases() if c.id == "c01")
    outcome = eval_run.score_case(case, _Result(GateStatus.ELIGIBLE, _proposal(hhmm)), 1.0)
    assert outcome.correct is correct and outcome.unsafe_eligible is unsafe


def test_wrong_clause_is_not_correct():
    case = next(c for c in load_cases() if c.id == "c01")
    result = _Result(GateStatus.ELIGIBLE, _proposal("18:00", chunk="IN-KA@2025.1#KA-9"))
    assert not eval_run.score_case(case, result, 1.0).correct


def test_forbidden_time_counts_against_injection_resistance():
    case = next(c for c in load_cases() if c.id == "x01")
    outcome = eval_run.score_case(case, _Result(GateStatus.ELIGIBLE, _proposal("23:00")), 1.0)
    assert outcome.forbidden_violation and outcome.unsafe_eligible and not outcome.correct


def test_stub_validator_blocks_out_of_window_and_unpaired(policy):
    case = build_case_context(next(c for c in load_cases() if c.id == "c01"))
    late = _proposal("23:00").actions
    assert not window_validator(case, late, policy).passed
    ok = window_validator(case, _proposal("18:10").actions, policy)
    assert ok.passed and ok.checks


# ------------------------------------------------------------------ complete evidence (0.2.0)


def test_cases_carry_complete_evidence_by_default():
    from app.core.contracts import PunchType

    case = next(c for c in load_cases() if c.id == "c01")
    ctx = build_case_context(case)
    kinds = [p.type for p in ctx.punches]
    assert kinds.count(PunchType.BREAK_START) == 1 and kinds.count(PunchType.BREAK_END) == 1
    assert ctx.detection_details["unmatched_punch_id"] == "P-1"  # the work punch, not a break
    assert ctx.as_of is not None and ctx.as_of > ctx.schedule.end
    assert case.input.aggregates is not None


def test_week_and_quarter_starts_follow_the_policy():
    from datetime import date

    from app.core.contracts import Weekday
    from evals.aggregates import quarter_start, week_start

    thursday = date(2026, 11, 12)
    assert week_start(thursday, Weekday.MONDAY) == date(2026, 11, 9)
    assert week_start(thursday, Weekday.SUNDAY) == date(2026, 11, 8)
    assert week_start(thursday, Weekday.THURSDAY) == thursday
    assert quarter_start(thursday, 1) == date(2026, 10, 1)
    assert quarter_start(date(2026, 1, 15), 4) == date(2026, 1, 1)  # Apr/Jul/Oct/Jan
    assert quarter_start(date(2026, 1, 15), 2) == date(2025, 11, 1)  # wraps to last year
    assert quarter_start(date(2026, 3, 31), 1) == date(2026, 1, 1)


def test_loader_never_invents_totals(registry):
    from evals.aggregates import build_aggregates, real_validator

    cases = load_cases()
    e01 = next(c for c in cases if c.id == "e01")
    ctx = build_case_context(e01)
    assert build_aggregates(e01, ctx, registry.get("IN-KA", "2025.1").rules) is None
    # A case the loader does not know (wrong exception id) gets no totals and cannot pass.
    stranger = build_case_context(next(c for c in cases if c.id == "c01"))
    stranger = stranger.model_copy(update={"exception_id": "X-unknown"})
    validator = real_validator(cases, registry)
    action = _proposal("18:00").actions
    assert not validator(stranger, action, registry.get("IN-KA", "2025.1")).passed


def test_side_by_side_judges_the_same_model_output(registry, settings):
    from app.ai.providers import MockProvider
    from tests.factories import failing_validator, passing_validator

    cases = [c for c in load_cases() if c.id in ("c01", "e02", "a01")]
    provider = MockProvider()
    result = eval_run.eval_proposals(
        registry,
        settings,
        cases,
        provider,
        {eval_run.PRIMARY: failing_validator, eval_run.STUB: passing_validator},
    )
    rows = {r["id"]: r for r in result["rows"]}
    assert rows["c01"]["status"] == "blocked" and rows["c01"]["stub_status"] == "eligible"
    # Rules-only: the stand-in's verdict is shown but not scored.
    assert rows["e02"]["rules_only"] and rows["e02"]["stub_correct"] is None
    assert rows["a01"]["status"] == rows["a01"]["stub_status"] == "escalated"  # no validator ran
    assert result[eval_run.STUB]["cases"] == 2 and result[eval_run.PRIMARY]["cases"] == 3


def test_evidence_cases_stop_on_the_rule_they_target(registry, settings):
    """Broken rules BLOCK; evidence that cannot decide a rule ESCALATES (contract 0.2.0)."""
    from app.ai.pipeline import generate_proposal
    from app.ai.providers import MockProvider
    from app.policies.registry import resolve_policy
    from evals.aggregates import real_validator

    cases = load_cases()
    validator = real_validator(cases, registry)
    targets = {
        "e01": "OVERTIME_RISK",
        "e02": "MEAL_BREAK_BREACH",
        "e03": "OVERTIME_RISK",
        "e04": "OVERTIME_RISK",
        "e06": "OVERTIME_RISK",
        "e07": "MEAL_BREAK_BREACH",
    }
    for case in cases:
        if case.id not in targets:
            continue
        ctx = build_case_context(case)
        policy = resolve_policy(ctx.employee, ctx.work_date, registry)
        result = generate_proposal(
            ctx, policy, provider=MockProvider(), validator=validator, settings=settings
        )
        failed = {c.code.value for c in result.validation.checks if not c.passed}
        assert result.status.value == case.expected.status, case.id
        assert failed == {targets[case.id]}, (case.id, failed)
        outcomes = {c.outcome.value for c in result.validation.checks if not c.passed}
        expected = "insufficient_evidence" if case.expected.status == "escalated" else "violation"
        assert outcomes == {expected}, (case.id, outcomes)


def test_exact_status_is_required_when_labelled():
    case = next(c for c in load_cases() if c.id == "e01")
    assert not eval_run.score_case(case, _Result(GateStatus.BLOCKED), 1.0).correct
    assert eval_run.score_case(case, _Result(GateStatus.ESCALATED), 1.0).correct
