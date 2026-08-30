from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.judgments import get_judgment, search_judgments


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _judgment(doc_id: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="judgment",
        title=title,
        court="Test Court",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="Indian Kanoon", url="https://indiankanoon.org/doc/1/", source_type="research"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Public judicial record",
            attribution_required=True,
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


def test_get_judgment_returns_evidence(conn):
    judgment = _judgment("test:j-1", "Alpha Traders vs Beta Logistics", "Full judgment text about alpha traders.")
    upsert_document(conn, judgment, embedding=_sparse_vector((3, 1.0)))

    evidence = get_judgment("test:j-1")

    assert evidence is not None
    assert evidence.document_id == "test:j-1"
    assert evidence.document_type == "judgment"
    assert evidence.content == "Full judgment text about alpha traders."


def test_get_judgment_returns_none_for_missing_judgment():
    assert get_judgment("test:does-not-exist") is None


def test_search_judgments_finds_existing_db_match_without_storing_again(conn):
    judgment = _judgment(
        "test:j-2", "Gamma Housing Society vs Delta Builders", "Full judgment text about gamma housing society."
    )
    upsert_document(conn, judgment, embedding=_sparse_vector((4, 1.0)))

    results = search_judgments("Gamma Housing Society Delta Builders")

    assert len(results) == 1
    assert results[0].document_id == "test:j-2"
    assert results[0].content == "Full judgment text about gamma housing society."


def test_search_judgments_returns_empty_list_for_no_match(conn):
    # A query with no real source behind it and no DB match — this would
    # otherwise fall through to live network sources; searching for
    # nonsense text keeps this test offline in practice for CI, but if a
    # network call does happen, an empty/0 result is still the correct,
    # honest outcome (no fabrication).
    results = search_judgments("Zzqvxk Nonexistent Fabricated Case Ptyltd", year=1900)
    assert results == []
