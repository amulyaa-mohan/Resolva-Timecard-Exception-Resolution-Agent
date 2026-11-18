"""HTTP model providers (B-03): Ollama (local, open-weight) and Groq (hosted, OpenAI-compatible).

Both return raw model text only. Errors never include request bodies, prompts, or credentials.
Tests inject an httpx transport, so no network is needed to exercise these adapters.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.providers.base import (
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeout,
)

REACHABILITY_TIMEOUT_S = 2.0
# Keep the model resident between calls; a cold load of a 7B model takes far longer than 8 s.
OLLAMA_KEEP_ALIVE = "30m"


def _messages(request: ProviderRequest) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in request.messages]


def _post_json(
    client: httpx.Client,
    url: str,
    body: dict[str, Any],
    timeout_s: float,
    headers: dict[str, str] | None = None,
    provider: str = "provider",
) -> dict[str, Any]:
    try:
        response = client.post(url, json=body, headers=headers, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        raise ProviderTimeout(f"{provider} did not respond within {timeout_s:g}s") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"{provider} unreachable ({type(exc).__name__})") from exc
    if response.status_code == 429:
        raise ProviderError(f"{provider} rate limited (HTTP 429)")
    if response.status_code >= 400:
        raise ProviderError(f"{provider} returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(f"{provider} returned a non-JSON response") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"{provider} returned an unexpected response shape")
    return data


class OllamaProvider:
    """Local open-weight models via Ollama's /api/chat with JSON mode."""

    name = "ollama"
    default_model = "qwen2.5:7b-instruct"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id or self.default_model
        self._client = httpx.Client(transport=transport)

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": _messages(request),
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {"temperature": request.temperature},
        }
        if request.json_mode:
            body["format"] = "json"
        data = _post_json(
            self._client, f"{self.base_url}/api/chat", body, request.timeout_s, provider="Ollama"
        )
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise ProviderError("Ollama response has no message content")
        usage = {
            k: v
            for k, v in (
                ("prompt_tokens", data.get("prompt_eval_count")),
                ("completion_tokens", data.get("eval_count")),
            )
            if isinstance(v, int)
        }
        return ProviderResponse(
            text=content, model_id=str(data.get("model", self.model_id)), usage=usage
        )

    def is_reachable(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/api/tags", timeout=REACHABILITY_TIMEOUT_S)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        names = {m.get("name", "") for m in response.json().get("models", [])}
        # Ollama reports "qwen2.5:7b-instruct" and also accepts "name:latest" for bare names.
        return self.model_id in names or f"{self.model_id}:latest" in names


class GroqProvider:
    """Hosted open-weight models via Groq's OpenAI-compatible chat completions API."""

    name = "groq"
    default_model = "llama-3.1-8b-instant"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.groq.com/openai/v1",
        model_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError("Groq API key is not configured")
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id or self.default_model
        self._client = httpx.Client(transport=transport)

    def __repr__(self) -> str:  # never expose the key
        return f"GroqProvider(model_id={self.model_id!r})"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": _messages(request),
            "temperature": request.temperature,
        }
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        data = _post_json(
            self._client,
            f"{self.base_url}/chat/completions",
            body,
            request.timeout_s,
            headers=self._headers(),
            provider="Groq",
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Groq response has no message content") from exc
        if not isinstance(content, str):
            raise ProviderError("Groq response has no message content")
        usage = {k: v for k, v in (data.get("usage") or {}).items() if isinstance(v, int)}
        return ProviderResponse(
            text=content, model_id=str(data.get("model", self.model_id)), usage=usage
        )

    def is_reachable(self) -> bool:
        try:
            response = self._client.get(
                f"{self.base_url}/models", headers=self._headers(), timeout=REACHABILITY_TIMEOUT_S
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200
