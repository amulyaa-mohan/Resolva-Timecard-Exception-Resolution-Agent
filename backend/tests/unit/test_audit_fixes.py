"""Regression tests for the Track B findings of the 2026-11-18 backend audit."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai.pipeline import generate_proposal
from app.ai.providers import MockProvider, build_provider
from app.core.contracts import ExceptionCode, GateStatus, RuleCheck, RuleOutcome, ValidationResult
from app.main import create_app
from app.retrieval.vector import build_embedder


def test_http_providers_are_shared_per_configuration(settings):
    ollama = settings.model_copy(update={"llm_provider": "ollama"})
    assert build_provider(ollama) is build_provider(ollama)
    other = ollama.model_copy(update={"llm_model": "llama3.1:8b"})
    assert build_provider(other) is not build_provider(ollama)


def test_mock_provider_is_never_shared(settings):
    # The mock records every call, so sharing it would grow without bound.
    assert build_provider(settings) is not build_provider(settings)


def test_ollama_embedder_is_shared_per_configuration(settings):
    s = settings.model_copy(update={"embedding_provider": "ollama"})
    assert build_embedder(s) is build_embedder(s)


def test_identical_validator_reasons_are_reported_once(case, policy, settings):
    def unsupported(case, actions, policy):
        checks = [
            RuleCheck(code=c, passed=False, reason="add_break corrections are not supported yet.")
            for c in ExceptionCode
        ]
        return ValidationResult(passed=False, checks=checks, rule_version="t")

    result = generate_proposal(
        case, policy, provider=MockProvider(), validator=unsupported, settings=settings
    )
    assert result.status == GateStatus.BLOCKED
    reason = next(r for r in result.reasons if "fails rule validation" in r)
    assert reason.count("not supported yet") == 1
    assert "MISSING_PUNCH, OVERLAPPING_SHIFT" in reason


def test_mixed_reasons_keep_each_rule(case, policy, settings):
    def mixed(case, actions, policy):
        checks = [
            RuleCheck(code=ExceptionCode.MISSING_PUNCH, passed=False, reason="a"),
            RuleCheck(code=ExceptionCode.SPREAD_OVER_BREACH, passed=False, reason="b"),
            RuleCheck(
                code=ExceptionCode.OVERTIME_RISK,
                passed=False,
                reason="c",
                outcome=RuleOutcome.INSUFFICIENT_EVIDENCE,
            ),
        ]
        return ValidationResult(passed=False, checks=checks, rule_version="t")

    result = generate_proposal(
        case, policy, provider=MockProvider(), validator=mixed, settings=settings
    )
    assert any("MISSING_PUNCH: a" in r and "SPREAD_OVER_BREACH: b" in r for r in result.reasons)


def test_assistant_is_open_without_the_attendance_store(settings):
    client = TestClient(create_app(settings))
    assert client.post("/assistant/query", json={"text": "show missing punches"}).status_code == 200


def test_assistant_requires_a_manager_when_the_attendance_store_is_enabled(settings):
    app = create_app(settings)
    app.state.attendance_repository = object()  # configured store
    app.state.attendance_credentials = ()  # no valid token exists
    client = TestClient(app)
    body = {"text": "show missing punches"}
    assert client.post("/assistant/query", json=body).status_code == 401
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.post("/assistant/query", json=body, headers=bad).status_code == 401
