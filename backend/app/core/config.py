"""Application configuration. Values come from environment variables or backend/.env.

Scaffold fields (app_name, cors_origins) by Track A; AI/policy fields by Track B (B-01).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Resolva"
    cors_origins: str = "http://localhost:5173"
    environment: Literal["development", "test", "demo"] = "development"

    # AI kill-switch: when false the pipeline escalates every case (rules-only mode).
    ai_enabled: bool = True
    llm_provider: Literal["mock", "ollama", "groq"] = "mock"
    llm_model: str = "mock-resolver-v1"
    llm_timeout_s: float = Field(default=8.0, gt=0, le=60)
    llm_temperature: float = Field(default=0.1, ge=0, le=1)
    llm_max_repair_retries: int = Field(default=1, ge=0, le=3)
    ollama_base_url: str = "http://localhost:11434"
    # Read from the environment only; never commit a real key.
    groq_api_key: str | None = None

    # Evidence gate: model confidence is necessary, never sufficient.
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    retrieval_top_k: int = Field(default=4, ge=1, le=20)

    policies_dir: Path = BACKEND_DIR / "policies"
    prompts_dir: Path = BACKEND_DIR / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
