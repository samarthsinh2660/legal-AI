from legal_ai.knowledge.static.db import EMBEDDING_DIM
from legal_ai.knowledge.static.embeddings import embed


def test_embed_returns_a_vector_of_the_expected_dimension():
    vector = embed("adverse possession of immovable property")
    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(x, float) for x in vector)


def test_embed_is_deterministic_for_the_same_text():
    a = embed("Section 6 of the Specific Relief Act")
    b = embed("Section 6 of the Specific Relief Act")
    assert a == b


def test_embed_produces_different_vectors_for_different_text():
    a = embed("adverse possession")
    b = embed("breach of contract damages")
    assert a != b
