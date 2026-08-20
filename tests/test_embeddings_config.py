import pytest

from legal_ai.knowledge.static import embeddings


def test_known_models_declare_their_dimensions():
    assert embeddings.KNOWN_MODELS["all-MiniLM-L6-v2"] == 384
    assert embeddings.KNOWN_MODELS["all-mpnet-base-v2"] == 768


def test_model_name_defaults_to_the_configured_default():
    assert embeddings.model_name() == embeddings.DEFAULT_MODEL


def test_model_name_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    assert embeddings.model_name() == "all-MiniLM-L6-v2"
    assert embeddings.embedding_dim() == 384


def test_embedding_dim_tracks_the_selected_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL", "all-mpnet-base-v2")
    assert embeddings.embedding_dim() == 768


def test_unknown_model_is_rejected_rather_than_guessed(monkeypatch):
    # A wrong dimension corrupts the vector column, so an unregistered
    # model must fail loudly rather than be assumed.
    monkeypatch.setenv("EMBEDDING_MODEL", "some-model-nobody-registered")
    with pytest.raises(KeyError):
        embeddings.embedding_dim()


def test_embed_returns_a_vector_of_the_declared_dimension():
    vector = embeddings.embed("possession of immovable property")
    assert len(vector) == embeddings.embedding_dim()


def test_embed_many_matches_embed_for_the_same_text():
    single = embeddings.embed("dishonour of cheque")
    batched = embeddings.embed_many(["dishonour of cheque"])
    assert len(batched) == 1
    assert len(batched[0]) == len(single)
    assert max(abs(a - b) for a, b in zip(single, batched[0])) < 1e-5


def test_embed_many_returns_one_vector_per_input():
    vectors = embeddings.embed_many(["first text", "second text", "third text"])
    assert len(vectors) == 3
    assert all(len(v) == embeddings.embedding_dim() for v in vectors)


def test_embed_many_of_nothing_is_empty():
    assert embeddings.embed_many([]) == []
