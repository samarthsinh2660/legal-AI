"""Local embeddings -- the model is a config choice, not a hardcoded string.

Set EMBEDDING_MODEL to override the default. Changing it requires
re-embedding the whole corpus (scripts/reembed_corpus.py), because stored
vectors and the column's declared dimension must agree, and vectors from
different models are not comparable.

Model selection rationale and benchmark numbers live in
docs/phases/PHASE_2_QUERY_RETRIEVAL.md.
"""

from __future__ import annotations

import os
from functools import lru_cache

# Registered models and their output dimensions. A model must be listed
# here before use -- guessing a dimension silently corrupts the vector
# column.
KNOWN_MODELS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
}

DEFAULT_MODEL = "all-mpnet-base-v2"


def model_name() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)


def embedding_dim() -> int:
    name = model_name()
    if name not in KNOWN_MODELS:
        raise KeyError(
            f"Embedding model {name!r} is not registered in KNOWN_MODELS. "
            f"Add it with its true output dimension before using it. "
            f"Known: {sorted(KNOWN_MODELS)}"
        )
    return KNOWN_MODELS[name]


@lru_cache(maxsize=2)
def _model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name)


def embed(text: str) -> list[float]:
    vector = _model(model_name()).encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_many(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Batch equivalent of embed(), for bulk work like a corpus re-embed.

    Several times faster than per-document calls over a large corpus.
    """
    if not texts:
        return []
    vectors = _model(model_name()).encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
    )
    return [v.tolist() for v in vectors]
