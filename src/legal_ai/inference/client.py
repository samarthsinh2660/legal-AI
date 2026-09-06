"""HTTP client for a Text Embeddings Inference server.

TEI, not TGI: TGI serves generation, which we do not run locally --
generation goes to Gemini over HTTP already. What we run locally is an
embedder and a cross-encoder, which is what TEI serves.

One model per server, so there are two of them: `/embed` on one and
`/rerank` on the other.

Verified against the local models before this was written (2026-09-06):

    embeddings   worst cosine 0.999999955, worst |diff| 1.57e-07
    reranking    ordering and top-10 identical

The corpus therefore does not need re-embedding, which is the one thing
that would have made this change unaffordable -- every vector in it came
from all-mpnet-base-v2 and a different model means 35,601 sections and
332,025 chunks re-embedded before search works at all.

The reranker's *scores* do differ: TEI returns a sigmoid where the local
CrossEncoder returns the raw logit, so -6.2726 becomes 0.0019. Harmless
here because the only caller discards the score and keeps the order --
see retrieval.hybrid, which reranks and then takes document ids alone. If
a caller ever needs the value, that is the line to check first.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# TEI refuses a client batch larger than this by default (`413 Payload Too
# Large`), and our shortlist is 50. Chunked here rather than raised on the
# server so the client is correct against a server it did not configure.
MAX_BATCH = 32

# Generous: 50 candidates through the cross-encoder took 6s on CPU, and a
# cold server has a model to load. Not unbounded -- a hung inference server
# must surface as an error, not as a run that never ends.
TIMEOUT_SECONDS = 120


class InferenceError(RuntimeError):
    """The model server could not be reached, or refused the request.

    Deliberately not caught into a local fallback. A worker configured for
    a service is sized for 163 MB; quietly loading 1.3 GB of models instead
    would trade a loud failure for an OOM kill later, on a different
    machine, with nothing pointing back here.
    """


def embed_url() -> str | None:
    return os.environ.get("LEGAL_AI_EMBED_URL") or None


def rerank_url() -> str | None:
    return os.environ.get("LEGAL_AI_RERANK_URL") or None


def _post(url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read()[:200].decode(errors="replace")
        raise InferenceError(f"{url} answered {error.code}: {detail}") from None
    except Exception as error:
        raise InferenceError(f"{url} unreachable: {error}") from None


def embed_texts(texts: list[str], base_url: str) -> list[list[float]]:
    """Embeddings for `texts`, in order.

    `normalize` matches what the corpus was built with -- the local path
    encodes with `normalize_embeddings=True`, and an unnormalised vector
    would score against stored ones as if it were a different model.

    `truncate` is what keeps a long section from being refused outright;
    mpnet's window is 384 tokens and the local path truncates silently too.
    """
    vectors: list[list[float]] = []
    for start in range(0, len(texts), MAX_BATCH):
        batch = texts[start : start + MAX_BATCH]
        vectors.extend(
            _post(
                f"{base_url.rstrip('/')}/embed",
                {"inputs": batch, "normalize": True, "truncate": True},
            )
        )
    return vectors


def rerank_texts(query: str, texts: list[str], base_url: str) -> list[float]:
    """A score per text, in the order the texts were given.

    TEI returns results sorted by score and carrying the index they came
    from, which is the opposite of what the caller wants -- so this puts
    them back in input order and lets the caller sort. Batching makes that
    mandatory rather than merely tidy: an index is relative to its own
    batch, so without the offset every chunk past the first would score the
    wrong passage.
    """
    scores = [0.0] * len(texts)
    for start in range(0, len(texts), MAX_BATCH):
        batch = texts[start : start + MAX_BATCH]
        for item in _post(
            f"{base_url.rstrip('/')}/rerank",
            {"query": query, "texts": batch, "truncate": True},
        ):
            scores[start + item["index"]] = float(item["score"])
    return scores
