"""Hybrid policy retrieval (B-03): metadata filter -> BM25 + vector -> reciprocal rank fusion.

1. Filter: only clauses of the applicable pack AND version are candidates. A clause from another
   jurisdiction or version can never be retrieved, so it can never be cited.
2. Score: BM25 on trusted query terms, cosine similarity on embeddings.
3. Floor: a clause must clear the lexical OR the vector floor; nothing above both floors means
   "no supporting policy" and the pipeline escalates.
4. Fuse: reciprocal rank fusion (k=60) of the two rankings; top-k returned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.contracts import CaseContext, PolicyClause, PolicySnapshot
from app.retrieval.keyword import BM25, QUERY_TEXT, query_tokens
from app.retrieval.vector import Embedder, EmbeddingError, HashingEmbedder, cosine

RRF_K = 60
# Calibrated on the shipped packs: relevant top clauses score BM25 7-15 / cosine 0.4-0.7;
# unrelated clauses score below 3 / 0.3. Re-check with the B-05 retrieval eval when packs change.
BM25_FLOOR = 3.0
# The vector floor belongs to each embedder (Embedder.vector_floor).


@dataclass(frozen=True)
class RetrievedClause:
    clause: PolicyClause
    score: float
    bm25: float
    vector: float | None


@dataclass(frozen=True)
class RetrievalResult:
    clauses: list[RetrievedClause]
    mode: str  # e.g. "hybrid:hashing-ngram-v1" or "bm25-only (embedder unavailable)"


_embedding_cache: dict[tuple[str, str, str], list[float]] = {}


def _clause_text(clause: PolicyClause) -> str:
    return f"{clause.title}. {clause.text}"


def _clause_vectors(embedder: Embedder, clauses: list[PolicyClause]) -> list[list[float]]:
    keys = [(embedder.name, c.chunk_id, _clause_text(c)) for c in clauses]
    missing = [i for i, k in enumerate(keys) if k not in _embedding_cache]
    if missing:
        vectors = embedder.embed([keys[i][2] for i in missing])
        for i, vec in zip(missing, vectors, strict=True):
            _embedding_cache[keys[i]] = vec
    return [_embedding_cache[k] for k in keys]


def _ranks(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    ranks = [0] * len(scores)
    for rank, i in enumerate(order, start=1):
        ranks[i] = rank
    return ranks


def retrieve(
    case: CaseContext,
    policy: PolicySnapshot,
    top_k: int = 4,
    embedder: Embedder | None = None,
) -> RetrievalResult:
    clauses = [
        c for c in policy.clauses if c.pack_id == policy.pack_id and c.version == policy.version
    ]
    if not clauses:
        return RetrievalResult([], "empty")

    bm25 = BM25([_clause_text(c) for c in clauses]).scores(query_tokens(case))

    embedder = embedder or HashingEmbedder()
    vector: list[float] | None
    try:
        query_vec = embedder.embed([QUERY_TEXT[case.code]])[0]
        vector = [cosine(query_vec, v) for v in _clause_vectors(embedder, clauses)]
        if any(math.isnan(v) for v in vector):
            raise EmbeddingError("embedder returned NaN similarities")
        mode = f"hybrid:{embedder.name}"
    except EmbeddingError:
        vector, mode = None, "bm25-only (embedder unavailable)"
    except (
        Exception
    ) as exc:  # malformed vectors (wrong dimensions, wrong types): degrade, never crash
        _embedding_cache.clear()  # cached vectors may be from a different model build
        vector, mode = None, f"bm25-only (embedder error: {type(exc).__name__})"

    bm25_ranks = _ranks(bm25)
    vec_ranks = _ranks(vector) if vector is not None else None
    results = []
    for i, clause in enumerate(clauses):
        vec_score = vector[i] if vector is not None else None
        passes_floor = bm25[i] >= BM25_FLOOR or (
            vec_score is not None and vec_score >= embedder.vector_floor
        )
        if not passes_floor:
            continue
        fused = 1 / (RRF_K + bm25_ranks[i])
        if vec_ranks is not None:
            fused += 1 / (RRF_K + vec_ranks[i])
        results.append(RetrievedClause(clause, fused, bm25[i], vec_score))
    results.sort(key=lambda r: (-r.score, r.clause.clause_id))
    return RetrievalResult(results[:top_k], mode)
