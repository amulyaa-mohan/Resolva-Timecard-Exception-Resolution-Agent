"""LLM providers behind one interface (ADR-4)."""

from __future__ import annotations

import hashlib
import threading

from app.ai.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeout,
)
from app.ai.providers.http import GroqProvider, OllamaProvider
from app.ai.providers.mock import MockProvider
from app.core.config import Settings

__all__ = [
    "ChatMessage",
    "GroqProvider",
    "LLMProvider",
    "MockProvider",
    "OllamaProvider",
    "ProviderError",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTimeout",
    "build_provider",
]


# Audit 2026-11-18: callers built a new provider (and HTTP connection pool) per request, so
# every proposal paid a fresh TCP handshake. HTTP providers are stateless apart from their
# pool and httpx.Client is thread-safe, so one instance per configuration is shared.
_SHARED: dict[tuple, LLMProvider] = {}
_SHARED_LOCK = threading.Lock()


def build_provider(settings: Settings) -> LLMProvider:
    """The configured provider. Raises ProviderError when it cannot be configured.

    HTTP providers are shared per configuration; the mock is always new (it records calls).
    """
    if settings.llm_provider == "mock":
        return MockProvider(model_id=settings.llm_model or "mock-resolver-v1")
    key_digest = (
        hashlib.sha256(settings.groq_api_key.get_secret_value().encode()).hexdigest()
        if settings.groq_api_key
        else ""
    )
    cache_key = (
        settings.llm_provider,
        settings.llm_model,
        settings.ollama_base_url,
        settings.groq_base_url,
        key_digest,
    )
    with _SHARED_LOCK:
        provider = _SHARED.get(cache_key)
        if provider is None:
            provider = _SHARED[cache_key] = _construct(settings)
    return provider


def _construct(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model_id=settings.llm_model)
    if settings.llm_provider == "groq":
        key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
        return GroqProvider(
            api_key=key, base_url=settings.groq_base_url, model_id=settings.llm_model
        )
    raise ProviderError(f"unknown LLM provider '{settings.llm_provider}'")
