"""Provider abstraction (ADR-4). The LLM sees text only; it cannot read or write data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


class ProviderError(RuntimeError):
    """The provider failed or is unreachable. The pipeline falls back to escalation."""


class ProviderTimeout(ProviderError):
    """The provider exceeded the configured timeout."""


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ProviderRequest:
    messages: tuple[ChatMessage, ...]
    temperature: float = 0.1
    timeout_s: float = 8.0
    json_mode: bool = True


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    model_id: str
    usage: dict[str, int] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model_id: str

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return the raw model text. Raise ProviderTimeout or ProviderError on failure."""
        ...

    def is_reachable(self) -> bool: ...
