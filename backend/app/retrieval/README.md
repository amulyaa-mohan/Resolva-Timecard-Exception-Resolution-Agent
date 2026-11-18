# Retrieval

Track B: clause ingestion, metadata filtering and keyword/vector retrieval.

Implemented (B-03): `hybrid.retrieve` filters to the applicable pack and version, scores with BM25 (`keyword.py`) and embeddings (`vector.py`), and fuses rankings. See docs/shared/adr/ADR-006.
