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
from app.ai.providers.mock import MockProvider
from app.core.config import Settings

__all__ = [
    "ChatMessage",
    "LLMProvider",
    "MockProvider",
    "ProviderError",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderTimeout",
    "build_provider",
]


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider(model_id=settings.llm_model)
    # Ollama and Groq providers are planned in task B-03.
    raise ProviderError(f"LLM provider '{settings.llm_provider}' is not implemented yet (B-03).")
