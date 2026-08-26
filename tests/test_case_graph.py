"""The case graph -- the deployable surface for a case workspace.

Separate from the research graph because the two run on different
occasions: research once per question, a case whenever it is opened.
"""

from datetime import datetime, timezone

import pytest

from legal_ai.case.files import get_facts, store_facts
from legal_ai.case.store import create_case, ensure_case_schema
from legal_ai.case.upload import upload_document
from legal_ai.context.models import DocumentFacts
from legal_ai.graph import case_nodes
from legal_ai.graph.build import build_case_graph
from legal_ai.knowledge.static.db import get_connection

COMPLAINT = b"""IN THE GUJARAT REAL ESTATE REGULATORY AUTHORITY
Possession was due on 30 June 2021 and has not been handed over.
The complainant relies on Section 18 of the Real Estate (Regulation and
Development) Act, 2016.
"""


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_case_schema(connection)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM cases WHERE case_id LIKE 'test:%'")
    connection.commit()
    create_case(connection, "test:g1", "Patel v. Marvel", state="Gujarat")
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM cases WHERE case_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def _no_model(monkeypatch):
    """Keep the graph runnable without an API key, as the research graph is."""
    monkeypatch.setattr(
        "legal_ai.agents.case.generate",
        lambda p, **kw: '{"issues": ["delayed possession"], "missing_facts": [], "contradictions": []}',
    )


# ------------------------------------------------------------- persistence

def test_extracted_facts_survive_the_upload(conn, monkeypatch):
    # Without this the workspace re-runs the Document Agent over every file
    # each time it is opened -- a model call per 12,000-character window,
    # paid again on every view.
    monkeypatch.setattr(
        "legal_ai.case.upload.extract_document_facts",
        lambda document_id, text: DocumentFacts(
            document_id=document_id, document_type="petition", issues=("delay",)
        ),
    )
    facts = upload_document(conn, "test:g1", "c.txt", COMPLAINT)
    stored = get_facts(conn, facts.document_id)
    assert stored is not None
    assert stored.issues == ("delay",)
    assert stored.document_type == "petition"


def test_a_failed_extraction_is_not_stored_as_fact(conn):
    # "We could not read it" must not become "it says nothing" on record --
    # a later view would find facts stored and never retry.
    upload_document(conn, "test:g1", "c.txt", COMPLAINT, extract_facts=False)
    from legal_ai.case.files import list_case_files

    document_id = list_case_files(conn, "test:g1")[0][0]
    store_facts(conn, document_id, DocumentFacts(document_id=document_id, extraction_failed=True))
    assert get_facts(conn, document_id) is None


# ------------------------------------------------------------------- graph

def test_the_graph_produces_an_analysis(conn, monkeypatch):
    _no_model(monkeypatch)
    monkeypatch.setattr(
        "legal_ai.case.upload.extract_document_facts",
        lambda document_id, text: DocumentFacts(
            document_id=document_id, dates=("30 June 2021",), issues=("delay",)
        ),
    )
    upload_document(conn, "test:g1", "c.txt", COMPLAINT)

    result = build_case_graph().invoke({"case_id": "test:g1"})
    analysis = result["analysis"]
    assert analysis.case_id == "test:g1"
    assert [e.raw for e in analysis.timeline] == ["30 June 2021"]
    assert analysis.issues


def test_an_unknown_case_ends_with_a_reason_not_an_empty_analysis():
    # An empty CaseAnalysis and a real one look alike from outside. A
    # workspace showing "no issues" for a case that does not exist is worse
    # than an error.
    result = build_case_graph().invoke({"case_id": "test:does-not-exist"})
    assert result.get("error")
    assert result.get("analysis") is None


def test_a_case_already_read_costs_no_extraction(conn, monkeypatch):
    monkeypatch.setattr(
        "legal_ai.case.upload.extract_document_facts",
        lambda document_id, text: DocumentFacts(document_id=document_id, issues=("delay",)),
    )
    upload_document(conn, "test:g1", "c.txt", COMPLAINT)

    def boom(*a, **k):
        raise AssertionError("stored facts must be reused, not re-extracted")

    monkeypatch.setattr("legal_ai.agents.document.extract_document_facts", boom)
    _no_model(monkeypatch)
    assert build_case_graph().invoke({"case_id": "test:g1"})["analysis"] is not None


def test_a_file_never_read_is_extracted_on_first_view(conn, monkeypatch):
    # The bulk-upload path attaches without extracting, so the first view
    # has to do it.
    upload_document(conn, "test:g1", "c.txt", COMPLAINT, extract_facts=False)
    monkeypatch.setattr(
        "legal_ai.agents.document.extract_document_facts",
        lambda document_id, text: DocumentFacts(document_id=document_id, issues=("read here",)),
    )
    _no_model(monkeypatch)
    result = build_case_graph().invoke({"case_id": "test:g1"})
    assert any("read here" in f.issues for f in result["documents"])


def test_the_case_graph_does_not_research(conn, monkeypatch):
    # A case analysis is a view of what is known, not a new question.
    # Evidence arrives on the channel from sessions already run.
    _no_model(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("the case graph must not research")

    monkeypatch.setattr("legal_ai.agents.supervisor.research", boom)
    assert build_case_graph().invoke({"case_id": "test:g1"})["analysis"] is not None


def test_langgraph_manifest_exposes_the_case_graph():
    # The deployable surface. Without this entry the Case Agent is a Python
    # function nothing outside Python can call.
    import json
    from pathlib import Path

    manifest = json.loads(Path("langgraph.json").read_text())
    assert "Case Analysis" in manifest["graphs"]
    assert manifest["graphs"]["Case Analysis"].endswith(":case_graph")
