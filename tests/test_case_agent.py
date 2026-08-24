"""Case Agent -- what the Research Agent structurally cannot answer."""

import json
from datetime import datetime, timezone

import pytest

from legal_ai.agents import case as case_agent
from legal_ai.case.models import Case, CaseAnalysis
from legal_ai.context.models import DocumentFacts, EstablishedFinding
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef

CASE = Case(
    case_id="c1",
    title="Patel v. Marvel Developers",
    court="Gujarat High Court",
    state="Gujarat",
    parties=("Kishor Patel", "Marvel Developers Pvt Ltd"),
)

PETITION = DocumentFacts(
    document_id="doc-1",
    document_type="petition",
    parties=("Kishor Patel", "Marvel Developers Pvt Ltd"),
    dates=("12 March 2019", "30 June 2021"),
    cited_sections=("Section 18 of the Real Estate (Regulation and Development) Act, 2016",),
    issues=("possession not handed over", "refund with interest"),
)


def _evidence(document_id: str, document_type: str, title: str) -> Evidence:
    return Evidence(
        content=f"text of {document_id}",
        document_id=document_id,
        title=title,
        document_type=document_type,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
    )


SECTION = _evidence("act:2016:sec-18", "section", "Return of amount and compensation")
JUDGMENT = _evidence("judgment:ik-149094324", "judgment", "Newtech Promoters v. State of UP")


def _stub(monkeypatch, payload, calls=None):
    def fake_generate(prompt, **kwargs):
        if calls is not None:
            calls.append(prompt)
        return json.dumps(payload) if isinstance(payload, dict) else payload

    monkeypatch.setattr(case_agent, "generate", fake_generate)


def test_separates_applicable_law_from_precedents(monkeypatch):
    # A section and a judgment are both "authority" but a lawyer uses them
    # differently, so the case view must not blend them into one list.
    _stub(monkeypatch, {"issues": ["delayed possession"], "missing_facts": []})
    analysis = case_agent.analyse_case(CASE, (PETITION,), [SECTION, JUDGMENT])
    assert analysis.applicable_law == ("act:2016:sec-18",)
    assert analysis.precedents == ("judgment:ik-149094324",)


def test_builds_the_timeline_without_asking_the_model(monkeypatch):
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    analysis = case_agent.analyse_case(CASE, (PETITION,), [])
    assert [e.raw for e in analysis.timeline] == ["12 March 2019", "30 June 2021"]
    # The dates must not have been sent for the model to re-derive.
    assert len(calls) == 1


def test_reports_what_the_matter_is_missing(monkeypatch):
    # The output with no counterpart in a research session.
    _stub(monkeypatch, {
        "issues": ["delayed possession"],
        "missing_facts": ["No proof the allottee's payments were made in full"],
    })
    analysis = case_agent.analyse_case(CASE, (PETITION,), [SECTION])
    assert analysis.missing_facts == ("No proof the allottee's payments were made in full",)


def test_every_fact_traces_to_a_document(monkeypatch):
    # A "fact" in the case view must be something a file actually says.
    _stub(monkeypatch, {"issues": [], "missing_facts": []})
    analysis = case_agent.analyse_case(CASE, (PETITION,), [])
    assert all("[doc-1]" in fact for fact in analysis.facts)


def test_the_documents_own_issues_survive_a_model_failure(monkeypatch):
    # A bad generation must not show a case with no issues at all.
    def boom(prompt, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(case_agent, "generate", boom)
    analysis = case_agent.analyse_case(CASE, (PETITION,), [SECTION])
    assert analysis.issues == ("possession not handed over", "refund with interest")
    # The deterministic half is unaffected.
    assert len(analysis.timeline) == 2
    assert analysis.applicable_law == ("act:2016:sec-18",)


def test_malformed_json_degrades_rather_than_raising(monkeypatch):
    _stub(monkeypatch, "not json at all")
    analysis = case_agent.analyse_case(CASE, (PETITION,), [SECTION])
    assert isinstance(analysis, CaseAnalysis)
    assert analysis.missing_facts == ()


def test_an_empty_case_costs_no_model_call(monkeypatch):
    # There is no matter to analyse yet; a call here would invent one.
    calls = []
    _stub(monkeypatch, {"issues": ["invented"], "missing_facts": ["invented"]}, calls)
    analysis = case_agent.analyse_case(CASE, (), [])
    assert calls == []
    assert analysis.issues == ()
    assert analysis.missing_facts == ()


def test_established_findings_are_shown_to_the_model(monkeypatch):
    # The point of the container: don't re-derive what earlier sessions settled.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    case = Case(
        case_id="c1", title="Patel v. Marvel",
        findings=(EstablishedFinding(claim="Section 18 applies", evidence_ids=("act:2016:sec-18",)),),
    )
    case_agent.analyse_case(case, (PETITION,), [SECTION])
    assert "Section 18 applies" in calls[0]


def test_issues_and_missing_facts_cost_one_call_not_two(monkeypatch):
    calls = []
    _stub(monkeypatch, {"issues": ["a"], "missing_facts": ["b"]}, calls)
    case_agent.analyse_case(CASE, (PETITION,), [SECTION, JUDGMENT])
    assert len(calls) == 1


def test_the_document_body_never_reaches_the_model(monkeypatch):
    # Same isolation guarantee the Document Agent gives: structure crosses
    # the boundary, never the file.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    case_agent.analyse_case(CASE, (PETITION,), [SECTION])
    assert "IN THE HIGH COURT" not in calls[0]


# --- bounded inputs: a case only ever grows ---

