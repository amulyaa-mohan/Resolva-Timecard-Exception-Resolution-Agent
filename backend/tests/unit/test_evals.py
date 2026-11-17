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
    assert cats == {"clear", "ambiguous", "adversarial", "jurisdiction"}
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
