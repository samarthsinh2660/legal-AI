from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.evidence_builder import (
    ELLIPSIS,
    EXTRACT_CHARS,
    build_evidence,
    to_evidence,
)
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

def _chunk(conn, document_id: str, ordinal: int, text: str,
           label: str | None = None, vector: list[float] | None = None) -> None:
    """A chunk with an embedding, so it is a candidate for the nearest-passage
    query -- the path that was dropping the provisos. `vector` fixes the
    similarity order; the default is a unit vector on the ordinal's axis."""
    from legal_ai.knowledge.static.db import EMBEDDING_DIM

    if vector is None:
        vector = [0.0] * EMBEDDING_DIM
        vector[ordinal] = 1.0
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document_chunks (chunk_id, document_id, ordinal, text, label, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (f"{document_id}#{ordinal}", document_id, ordinal, text, label, str(vector)),
        )
    conn.commit()


def _near_and_far(query: str) -> tuple[list[float], list[float]]:
    """The query's own embedding and its opposite, so a test can decide which
    chunks are nearest without depending on what the model thinks."""
    from legal_ai.knowledge.static.embeddings import embed

    near = list(embed(query))
    return near, [-x for x in near]


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


# --- a judgment reaches the reader as several passages --------------------
#
# The median judgment is 15,196 chars across 18 chunks, and retrieval carried
# one of them: the analyst saw ~5% of every judgment it cited. It cannot be
# carried whole (p95 is 107,100 chars), so it is carried as the nearest few
# chunks in document order.

def test_a_judgment_carries_several_passages_in_document_order(conn):
    near, far = _near_and_far("the holding")
    upsert_document(conn, _doc("test:e-multi", "judgment", "X v. Y", "irrelevant"))
    for ordinal in range(6):
        text = f"Paragraph {ordinal} of the judgment. " * 30
        _chunk(conn, "test:e-multi", ordinal, text,
               vector=near if ordinal in (0, 3, 5) else far)

    evidence = build_evidence(conn, ["test:e-multi"], query="the holding")
    content = evidence[0].content

    ordinals = [int(w) for w in content.split() if w.isdigit()]
    assert set(ordinals) == {0, 3, 5}, "the three nearest passages were not carried"
    assert ordinals == sorted(ordinals), "passages are not in document order"


def test_a_gap_between_passages_is_marked(conn):
    near, far = _near_and_far("cheque notice")
    upsert_document(conn, _doc("test:e-gap", "judgment", "G v. H", "irrelevant"))
    _chunk(conn, "test:e-gap", 0, "First passage about a dishonoured cheque. " * 15, vector=near)
    for ordinal in (1, 2, 3, 4):
        _chunk(conn, "test:e-gap", ordinal, "Unrelated procedural history. " * 15, vector=far)
    _chunk(conn, "test:e-gap", 5, "Second passage about the notice period. " * 15, vector=near)

    evidence = build_evidence(conn, ["test:e-gap"], query="cheque notice")

    assert ELLIPSIS in evidence[0].content


def test_adjacent_passages_are_joined_without_a_gap_marker(conn):
    near, far = _near_and_far("the notice")
    upsert_document(conn, _doc("test:e-adj", "judgment", "A v. B", "irrelevant"))
    _chunk(conn, "test:e-adj", 0, "Notice was given on the first day. " * 15, vector=near)
    _chunk(conn, "test:e-adj", 1, "Notice was repeated the next day. " * 15, vector=near)
    _chunk(conn, "test:e-adj", 2, "Unrelated costs order. " * 15, vector=far)

    evidence = build_evidence(conn, ["test:e-adj"], query="the notice")

    assert ELLIPSIS not in evidence[0].content


def test_a_judgment_stays_within_its_character_budget(conn):
    upsert_document(conn, _doc("test:e-budget", "judgment", "B v. C", "irrelevant"))
    for ordinal in range(12):
        _chunk(conn, "test:e-budget", ordinal, f"Chunk {ordinal}. " * 200)

    evidence = build_evidence(conn, ["test:e-budget"], query="chunk")

    assert len(evidence[0].content) <= EXTRACT_CHARS


def test_location_marks_where_the_extract_begins(conn):
    near, _ = _near_and_far("held")
    upsert_document(conn, _doc("test:e-loc", "judgment", "L v. M", "irrelevant"))
    _chunk(conn, "test:e-loc", 0, "Held on the first point. " * 15, label="7", vector=near)
    _chunk(conn, "test:e-loc", 1, "Held on the second point. " * 15, label="8", vector=near)

    evidence = build_evidence(conn, ["test:e-loc"], query="held")

    assert evidence[0].location is not None
    assert evidence[0].location.paragraph == 7
