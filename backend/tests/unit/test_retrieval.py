"""B-03 acceptance: hybrid retrieval quality, wrong-version isolation, and jurisdiction resolution."""

import json
from datetime import date

import httpx
import pytest

from app.ai.pipeline import generate_proposal
from app.ai.providers import MockProvider
from app.core.contracts import EmployeeContext, ExceptionCode, GateStatus
from app.policies.registry import PolicyResolutionError
from app.retrieval.hybrid import retrieve
from app.retrieval.vector import EmbeddingError, HashingEmbedder, OllamaEmbedder
from tests.factories import make_case, passing_validator

EXPECTED_TOP = {
    ("IN-KA", ExceptionCode.MISSING_PUNCH): "KA-8",
    ("IN-KA", ExceptionCode.OVERLAPPING_SHIFT): "KA-11",
    ("IN-KA", ExceptionCode.MEAL_BREAK_BREACH): "KA-6",
    ("IN-KA", ExceptionCode.OVERTIME_RISK): "KA-5",
    ("IN-KA", ExceptionCode.SPREAD_OVER_BREACH): "KA-7",
    ("IN-KA", ExceptionCode.SCHEDULE_DEVIATION): "KA-9",
    ("US-FED", ExceptionCode.MISSING_PUNCH): "US-5",
    ("US-FED", ExceptionCode.OVERLAPPING_SHIFT): "US-7",
    ("US-FED", ExceptionCode.MEAL_BREAK_BREACH): "US-4",
    ("US-FED", ExceptionCode.OVERTIME_RISK): "US-3",
    ("US-FED", ExceptionCode.SCHEDULE_DEVIATION): "US-6",
}


def case_for(code: ExceptionCode, jurisdiction: str = "IN-KA", **kw):
    case = make_case(**kw)
    employee = case.employee.model_copy(update={"jurisdiction": jurisdiction})
    return case.model_copy(update={"code": code, "employee": employee})


@pytest.mark.parametrize(("pack", "code"), list(EXPECTED_TOP))
def test_top_clause_is_the_relevant_one(registry, pack, code):
    result = retrieve(case_for(code, pack), registry.get(pack, "2025.1"))
    assert result.mode == "hybrid:hashing-ngram-v1"
    assert result.clauses[0].clause.clause_id == EXPECTED_TOP[(pack, code)]


def test_no_supporting_clause_escalates(registry, settings):
    # US-FED has no spread-over rule, so nothing clears the relevance floor. The note states a
    # time near the recorded punch so the case passes the evidence gate and reaches retrieval.
    case = case_for(ExceptionCode.SPREAD_OVER_BREACH, "US-FED", notes=("I punched in at 09:00.",))
    policy = registry.get("US-FED", "2025.1")
    assert retrieve(case, policy).clauses == []
    result = generate_proposal(
        case, policy, provider=MockProvider(), validator=passing_validator, settings=settings
    )
    assert result.status == GateStatus.ESCALATED
    assert result.reasons == ["No supporting policy clause was retrieved."]


# ------------------------------------------------------------- wrong-version isolation


def test_near_duplicate_proposed_version_is_never_retrieved(registry):
    active, proposed = registry.get("IN-KA", "2025.1"), registry.get("IN-KA", "2025.2-proposed")
    same_text = {c.clause_id for c in active.clauses} & {c.clause_id for c in proposed.clauses}
    assert len(same_text) == 11  # near-duplicate corpus: same clause ids in both versions
    for code in ExceptionCode:
        hits = retrieve(case_for(code), active, top_k=20).clauses
        assert all(h.clause.chunk_id.startswith("IN-KA@2025.1#") for h in hits)


def test_snapshot_polluted_with_other_version_is_filtered(registry):
    active, proposed = registry.get("IN-KA", "2025.1"), registry.get("IN-KA", "2025.2-proposed")
    polluted = active.model_copy(update={"clauses": [*proposed.clauses, *active.clauses]})
    hits = retrieve(case_for(ExceptionCode.OVERTIME_RISK), polluted, top_k=20).clauses
    assert hits and all(h.clause.version == "2025.1" for h in hits)


def test_citing_identical_text_from_wrong_version_is_blocked(registry, settings, case):
    policy = registry.get("IN-KA", "2025.1")
    quote = "Every working period must have a clock-in and a matching clock-out."
    reply = json.dumps(
        {
            "exception_id": "X-1",
            "decision": "propose",
            "actions": [
                {"type": "add_punch", "punch_type": "out", "new_ts": "2026-11-12T18:00:00+05:30"}
            ],
            "rationale": "r",
            "citations": [{"chunk_id": "IN-KA@2025.2-proposed#KA-8", "quote": quote}],
            "confidence": 0.95,
        }
    )
    result = generate_proposal(
        case,
        policy,
        provider=MockProvider(script=[reply]),
        validator=passing_validator,
        settings=settings,
    )
    assert result.status == GateStatus.BLOCKED
    assert any(c.name == "citations_retrieved" and not c.passed for c in result.gate_checks)


