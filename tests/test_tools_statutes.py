from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.statutes import get_section, get_statute, search_statutes


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _doc(doc_id: str, doc_type: str, title: str, text: str, act_id: str | None = None) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        act_id=act_id,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_get_statute_returns_evidence_with_identity_fields(conn):
    act = _doc("test:act-1", "act", "Test Act, 2026", "An Act to test things.")
    upsert_document(conn, act, embedding=_sparse_vector((0, 1.0)))

    evidence = get_statute("test:act-1")

    assert evidence is not None
    assert evidence.document_id == "test:act-1"
    assert evidence.title == "Test Act, 2026"
    assert evidence.document_type == "act"
    assert evidence.content == "An Act to test things."


def test_get_statute_returns_none_for_missing_act():
    assert get_statute("test:does-not-exist") is None


def test_get_section_builds_compound_document_id(conn):
    section = _doc("test:act-1:sec-3", "section", "Section 3", "Prior registration.", act_id="test:act-1")
    upsert_document(conn, section, embedding=_sparse_vector((1, 1.0)))

    evidence = get_section("test:act-1", "3")

    assert evidence is not None
    assert evidence.document_id == "test:act-1:sec-3"
    assert evidence.content == "Prior registration."


def test_search_statutes_excludes_non_statute_document_types(conn):
    # search_statutes embeds the query text for real (real sentence-
    # transformers model, real ~35k-document corpus in this DB) — a
    # synthetic sparse vector would never reliably rank near the top of
    # that, so seed rows with a real embedding of the exact query text
    # instead, which guarantees distance ~0 regardless of corpus size.
    distinctive_text = "zzqvxk flibbertigibbet possession dispute remedy provision"
    vector = embed(distinctive_text)
    act = _doc("test:act-2", "act", "Searchable Act", distinctive_text)
    judgment = _doc("test:j-1", "judgment", "Some Judgment", distinctive_text)
    upsert_document(conn, act, embedding=vector)
    upsert_document(conn, judgment, embedding=vector)

    results = search_statutes(distinctive_text, limit=10)

    result_ids = {e.document_id for e in results}
    assert "test:act-2" in result_ids
    assert "test:j-1" not in result_ids
