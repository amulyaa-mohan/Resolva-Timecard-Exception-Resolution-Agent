"""Shared pytest fixtures. Synthetic data only."""

from __future__ import annotations

import pytest

from app.core.config import BACKEND_DIR, Settings
from app.core.contracts import CaseContext
from app.policies.registry import PolicyRegistry
from tests.factories import make_case


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="test", llm_provider="mock")


@pytest.fixture
def registry() -> PolicyRegistry:
    return PolicyRegistry.from_directory(BACKEND_DIR / "policies")


@pytest.fixture
def policy(registry):
    return registry.get("IN-KA", "2025.1")


@pytest.fixture
def case() -> CaseContext:
    return make_case()
