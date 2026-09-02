"""Evidence carries what the source panel renders.

design/UX_FLOWS.md: clicking [1] opens a panel with court, case name,
citation, the relevant paragraph extract, and Open. Every one of those has
to travel with the Evidence.
"""

from legal_ai.knowledge.static.db import get_connection
from legal_ai.retrieval.evidence_builder import PASSAGE_CHARS, _location, build_evidence
from legal_ai.retrieval.hybrid import hybrid_search
from legal_ai.schemas.evidence import Evidence

RERA_18 = "act:2158:sec-18"


def _conn():
    return get_connection()


def test_location_from_a_numbered_judgment_paragraph():
    location = _location("14")
    assert location.paragraph == 14
    assert location.label == "14"


def test_location_from_a_statutory_marker_sets_no_paragraph():
    # Coercing "(a)" to an integer would invent a paragraph that does not
    # exist in the document.
    location = _location("(a)")
    assert location.paragraph is None
    assert location.label == "(a)"


def test_location_of_nothing_is_none():
    assert _location(None) is None
    assert _location("") is None


def test_evidence_carries_court_and_citation():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM documents "
                "WHERE court IS NOT NULL AND citation IS NOT NULL LIMIT 1"
            )
            row = cur.fetchone()
        if row is None:
            import pytest

            pytest.skip("corpus holds no document with both court and citation")
        evidence = build_evidence(conn, [row[0]])
    finally:
        conn.close()
    assert evidence[0].court
    assert evidence[0].citation


def test_a_search_result_carries_the_matched_passage_not_the_whole_document():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT full_text FROM documents WHERE document_id = %s", (RERA_18,))
            full_text = cur.fetchone()[0]
        evidence = build_evidence(conn, [RERA_18], query="refund of amount by promoter")
    finally:
        conn.close()
    assert len(evidence[0].content) <= PASSAGE_CHARS
    assert len(evidence[0].content) < len(full_text) or len(full_text) <= PASSAGE_CHARS


def test_without_a_query_the_whole_document_is_carried():
    # get_section and get_judgment resolve a known id: the document IS the
    # answer, so it must not be truncated to a passage.
    conn = _conn()
    try:
        evidence = build_evidence(conn, [RERA_18])
    finally:
        conn.close()
    assert evidence[0].content


def test_hybrid_search_results_are_passages_with_provenance():
    # A judgment arrives as its nearest few passages, not one -- so the bound
    # is the extract budget, not a single passage.
    from legal_ai.retrieval.evidence_builder import EXTRACT_CHARS

    results = hybrid_search("refund when builder fails to give possession", limit=3)
    assert results
    for item in results:
        assert isinstance(item, Evidence)
        assert len(item.content) <= EXTRACT_CHARS
        assert item.provenance.source.url
        assert item.document_id


def test_a_missing_document_is_skipped_rather_than_raising():
    conn = _conn()
    try:
        evidence = build_evidence(conn, ["act:0:sec-does-not-exist", RERA_18])
    finally:
        conn.close()
    assert len(evidence) == 1
    assert evidence[0].document_id == RERA_18


def test_requested_order_is_preserved():
    conn = _conn()
    try:
        ids = ["act:2158:sec-3", RERA_18, "act:2158:sec-4"]
        evidence = build_evidence(conn, ids, query="registration and refund")
    finally:
        conn.close()
    assert [e.document_id for e in evidence] == ids
