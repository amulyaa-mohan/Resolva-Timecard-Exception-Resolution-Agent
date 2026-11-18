"""Per-request trace ids, propagated to logs, LLM traces, and audit events."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

TRACE_HEADER = "X-Trace-Id"
_trace_id: ContextVar[str | None] = ContextVar("resolva_trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """Current request trace id, or a fresh one outside a request."""
    return _trace_id.get() or new_trace_id()


def set_trace_id(value: str) -> None:
    _trace_id.set(value)
