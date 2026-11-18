"""Embedders for the vector side of hybrid retrieval (B-03).

HashingEmbedder is offline, deterministic and dependency-free (word + character n-gram feature
hashing). It captures lexical similarity and spelling variants, not deep semantics.
OllamaEmbedder uses a real embedding model when a local Ollama server is available.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.retrieval.keyword import tokens


class EmbeddingError(RuntimeError):
    """Embeddings unavailable. Retrieval falls back to BM25 only."""


class Embedder(Protocol):
    name: str
    # Minimum cosine similarity for a clause to count as relevant; scales differ per embedder.
    vector_floor: float

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class HashingEmbedder:
    name = "hashing-ngram-v1"
    vector_floor = 0.35  # calibrated on shipped packs; see ADR-006

    def __init__(self, dims: int = 1024) -> None:
        self.dims = dims

    def _features(self, text: str) -> list[str]:
        words = tokens(text)
        feats = [f"w:{w}" for w in words]
        feats += [f"b:{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        for w in words:
            padded = f"#{w}#"
            feats += [f"c:{padded[i : i + 4]}" for i in range(max(len(padded) - 3, 1))]
        return feats

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            for feat in self._features(text):
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dims
                vec[idx] += 1.0 if digest[4] & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OllamaEmbedder:
    name = "ollama"
    # Calibrated 2026-11-17 for nomic-embed-text on the shipped packs: relevant clauses 0.745-0.882,
    # unrelated p90 0.672. Recalibrate if the embedding model changes (see ADR-006).
    vector_floor = 0.72

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout_s: float = 5.0,
        keep_alive: str = "30m",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url, self.model, self.timeout_s = base_url.rstrip("/"), model, timeout_s
        self.keep_alive = keep_alive
        self.name = f"ollama:{model}"
        self._client = httpx.Client(transport=transport)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": list(texts), "keep_alive": self.keep_alive},
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise EmbeddingError(f"Ollama embeddings unavailable ({type(exc).__name__})") from exc
        if len(vectors) != len(texts):
            raise EmbeddingError("Ollama returned the wrong number of embeddings")
        return vectors


def build_embedder(settings) -> Embedder:
    """Embedder from settings. Ollama embeddings fall back to BM25-only at query time if down."""
    if settings.embedding_provider == "ollama":
        return OllamaEmbedder(
            base_url=settings.ollama_base_url, model=settings.ollama_embedding_model
        )
    return HashingEmbedder()
