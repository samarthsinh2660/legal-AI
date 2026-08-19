from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.evidence_builder import build_evidence, to_evidence
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, doc_type: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://indiacode.nic.in/x", source_type="primary"),
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


def test_to_evidence_carries_identity_and_provenance():
    evidence = to_evidence(_doc("test:e-1", "section", "Section 1", "Body text."))

    assert evidence.document_id == "test:e-1"
    assert evidence.title == "Section 1"
    assert evidence.document_type == "section"
    assert evidence.content == "Body text."
    assert evidence.provenance.source.url == "https://indiacode.nic.in/x"


def test_build_evidence_preserves_the_given_order(conn):
    upsert_document(conn, _doc("test:e-a", "act", "A", "text a"))
    upsert_document(conn, _doc("test:e-b", "act", "B", "text b"))

    evidence = build_evidence(conn, ["test:e-b", "test:e-a"])

    assert [e.document_id for e in evidence] == ["test:e-b", "test:e-a"]


def test_build_evidence_skips_ids_with_no_stored_document(conn):
    upsert_document(conn, _doc("test:e-c", "act", "C", "text c"))

    evidence = build_evidence(conn, ["test:e-c", "test:e-missing"])

    assert [e.document_id for e in evidence] == ["test:e-c"]


def test_build_evidence_returns_empty_for_no_ids(conn):
    assert build_evidence(conn, []) == []
