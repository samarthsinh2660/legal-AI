"""The model server must agree with the model it replaces.

This is the claim the whole change rests on. If the server's vectors differ
from the ones in the corpus, every stored vector is wrong and search breaks
until 35,601 sections and 332,025 chunks are re-embedded -- so it is worth
proving against a real server rather than asserting in a docstring.

Skipped unless one is running. Bring both up with:

    docker compose up -d embedder reranker

and point the suite at them the way the services do:

    LEGAL_AI_EMBED_URL=http://localhost:8085 \\
    LEGAL_AI_RERANK_URL=http://localhost:8086 pytest tests/inference
"""

from __future__ import annotations

import os
import urllib.request

import pytest

from legal_ai.inference import client

EMBED_URL = os.environ.get("LEGAL_AI_EMBED_URL")
RERANK_URL = os.environ.get("LEGAL_AI_RERANK_URL")


def _up(url: str | None) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


embedder = pytest.mark.skipif(not _up(EMBED_URL), reason="no embedding server")
reranker = pytest.mark.skipif(not _up(RERANK_URL), reason="no reranking server")

# Real shapes: a query, a short section, and one long enough to truncate.
TEXTS = [
    "what is the punishment under section 138 of the Negotiable Instruments Act",
    "Where any cheque drawn by a person on an account maintained by him is "
    "returned by the bank unpaid, such person shall be deemed to have "
    "committed an offence.",
    "Provided that nothing contained in this section shall apply unless " * 200,
]


def _local_embed(texts):
    """The in-process path, with the service switched off for this call."""
    saved = os.environ.pop("LEGAL_AI_EMBED_URL", None)
    try:
        from legal_ai.knowledge.static.embeddings import embed_many

        return embed_many(texts)
    finally:
        if saved is not None:
            os.environ["LEGAL_AI_EMBED_URL"] = saved


@embedder
def test_the_server_returns_the_dimension_the_column_declares():
    from legal_ai.knowledge.static.embeddings import embedding_dim

    vectors = client.embed_texts(["hello"], EMBED_URL)
    assert len(vectors[0]) == embedding_dim()


@embedder
def test_server_vectors_match_the_ones_the_corpus_was_built_with():
    served = client.embed_texts(TEXTS, EMBED_URL)
    local = _local_embed(TEXTS)

    for index, (a, b) in enumerate(zip(local, served)):
        cosine = sum(x * y for x, y in zip(a, b))
        assert cosine > 0.9999, f"text {index} diverged: cosine {cosine}"


@embedder
def test_served_vectors_are_normalised():
    """Stored vectors are unit length. One that is not scores against them
    as though it came from a different model."""
    (vector,) = client.embed_texts([TEXTS[0]], EMBED_URL)
    length = sum(x * x for x in vector) ** 0.5
    assert abs(length - 1.0) < 1e-4


@embedder
def test_a_batch_larger_than_the_servers_limit_still_works():
    """50 is the shortlist size, and TEI refuses more than 32 at once."""
    vectors = client.embed_texts([f"section {n}" for n in range(50)], EMBED_URL)
    assert len(vectors) == 50
    assert len({tuple(v[:4]) for v in vectors}) > 1  # not all the same vector


@reranker
def test_the_server_ranks_the_shortlist_the_way_the_local_model_does():
    """Only the order is used -- hybrid.py keeps the ids and drops the
    scores -- so the order is what has to agree. The scores do not: TEI
    returns a sigmoid where CrossEncoder returns the raw logit."""
    from legal_ai.retrieval.rerank import rerank

    query = "punishment for dishonour of a cheque"
    candidates = [
        ("act:138", "Punishment for dishonour of cheque for insufficiency of funds."),
        ("act:420", "Cheating and dishonestly inducing delivery of property."),
        ("act:139", "It shall be presumed that the holder received the cheque for a debt."),
        ("act:001", "Short title, extent and commencement of this Act."),
    ]

    saved = os.environ.pop("LEGAL_AI_RERANK_URL", None)
    try:
        local = [document_id for document_id, _score in rerank(query, candidates)]
    finally:
        if saved is not None:
            os.environ["LEGAL_AI_RERANK_URL"] = saved

    scores = client.rerank_texts(query, [p for _i, p in candidates], RERANK_URL)
    served = [
        document_id
        for document_id, _score in sorted(
            zip((i for i, _p in candidates), scores), key=lambda pair: -pair[1]
        )
    ]

    assert local == served


@reranker
def test_reranking_more_candidates_than_one_batch_scores_the_right_passages():
    """The offset bug, against a real server: a wrong index would put a
    plausible ranking on the wrong documents."""
    query = "punishment for dishonour of a cheque"
    texts = [f"unrelated filler about municipal drainage number {n}" for n in range(45)]
    texts.append("Punishment for dishonour of cheque for insufficiency of funds.")

    scores = client.rerank_texts(query, texts, RERANK_URL)

    assert len(scores) == len(texts)
    assert scores.index(max(scores)) == len(texts) - 1
