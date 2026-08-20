"""Cross-encoder reranking of a retrieved shortlist.

Vector search is a bi-encoder: query and document are embedded separately,
so a document's vector is fixed before any query exists and cannot
emphasise what a particular question is asking about. A cross-encoder
reads query and passage together in one pass, letting attention run across
both -- far more accurate, but it costs a forward pass per pair, so it is
affordable only over a shortlist, never the whole corpus.

Reranking reorders; it never recovers a document the retriever missed. If
the right document is not in the shortlist, no reranker will find it.

Set RERANK_MODEL to switch models. Benchmark numbers are in
docs/phases/PHASE_2_QUERY_RETRIEVAL.md.
"""

from __future__ import annotations

import os
from functools import lru_cache

# Registered models, with a note on the trade-off each represents. A model
# must be listed here before use so a typo cannot silently download an
# arbitrary model and rank results with it.
KNOWN_RERANKERS: dict[str, str] = {
    "cross-encoder/ms-marco-MiniLM-L-12-v2": "stronger; roughly twice the latency of L-6",
    "cross-encoder/ms-marco-MiniLM-L-6-v2": "faster; measurably weaker ranking",
}

DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L-12-v2"

# Cross-encoder input is query + passage, so this bounds the per-pair cost.
MAX_LENGTH = 512


def reranker_name() -> str:
    name = os.environ.get("RERANK_MODEL", DEFAULT_RERANKER)
    if name not in KNOWN_RERANKERS:
        raise KeyError(
            f"Reranker {name!r} is not registered in KNOWN_RERANKERS. "
            f"Known: {sorted(KNOWN_RERANKERS)}"
        )
    return name


@lru_cache(maxsize=2)
def _model(name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(name, device="cpu", max_length=MAX_LENGTH)


def rerank(
    query: str,
    candidates: list[tuple[str, str]],
    limit: int | None = None,
    batch_size: int = 16,
) -> list[tuple[str, float]]:
    """Rescore `candidates` -- (document_id, passage) -- against `query`.

    Returns (document_id, score) sorted best first, where a higher score is
    better. Note this is the opposite direction to vector distance.
    """
    if not candidates:
        return []

    scores = _model(reranker_name()).predict(
        [(query, passage) for _doc_id, passage in candidates],
        batch_size=batch_size,
        show_progress_bar=False,
    )
    ranked = sorted(
        ((doc_id, float(score)) for (doc_id, _passage), score in zip(candidates, scores)),
        key=lambda item: -item[1],
    )
    return ranked[:limit] if limit is not None else ranked
