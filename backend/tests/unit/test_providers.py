"""Ollama and Groq adapters, exercised through httpx.MockTransport (no network)."""

import json
import time

import httpx
import pytest

from app.ai.pipeline import call_with_deadline, generate_proposal
from app.ai.providers import (
    ChatMessage,
    GroqProvider,
    MockProvider,
    OllamaProvider,
    ProviderError,
    ProviderRequest,
    ProviderTimeout,
    build_provider,
)
from app.core.config import Settings
from app.core.contracts import GateStatus
from tests.factories import passing_validator

SECRET = "gsk_test_not_a_real_key_123"
REQUEST = ProviderRequest(
    messages=(ChatMessage("system", "sys"), ChatMessage("user", "hi")), timeout_s=2.0
)


def transport(handler):
    return httpx.MockTransport(handler)


# ------------------------------------------------------------------------ Ollama


def test_ollama_sends_json_mode_and_parses_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b-instruct",
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "prompt_eval_count": 120,
                "eval_count": 30,
            },
        )

    provider = OllamaProvider(transport=transport(handler))
    response = provider.complete(REQUEST)
    assert response.text == '{"ok": true}'
    assert response.usage == {"prompt_tokens": 120, "completion_tokens": 30}
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["format"] == "json" and seen["body"]["stream"] is False
    assert seen["body"]["keep_alive"] == "30m"
    assert seen["body"]["options"]["temperature"] == 0.1
    assert seen["body"]["model"] == "qwen2.5:7b-instruct"


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)), ProviderTimeout),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused", request=r)), ProviderError),
        (lambda r: httpx.Response(500, text="boom"), ProviderError),
        (lambda r: httpx.Response(200, text="not json"), ProviderError),
        (lambda r: httpx.Response(200, json={"message": {}}), ProviderError),
    ],
)
def test_ollama_failures_map_to_provider_errors(handler, error):
    with pytest.raises(error):
        OllamaProvider(transport=transport(handler)).complete(REQUEST)


def test_ollama_reachability_requires_the_model_to_be_pulled():
    tags = {"models": [{"name": "qwen2.5:7b-instruct"}, {"name": "nomic-embed-text:latest"}]}
    ok = transport(lambda r: httpx.Response(200, json=tags))
    assert OllamaProvider(transport=ok).is_reachable()
    assert not OllamaProvider(model_id="llama3.1:8b", transport=ok).is_reachable()
    down = transport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x", request=r)))
    assert not OllamaProvider(transport=down).is_reachable()


# ------------------------------------------------------------------------ Groq


def test_groq_sends_auth_and_json_mode():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"content": '{"ok": 1}'}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 9, "total_time": 0.2},
            },
        )

    response = GroqProvider(api_key=SECRET, transport=transport(handler)).complete(REQUEST)
    assert response.text == '{"ok": 1}' and response.model_id == "llama-3.1-8b-instant"
    assert response.usage == {"prompt_tokens": 50, "completion_tokens": 9}
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["url"].endswith("/chat/completions")


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_groq_http_errors_never_leak_the_key(status):
    provider = GroqProvider(
        api_key=SECRET, transport=transport(lambda r: httpx.Response(status, text=SECRET))
    )
    with pytest.raises(ProviderError) as exc:
        provider.complete(REQUEST)
    assert SECRET not in str(exc.value)
    assert SECRET not in repr(provider)


def test_groq_requires_a_key():
    with pytest.raises(ProviderError):
        GroqProvider(api_key="")


def test_build_provider_from_settings(settings):
    groq = settings.model_copy(update={"llm_provider": "groq", "groq_api_key": None})
    with pytest.raises(ProviderError):
        build_provider(groq)
    ollama = build_provider(settings.model_copy(update={"llm_provider": "ollama"}))
    assert isinstance(ollama, OllamaProvider) and ollama.model_id == "qwen2.5:7b-instruct"
    custom = settings.model_copy(update={"llm_provider": "ollama", "llm_model": "llama3.1:8b"})
    assert build_provider(custom).model_id == "llama3.1:8b"
    # Settings validated from input (as from .env) hold the key as SecretStr: hidden in repr/logs.
    loaded = Settings(_env_file=None, llm_provider="groq", groq_api_key=SECRET)
    assert SECRET not in repr(loaded) and SECRET not in str(loaded.model_dump())
    assert build_provider(loaded).model_id == "llama-3.1-8b-instant"


# ------------------------------------------------------------------------ deadlines


class SlowProvider(MockProvider):
    def __init__(self, delay: float, **kw):
        super().__init__(**kw)
        self.delay = delay

    def complete(self, request):
        time.sleep(self.delay)
        return super().complete(request)


def test_deadline_is_enforced_even_if_provider_ignores_it():
    started = time.perf_counter()
    with pytest.raises(ProviderTimeout):
        call_with_deadline(SlowProvider(1.0), ProviderRequest(messages=(), timeout_s=0.1))
    assert time.perf_counter() - started < 0.6


def test_slow_model_escalates_within_budget(case, policy, settings):
    fast_budget = settings.model_copy(update={"llm_timeout_s": 0.2})
    started = time.perf_counter()
    result = generate_proposal(
        case,
        policy,
        provider=SlowProvider(1.0),
        validator=passing_validator,
        settings=fast_budget,
    )
    assert result.status == GateStatus.ESCALATED and result.trace.error.startswith("timeout")
    assert time.perf_counter() - started < 0.8


def test_budget_is_shared_across_repair_retry(case, policy, settings):
    # First reply is malformed and uses most of the budget; the retry must not get a fresh 8 s.
    provider = SlowProvider(0.15, script=["not json", "not json"])
    result = generate_proposal(
        case,
        policy,
        provider=provider,
        validator=passing_validator,
        settings=settings.model_copy(update={"llm_timeout_s": 0.25}),
    )
    assert result.status == GateStatus.ESCALATED
    assert result.trace.error and result.trace.error.startswith("timeout")


def test_adapter_bug_fails_safe(case, policy, settings):
    class Broken(MockProvider):
        def complete(self, request):
            raise KeyError("unexpected")

    result = generate_proposal(
        case, policy, provider=Broken(), validator=passing_validator, settings=settings
    )
    assert result.status == GateStatus.ESCALATED
