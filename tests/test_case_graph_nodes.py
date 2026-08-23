"""The graph nodes Phase 4 filled in: document extraction and case seeding."""

import pytest

from legal_ai.case.store import create_case, ensure_case_schema, get_case, record_finding
from legal_ai.context.models import DocumentFacts, EstablishedFinding
from legal_ai.graph import nodes
from legal_ai.knowledge.static.db import get_connection


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_case_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM cases WHERE case_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_document_node_uses_facts_already_on_the_channel(monkeypatch):
    # The path a caller who has already extracted takes -- and what keeps
    # the graph runnable without an API key.
    def boom(*a, **k):
        raise AssertionError("should not re-extract")

    monkeypatch.setattr("legal_ai.agents.document.extract_document_facts", boom)
    facts = [DocumentFacts(document_id="doc-1")]
    assert nodes.document({"question": "q", "document_facts": facts}) == {}


def test_document_node_is_a_no_op_with_no_documents():
    assert nodes.document({"question": "q"}) == {}


def test_document_node_skips_a_document_that_is_not_stored():
    # One unreadable exhibit in a bundle must not cost the whole thread.
    result = nodes.document({"question": "q", "document_ids": ["test:absent"]})
    assert result == {"document_facts": []}


def test_context_builder_without_a_case_needs_no_case_lookup():
    result = nodes.context_builder({"question": "doctrine of frustration"})
    assert result["context"].case_id is None
    assert result["context"].established_findings == ()


def test_context_builder_seeds_from_the_case(conn):
    create_case(conn, "test:g1", "Patel v. Shah")
    record_finding(conn, "test:g1", EstablishedFinding(
        claim="Section 18 applies", evidence_ids=("act:2016:sec-18",),
    ))
    result = nodes.context_builder({"question": "What is the refund rate?", "case_id": "test:g1"})
    context = result["context"]
    assert context.case_id == "test:g1"
    assert [f.claim for f in context.established_findings] == ["Section 18 applies"]


def test_context_builder_records_the_session_against_the_case(conn):
    create_case(conn, "test:g2", "Patel v. Shah")
    nodes.context_builder({"question": "Can adverse possession apply?", "case_id": "test:g2"})
    assert get_case(conn, "test:g2").research_questions == ("Can adverse possession apply?",)


def test_document_facts_reach_the_context(conn):
    facts = [DocumentFacts(document_id="doc-1", issues=("gujarat land dispute",))]
    result = nodes.context_builder({"question": "who owns it", "document_facts": facts})
    assert result["context"].document_ids == ("doc-1",)
    assert result["context"].jurisdiction.state == "Gujarat"
