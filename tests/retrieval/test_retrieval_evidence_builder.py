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


# --- a statute section reaches the reader whole ---------------------------
#
# 19% of the 35,601 sections we hold are stored as more than one chunk, and
# retrieval carried only the nearest one. Section 138 NI Act is the case that
# exposed it: the offence is in the first chunk and the provisos that decide
# whether a complaint is valid -- the thirty-day notice, the fifteen-day
# window -- are in the second, so answers described the offence and omitted
# every filing requirement.

def _chunk(conn, document_id: str, ordinal: int, text: str) -> None:
    """A chunk with an embedding, so it is a candidate for the nearest-passage
    query -- the path that was dropping the provisos."""
    from legal_ai.knowledge.static.db import EMBEDDING_DIM

    vector = [0.0] * EMBEDDING_DIM
    vector[ordinal] = 1.0
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document_chunks (chunk_id, document_id, ordinal, text, embedding) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (f"{document_id}#{ordinal}", document_id, ordinal, text, str(vector)),
        )
    conn.commit()


def test_a_multi_chunk_section_is_carried_whole(conn):
    # Longer than `passage_chars`, so the old path could not have carried
    # it whole by accident.
    whole = "The offence is committed when a cheque bounces. " * 60 + \
            "Provided that the payee gives notice within thirty days."
    upsert_document(conn, _doc("test:e-sec", "section", "s.138", whole))
    _chunk(conn, "test:e-sec", 0, whole[:1400])
    _chunk(conn, "test:e-sec", 1, whole[1400:])

    evidence = build_evidence(conn, ["test:e-sec"], query="cheque bounce")

    assert "thirty days" in evidence[0].content
    assert evidence[0].content == whole


def test_a_section_too_long_to_carry_whole_falls_back_to_the_passage(conn):
    """The budget is not a promise. A very long section still gets the
    matching passage rather than blowing the prompt."""
    from legal_ai.retrieval.evidence_builder import SECTION_CHARS

    long_text = "x" * (SECTION_CHARS + 500)
    upsert_document(conn, _doc("test:e-long", "section", "long", long_text))
    _chunk(conn, "test:e-long", 0, long_text[:300])

    evidence = build_evidence(conn, ["test:e-long"], query="anything")

    assert len(evidence[0].content) <= SECTION_CHARS


def test_a_judgment_still_gets_only_the_matching_passage(conn):
    """Judgments run to hundreds of thousands of characters. Carrying one
    whole would spend the entire prompt on a single authority."""
    body = "Held that the appeal is allowed. " * 300
    upsert_document(conn, _doc("test:e-judg", "judgment", "X v. Y", body))
    _chunk(conn, "test:e-judg", 0, body[:400])

    evidence = build_evidence(conn, ["test:e-judg"], query="appeal allowed")

    assert len(evidence[0].content) < len(body)
