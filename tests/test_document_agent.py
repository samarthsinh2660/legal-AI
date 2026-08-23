import json

import pytest

from legal_ai.agents import document as doc
from legal_ai.context.models import DocumentFacts

PETITION = """
IN THE HIGH COURT OF GUJARAT AT AHMEDABAD

Kishor Patel .... Petitioner
versus
Marvel Developers Pvt Ltd .... Respondent

The agreement to sell was executed on 12 March 2019. Possession was due on
30 June 2021 and has not been given. The petitioner relies on Section 18 of
the Real Estate (Regulation and Development) Act, 2016 and on Section 19 of
the Real Estate (Regulation and Development) Act, 2016.
"""


def _stub(monkeypatch, payload, calls=None):
    def fake_generate(prompt, **kwargs):
        if calls is not None:
            calls.append(prompt)
        return json.dumps(payload) if isinstance(payload, dict) else payload

    monkeypatch.setattr(doc, "generate", fake_generate)


def test_returns_structure_not_the_document_body(monkeypatch):
    # The whole reason this is a separate agent: a researcher must never be
    # handed a 300-page petition.
    _stub(monkeypatch, {"document_type": "petition", "parties": ["Kishor Patel"],
                        "dates": ["30 June 2021"], "issues": ["delayed possession"]})
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert isinstance(facts, DocumentFacts)
    assert "IN THE HIGH COURT" not in str(facts)


def test_extracts_the_model_fields(monkeypatch):
    _stub(monkeypatch, {"document_type": "petition",
                        "parties": ["Kishor Patel", "Marvel Developers Pvt Ltd"],
                        "dates": ["12 March 2019", "30 June 2021"],
                        "issues": ["delayed possession"]})
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert facts.document_type == "petition"
    assert "Kishor Patel" in facts.parties
    assert "30 June 2021" in facts.dates
    assert facts.issues == ("delayed possession",)


def test_cited_sections_come_from_regex_not_the_model(monkeypatch):
    # A citation is a pattern, not a judgement. The model is told nothing
    # about sections and must not be the source of them.
    _stub(monkeypatch, {"document_type": "petition", "parties": [], "dates": [], "issues": []})
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert any("Section 18" in c for c in facts.cited_sections)
    assert any("Section 19" in c for c in facts.cited_sections)


def test_a_malformed_generation_degrades_rather_than_raises(monkeypatch):
    _stub(monkeypatch, "this is not json at all")
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert facts.parties == ()
    # Regex extraction is unaffected by the model failing.
    assert facts.cited_sections


def test_a_failing_model_call_does_not_lose_the_whole_extraction(monkeypatch):
    monkeypatch.setattr(doc, "generate", lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("429")))
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert facts.parties == ()
    assert facts.cited_sections


def test_non_string_fields_are_dropped_not_trusted(monkeypatch):
    _stub(monkeypatch, {"parties": ["Real Name", 42, None, "  "], "dates": "not a list",
                        "issues": [], "document_type": None})
    facts = doc.extract_document_facts("doc-1", PETITION)
    assert facts.parties == ("Real Name",)
    assert facts.dates == ("not a list",)


def test_a_long_document_is_read_in_windows(monkeypatch):
    calls = []
    _stub(monkeypatch, {"parties": [], "dates": [], "issues": [], "document_type": None}, calls)
    doc.extract_document_facts("doc-1", "x" * (doc.WINDOW_CHARS * 3))
    assert len(calls) == 3


def test_window_count_is_capped_so_a_huge_upload_cannot_run_away(monkeypatch):
    calls = []
    _stub(monkeypatch, {"parties": [], "dates": [], "issues": [], "document_type": None}, calls)
    doc.extract_document_facts("doc-1", "x" * (doc.WINDOW_CHARS * 50))
    assert len(calls) == doc.MAX_WINDOWS


def test_facts_merge_across_windows_without_duplicating(monkeypatch):
    _stub(monkeypatch, {"parties": ["Same Party"], "dates": [], "issues": [],
                        "document_type": "notice"})
    facts = doc.extract_document_facts("doc-1", "y" * (doc.WINDOW_CHARS * 3))
    assert facts.parties == ("Same Party",)


def test_a_fenced_json_block_is_parsed():
    assert doc._parse('```json\n{"parties": ["A"]}\n```') == {"parties": ["A"]}


def test_a_json_list_is_rejected_since_the_contract_is_an_object():
    assert doc._parse('["not", "an", "object"]') == {}


def test_document_facts_reach_the_context_and_settle_jurisdiction():
    # People describe a grievance without saying where they are; the
    # document usually does.
    from legal_ai.context.builder import build_thread_context

    facts = DocumentFacts(
        document_id="doc-1",
        document_type="petition",
        parties=("Kishor Patel",),
        issues=("delayed possession before the Gujarat authority",),
    )
    ctx = build_thread_context("builder has not given possession", documents=(facts,))
    assert ctx.jurisdiction.court == "Gujarat High Court"
    assert ctx.document_ids == ("doc-1",)
    assert ctx.documents[0].parties == ("Kishor Patel",)


def test_the_context_never_carries_a_document_body():
    from legal_ai.context.builder import build_thread_context
    from legal_ai.context.serialization import render

    facts = DocumentFacts(document_id="doc-1", parties=("A Party",), issues=("an issue",))
    rendered = render(build_thread_context("what are my options", documents=(facts,)))
    assert "IN THE HIGH COURT" not in rendered


def test_the_document_node_is_skipped_when_nothing_was_uploaded():
    from legal_ai.graph import nodes

    assert nodes.document({"question": "q"}) == {}
