"""Local embeddings — one default model, no benchmarking.

Phase 2 benchmarks InLegalBERT vs. general-purpose embeddings
(docs/LEGAL_DATA_SOURCES.md §18); this is deliberately not that — a
single reasonable, CPU-friendly default for Phase 1's basic index.
"""

from __future__ import annotations

from functools import lru_cache

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> list[float]:
    vector = _model().encode(text, normalize_embeddings=True)
    return vector.tolist()
