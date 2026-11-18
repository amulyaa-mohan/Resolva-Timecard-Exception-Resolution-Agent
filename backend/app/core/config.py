"""Application configuration. Values come from environment variables or backend/.env.

Scaffold fields (app_name, cors_origins) by Track A; AI/policy fields by Track B (B-01).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    # None = provider default (mock-resolver-v1, qwen2.5:7b-instruct, llama-3.1-8b-instant).
    llm_model: str | None = None
    llm_timeout_s: float = Field(default=8.0, gt=0, le=60)
    llm_temperature: float = Field(default=0.1, ge=0, le=1)
    llm_max_repair_retries: int = Field(default=1, ge=0, le=3)
    # propose_v2 adds trusted plain-language facts; v1 kept for comparison (evals/reports).
    prompt_version: Literal["propose_v1", "propose_v2", "propose_v3"] = "propose_v3"
    ollama_base_url: str = "http://localhost:11434"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Read from the environment only; never commit a real key. SecretStr keeps it out of logs/repr.
    groq_api_key: SecretStr | None = None

    # Retrieval embeddings: "hashing" is offline and dependency-free; "ollama" calls the local server.
    embedding_provider: Literal["hashing", "ollama"] = "hashing"
    ollama_embedding_model: str = "nomic-embed-text"

    # Evidence gate: model confidence is necessary, never sufficient.
    confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    retrieval_top_k: int = Field(default=4, ge=1, le=20)

    policies_dir: Path = BACKEND_DIR / "policies"
    prompts_dir: Path = BACKEND_DIR / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
