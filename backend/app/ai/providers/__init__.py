"""LLM providers behind one interface (ADR-4)."""

from __future__ import annotations

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


def build_provider(settings: Settings) -> LLMProvider:
    """Construct the configured provider. Raises ProviderError when it cannot be configured."""
    if settings.llm_provider == "mock":
        return MockProvider(model_id=settings.llm_model or "mock-resolver-v1")
    if settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url, model_id=settings.llm_model)
    if settings.llm_provider == "groq":
        key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
        return GroqProvider(
            api_key=key, base_url=settings.groq_base_url, model_id=settings.llm_model
        )
    raise ProviderError(f"unknown LLM provider '{settings.llm_provider}'")
