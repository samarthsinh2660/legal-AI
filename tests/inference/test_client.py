"""The model server client.

Every case here runs against a fake server, because what can go wrong is
the shape of the conversation -- batching, index offsets, failure -- not
the arithmetic inside a model. The claim that the server and the local
model agree is a different question and is tested in
tests/inference/test_equivalence.py, against a real one.
"""

from __future__ import annotations

import json

import pytest

from legal_ai.inference import client


@pytest.fixture
def server(monkeypatch):
    """Records every request, and replies however the test says."""

    calls: list[dict] = []

    def build(reply):
        def fake_post(url, payload):
            calls.append({"url": url, **payload})
            return reply(payload) if callable(reply) else reply

        monkeypatch.setattr(client, "_post", fake_post)
        return calls

    return build


# --- embeddings ------------------------------------------------------------


def test_a_single_text_comes_back_as_one_vector(server):
    server(lambda payload: [[0.1, 0.2]] * len(payload["inputs"]))
    assert client.embed_texts(["hello"], "http://tei") == [[0.1, 0.2]]


def test_the_corpus_normalisation_is_asked_for(server):
    """The stored vectors were normalised. An unnormalised query vector
    scores against them as though it came from a different model."""
    calls = server(lambda payload: [[0.0]] * len(payload["inputs"]))
    client.embed_texts(["hello"], "http://tei")
    assert calls[0]["normalize"] is True


def test_long_input_is_truncated_rather_than_refused(server):
    """mpnet's window is 384 tokens and the local path truncates silently.
    Without this a long section is a 413 instead of an embedding."""
    calls = server(lambda payload: [[0.0]] * len(payload["inputs"]))
    client.embed_texts(["x" * 100_000], "http://tei")
    assert calls[0]["truncate"] is True


def test_more_texts_than_a_batch_are_split_and_rejoined_in_order(server):
    """TEI refuses a client batch over 32 with a 413, and the shortlist is
    50. The pieces have to come back in the order they went out."""
    calls = server(lambda payload: [[float(len(t))] for t in payload["inputs"]])

    texts = ["x" * n for n in range(1, 71)]
    vectors = client.embed_texts(texts, "http://tei")

    assert len(calls) == 3  # 32 + 32 + 6
    assert [len(c["inputs"]) for c in calls] == [32, 32, 6]
    assert vectors == [[float(n)] for n in range(1, 71)]


def test_a_trailing_slash_on_the_url_does_not_double_up(server):
    calls = server(lambda payload: [[0.0]])
    client.embed_texts(["hello"], "http://tei/")
    assert calls[0]["url"] == "http://tei/embed"


# --- reranking -------------------------------------------------------------


def test_scores_come_back_in_input_order_not_ranked_order(server):
    """TEI answers sorted best-first, carrying the index it came from. The
    caller pairs scores with its own candidate list, so they have to be put
    back."""
    server([
        {"index": 2, "score": 0.9},
        {"index": 0, "score": 0.5},
        {"index": 1, "score": 0.1},
    ])

    assert client.rerank_texts("q", ["a", "b", "c"], "http://tei") == [0.5, 0.1, 0.9]


def test_a_batched_rerank_offsets_each_index_by_its_batch(server):
    """The bug this exists to prevent: TEI's index is relative to the batch
    it was in, so without the offset every chunk past the first scores the
    wrong passage -- silently, and with a plausible-looking ranking."""

    def reply(payload):
        # Reversed, so an unoffset index would be visibly wrong.
        return [
            {"index": i, "score": float(i)}
            for i in reversed(range(len(payload["texts"])))
        ]

    server(reply)
    scores = client.rerank_texts("q", [f"t{i}" for i in range(40)], "http://tei")

    assert scores[:3] == [0.0, 1.0, 2.0]
    # The second batch holds 8 texts, indexed 0-7 by the server.
    assert scores[32:] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def test_reranking_an_empty_shortlist_asks_the_server_nothing(server):
    calls = server([])
    assert client.rerank_texts("q", [], "http://tei") == []
    assert calls == []


# --- failure ---------------------------------------------------------------


def test_a_server_that_is_down_raises_rather_than_loading_a_model(monkeypatch):
    """A worker configured for a service is sized for 163 MB. Falling back
    to loading 1.3 GB of models would turn a loud failure into an OOM kill
    later, on another machine, with nothing pointing back here."""
    import urllib.request

    def refuse(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)

    with pytest.raises(client.InferenceError) as raised:
        client.embed_texts(["hello"], "http://tei")
    assert "unreachable" in str(raised.value)


def test_an_http_error_carries_the_servers_own_words(monkeypatch):
    import io
    import urllib.error
    import urllib.request

    def fail(*_a, **_k):
        raise urllib.error.HTTPError(
            "http://tei/embed", 413, "Payload Too Large", {},
            io.BytesIO(b'{"error":"batch size 50 > maximum allowed batch size 32"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(client.InferenceError) as raised:
        client.embed_texts(["hello"], "http://tei")
    assert "413" in str(raised.value)
    assert "maximum allowed batch size" in str(raised.value)


# --- the switch ------------------------------------------------------------


def test_no_url_configured_means_no_url(monkeypatch):
    monkeypatch.delenv("LEGAL_AI_EMBED_URL", raising=False)
    monkeypatch.delenv("LEGAL_AI_RERANK_URL", raising=False)
    assert client.embed_url() is None
    assert client.rerank_url() is None


def test_an_empty_string_counts_as_unset(monkeypatch):
    """Compose passes an empty value for a variable that is not set, and an
    empty base URL would build requests to `/embed` on nothing."""
    monkeypatch.setenv("LEGAL_AI_EMBED_URL", "")
    assert client.embed_url() is None
