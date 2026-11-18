# ADR-006: Hybrid retrieval without a vector database

- Status: Accepted by Track B (Amulya Mohan), 2026-11-17. Open for team review.
- Context owner: Track B (policy retrieval).

## Context

The design document proposed ChromaDB with `bge-small-en-v1.5` embeddings. The enhancement proposal
asked for hybrid retrieval: strict metadata filtering, keyword (BM25-style) search, and vector search.

The corpus is small: one policy version has 9 to 11 clauses, and a request only ever searches the
single applicable pack and version. ChromaDB plus a local sentence-transformers model would add
roughly a gigabyte of dependencies (PyTorch) to the Docker image and CI, and slow every cold start.
It would also not change the results for a corpus this small.

## Decision

- Filter first: candidates are only clauses whose `pack_id` and `version` match the resolved
  `PolicySnapshot`. Wrong-jurisdiction and wrong-version clauses cannot be retrieved or cited.
- Score with BM25 over trusted query terms (exception code + detection-detail keys; never employee
  notes) and with cosine similarity from a pluggable `Embedder`.
- Keep a clause only if it clears the BM25 floor or the vector floor; otherwise escalate as
  "no supporting policy". Fuse rankings with reciprocal rank fusion (k = 60).
- Embedders: `HashingEmbedder` (default; offline, deterministic, no dependencies; word and
  character n-gram hashing, so lexical rather than deep semantic similarity) and `OllamaEmbedder`
  (`nomic-embed-text` through the local Ollama server). Each embedder carries its own floor.
- If embeddings fail, retrieval falls back to BM25 only, and the mode is recorded in `gate_checks`.

## Consequences

- No extra runtime dependencies; tests and CI run fully offline and deterministically.
- In-memory scoring is linear in clause count. Revisit a vector database if the corpus grows to
  thousands of chunks (many packs, versions, or long handbooks).
- Floors were calibrated on the shipped packs and must be rechecked by the B-05 retrieval
  evaluation whenever packs or embedders change.