def test_proposed_version_is_never_resolved(registry):
    emp = EmployeeContext(
        employee_id="E", location_id="L", jurisdiction="IN-KA", timezone="Asia/Kolkata"
    )
    assert registry.resolve(emp, date(2026, 11, 12)).version == "2025.1"


def test_proposed_version_passed_in_directly_escalates(registry, settings, case):
    result = generate_proposal(
        case,
        registry.get("IN-KA", "2025.2-proposed"),
        provider=MockProvider(),
        validator=passing_validator,
        settings=settings,
    )
    assert result.status == GateStatus.ESCALATED
    assert any(c.name == "policy_resolved" and not c.passed for c in result.gate_checks)


# ------------------------------------------------------------- jurisdiction flip


def test_same_case_resolves_by_jurisdiction(registry):
    ka = make_case().employee
    us = ka.model_copy(update={"jurisdiction": "US-FED", "timezone": "America/Chicago"})
    day = date(2026, 11, 12)
    assert registry.resolve(ka, day).rules.daily_regular_hours == 9
    assert registry.resolve(us, day).rules.daily_regular_hours == 8
    assert registry.resolve(us, day).rules.max_spread_hours is None
    with pytest.raises(PolicyResolutionError):
        registry.resolve(ka.model_copy(update={"jurisdiction": "IN-TN"}), day)


def test_us_pack_produces_us_citation(registry, settings):
    case = case_for(ExceptionCode.MISSING_PUNCH, "US-FED")
    result = generate_proposal(
        case,
        registry.get("US-FED", "2025.1"),
        provider=MockProvider(),
        validator=passing_validator,
        settings=settings,
    )
    assert result.status == GateStatus.ELIGIBLE
    assert result.proposal.citations[0].chunk_id == "US-FED@2025.1#US-5"


# ------------------------------------------------------------- robustness


def test_employee_note_cannot_steer_retrieval(registry):
    policy = registry.get("IN-KA", "2025.1")
    plain = retrieve(case_for(ExceptionCode.MISSING_PUNCH), policy, top_k=20).clauses
    noisy_case = case_for(
        ExceptionCode.MISSING_PUNCH, notes=("overtime overtime quarter spread rest interval",)
    )
    noisy = retrieve(noisy_case, policy, top_k=20).clauses
    assert [h.clause.chunk_id for h in plain] == [h.clause.chunk_id for h in noisy]


class FailingEmbedder:
    name = "failing"
    vector_floor = 0.5

    def embed(self, texts):
        raise EmbeddingError("down")


def test_embedder_outage_falls_back_to_bm25(registry):
    result = retrieve(
        case_for(ExceptionCode.MISSING_PUNCH),
        registry.get("IN-KA", "2025.1"),
        embedder=FailingEmbedder(),
    )
    assert result.mode.startswith("bm25-only")
    assert result.clauses[0].clause.clause_id == "KA-8"


def test_retrieval_mode_is_recorded_in_gate_checks(case, policy, settings):
    result = generate_proposal(
        case, policy, provider=MockProvider(), validator=passing_validator, settings=settings
    )
    mode = next(c for c in result.gate_checks if c.name == "retrieval_mode")
    assert mode.detail == "hybrid:hashing-ngram-v1"


def test_hashing_embedder_is_deterministic_and_normalised():
    a, b = HashingEmbedder().embed(["missing clock-out", "missing clock-out"])
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-9


def test_ollama_embedder_via_mock_transport():
    def handler(request):
        n = len(json.loads(request.content)["input"])
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0]] * n})

    embedder = OllamaEmbedder(transport=httpx.MockTransport(handler))
    assert embedder.embed(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    broken = OllamaEmbedder(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(EmbeddingError):
        broken.embed(["a"])


class ShiftingDimsEmbedder:
    """Returns a different vector size on each call (e.g. a model updated under the same name)."""

    name, vector_floor = "shifting", 0.5

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0] * (2 + self.calls) for _ in texts]


class NaNEmbedder:
    name, vector_floor = "nan", 0.5

    def embed(self, texts):
        return [[float("nan"), 1.0] for _ in texts]


@pytest.mark.parametrize("embedder", [ShiftingDimsEmbedder(), NaNEmbedder()])
def test_malformed_embeddings_degrade_to_bm25(registry, embedder):
    result = retrieve(
        case_for(ExceptionCode.MISSING_PUNCH), registry.get("IN-KA", "2025.1"), embedder=embedder
    )
    assert result.mode.startswith("bm25-only")
    assert result.clauses[0].clause.clause_id == "KA-8"