def test_documents_shown_to_the_model_are_capped(monkeypatch):
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    many = tuple(
        DocumentFacts(document_id=f"doc-{i}", issues=(f"issue{i}",))
        for i in range(case_agent.MAX_DOCUMENTS_SHOWN + 12)
    )
    case_agent.analyse_case(CASE, many, [])
    assert "issue0" in calls[0]
    assert f"issue{case_agent.MAX_DOCUMENTS_SHOWN + 5}" not in calls[0]
    assert "12 further document(s) not shown" in calls[0]


def test_established_findings_shown_are_capped(monkeypatch):
    # A long-running matter accumulates findings without limit. The recent
    # ones are what a new analysis has to stay consistent with.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    case = Case(
        case_id="c1", title="Long matter",
        findings=tuple(
            EstablishedFinding(claim=f"finding {i}", evidence_ids=("a",))
            for i in range(case_agent.MAX_FINDINGS_SHOWN + 5)
        ),
    )
    case_agent.analyse_case(case, (PETITION,), [])
    assert "finding 0" not in calls[0]
    assert f"finding {case_agent.MAX_FINDINGS_SHOWN + 4}" in calls[0]
    assert "5 earlier not shown" in calls[0]


def test_retrieved_law_shown_is_capped(monkeypatch):
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    many = [_evidence(f"act:x:sec-{i}", "section", f"title{i}") for i in range(case_agent.MAX_LAW_SHOWN + 10)]
    analysis = case_agent.analyse_case(CASE, (PETITION,), many)
    assert f"title{case_agent.MAX_LAW_SHOWN + 5}" not in calls[0]
    # Ids are cheap and stay complete -- only what the model reads is cut.
    assert len(analysis.applicable_law) == case_agent.MAX_LAW_SHOWN + 10


def test_a_thousand_exhibit_bundle_costs_the_same_prompt_as_eight(monkeypatch):
    # Structure only, never bodies. That is what bounds this at all.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    case_agent.analyse_case(CASE, tuple(DocumentFacts(document_id=f"d{i}") for i in range(1000)), [])
    small = len(calls[0])
    calls.clear()
    case_agent.analyse_case(CASE, tuple(DocumentFacts(document_id=f"d{i}") for i in range(8)), [])
    assert small < len(calls[0]) * 4


def test_a_document_that_was_never_read_is_labelled_not_guessed(monkeypatch):
    # The model must not conclude a document raises no issues when the
    # truth is that an outage stopped anything reading it.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": []}, calls)
    unread = DocumentFacts(document_id="doc-9", document_type="petition", extraction_failed=True)
    case_agent.analyse_case(CASE, (unread,), [SECTION])
    assert "NOT YET READ" in calls[0]


# --- contradictions: the cross-document check (Phase 4) ---

AGREEMENT = DocumentFacts(
    document_id="doc-1",
    document_type="agreement",
    clauses=("possession by 30 June 2021",),
    dates=("30 June 2021",),
)
REPLY = DocumentFacts(
    document_id="doc-2",
    document_type="notice",
    claims=("promoter says the project was never registered under RERA",),
)


def test_contradictions_are_reported_between_documents(monkeypatch):
    _stub(monkeypatch, {
        "issues": [], "missing_facts": [],
        "contradictions": ["agreement [doc-1] promises possession by June 2021 "
                           "but the reply [doc-2] says the project was never registered"],
    })
    analysis = case_agent.analyse_case(CASE, (AGREEMENT, REPLY), [])
    assert len(analysis.contradictions) == 1
    assert "doc-1" in analysis.contradictions[0]


def test_a_single_document_case_reports_no_contradictions(monkeypatch):
    # A conflict needs two sides. Reporting one from a single document
    # would be the model inventing a disagreement.
    _stub(monkeypatch, {
        "issues": [], "missing_facts": [],
        "contradictions": ["this document contradicts itself"],
    })
    analysis = case_agent.analyse_case(CASE, (AGREEMENT,), [])
    assert analysis.contradictions == ()


def test_documents_that_agree_produce_no_contradictions(monkeypatch):
    _stub(monkeypatch, {"issues": [], "missing_facts": [], "contradictions": []})
    analysis = case_agent.analyse_case(CASE, (AGREEMENT, REPLY), [])
    assert analysis.contradictions == ()


def test_clauses_and_claims_are_shown_so_a_conflict_can_be_seen(monkeypatch):
    # Most conflict signal lives in the terms one document sets and the
    # assertions another makes. Not rendering them would make the task
    # impossible rather than hard.
    calls = []
    _stub(monkeypatch, {"issues": [], "missing_facts": [], "contradictions": []}, calls)
    case_agent.analyse_case(CASE, (AGREEMENT, REPLY), [])
    assert "possession by 30 June 2021" in calls[0]
    assert "never registered under RERA" in calls[0]


def test_contradictions_cost_no_extra_model_call(monkeypatch):
    calls = []
    _stub(monkeypatch, {"issues": ["a"], "missing_facts": ["b"], "contradictions": ["c"]}, calls)
    case_agent.analyse_case(CASE, (AGREEMENT, REPLY), [])
    assert len(calls) == 1


def test_a_model_failure_leaves_contradictions_empty_not_wrong(monkeypatch):
    def boom(prompt, **kwargs):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(case_agent, "generate", boom)
    analysis = case_agent.analyse_case(CASE, (AGREEMENT, REPLY), [])
    assert analysis.contradictions == ()
    # The deterministic half still stands.
    assert len(analysis.timeline) == 1
