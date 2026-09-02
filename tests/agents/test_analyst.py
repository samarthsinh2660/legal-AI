"""The Analyst turns retrieved law into statements that can be checked."""

import json
from datetime import datetime, timezone

import pytest

from legal_ai.agents import analyst
from legal_ai.agents.analyst import analyse
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _evidence(doc_id, doc_type="section", title="Return of amount and compensation"):
    return Evidence(
        content="If the promoter fails to give possession, he shall return the amount.",
        document_id=doc_id,
        title=title,
        document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


EVIDENCE = [_evidence("act:2158:sec-18"), _evidence("act:2158:sec-19")]


def _stub(monkeypatch, payload):
    monkeypatch.setattr(
        analyst, "generate",
        lambda p, **kw: json.dumps(payload) if isinstance(payload, dict) else payload,
    )


def test_claims_carry_their_own_evidence_ids(monkeypatch):
    # The point of the whole agent: "Sources: a, b, c" at the end of a
    # paragraph cannot be verified, because nothing says which sentence
    # rests on which source.
    _stub(monkeypatch, {"lede": "You may claim a refund.", "claims": [
        {"text": "A promoter who misses possession must refund with interest",
         "evidence_ids": ["act:2158:sec-18"]},
    ]})
    result = analyst.analyse("what are my options", EVIDENCE)
    assert result.claims[0].evidence_ids == ("act:2158:sec-18",)
    assert result.lede == "You may claim a refund."


def test_an_invented_identifier_is_dropped(monkeypatch):
    # A model asked to cite will sometimes produce a plausible id that was
    # never in front of it. An invented citation in a legal answer is the
    # worst failure this system has, so only ids that were actually
    # retrieved survive.
    _stub(monkeypatch, {"claims": [
        {"text": "Section 42 says something", "evidence_ids": ["act:9999:sec-42"]},
    ]})
    result = analyst.analyse("q", EVIDENCE)
    assert result.claims[0].evidence_ids == ()


def test_a_claim_with_a_fabricated_id_survives_as_unsupported(monkeypatch):
    # Dropping the id, not the claim: the statement becomes visibly
    # unsupported instead of quietly disappearing.
    _stub(monkeypatch, {"claims": [
        {"text": "invented statement", "evidence_ids": ["act:9999:sec-42"]},
    ]})
    assert analyst.analyse("q", EVIDENCE).claims[0].text == "invented statement"


def test_real_and_invented_ids_are_separated(monkeypatch):
    _stub(monkeypatch, {"claims": [
        {"text": "mixed", "evidence_ids": ["act:2158:sec-18", "act:9999:sec-1"]},
    ]})
    assert analyst.analyse("q", EVIDENCE).claims[0].evidence_ids == ("act:2158:sec-18",)


def test_no_evidence_produces_no_claims(monkeypatch):
    def boom(p, **kw):
        raise AssertionError("must not call a model with nothing to analyse")

    monkeypatch.setattr(analyst, "generate", boom)
    result = analyst.analyse("q", [])
    assert result.claims == ()
    assert "No supporting provisions" in result.lede


def test_a_model_failure_says_so_rather_than_inventing(monkeypatch):
    def boom(p, **kw):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(analyst, "generate", boom)
    result = analyst.analyse("q", EVIDENCE)
    assert result.claims == ()
    assert "unavailable" in result.lede


def test_malformed_json_degrades_to_an_empty_analysis(monkeypatch):
    _stub(monkeypatch, "not json")
    assert analyst.analyse("q", EVIDENCE).claims == ()


def test_a_claim_without_text_is_dropped(monkeypatch):
    _stub(monkeypatch, {"claims": [{"text": "  ", "evidence_ids": ["act:2158:sec-18"]}]})
    assert analyst.analyse("q", EVIDENCE).claims == ()


def test_the_case_documents_reach_the_prompt(monkeypatch):
    from legal_ai.context.models import DocumentFacts

    seen = {}
    monkeypatch.setattr(analyst, "generate",
                        lambda p, **kw: seen.update(prompt=p) or '{"claims": []}')
    analyst.analyse("q", EVIDENCE, documents=(
        DocumentFacts(document_id="doc-1", clauses=("possession by 30 June 2021",)),
    ))
    assert "possession by 30 June 2021" in seen["prompt"]


def test_evidence_shown_to_the_model_is_capped(monkeypatch):
    seen = {}
    monkeypatch.setattr(analyst, "generate",
                        lambda p, **kw: seen.update(prompt=p) or '{"claims": []}')
    many = [_evidence(f"act:1:sec-{i}") for i in range(analyst.MAX_EVIDENCE_SHOWN + 10)]
    analyst.analyse("q", many)
    assert f"act:1:sec-{analyst.MAX_EVIDENCE_SHOWN + 5}" not in seen["prompt"]


def test_one_model_call_per_question(monkeypatch):
    calls = []
    monkeypatch.setattr(analyst, "generate",
                        lambda p, **kw: calls.append(1) or '{"claims": []}')
    analyst.analyse("q", EVIDENCE)
    assert len(calls) == 1


def test_dropped_identifiers_are_counted(monkeypatch):
    # The number worth watching when the model changes: it is the
    # difference between a fabricated citation a reader would trust and a
    # visibly unsupported statement.
    _stub(monkeypatch, {"claims": [
        {"text": "a", "evidence_ids": ["act:2158:sec-18", "act:9999:sec-1"]},
        {"text": "b", "evidence_ids": ["act:8888:sec-2"]},
    ]})
    result = analyst.analyse("q", EVIDENCE)
    assert set(result.dropped_ids) == {"act:9999:sec-1", "act:8888:sec-2"}


def test_nothing_is_dropped_when_every_citation_is_real(monkeypatch):
    _stub(monkeypatch, {"claims": [
        {"text": "a", "evidence_ids": ["act:2158:sec-18"]},
    ]})
    assert analyst.analyse("q", EVIDENCE).dropped_ids == ()


def test_a_question_that_was_never_searched_says_so():
    """Distinct from "we searched and found nothing".

    A greeting or an off-topic message plans no angles, so nothing is
    retrieved -- but reporting that as a thin corpus tells the reader we
    looked. Same three-state rule the rest of the system follows.
    """
    result = analyse("write me a poem", [], searched=False)

    assert result.claims == ()
    assert "provisions were retrieved" not in result.lede
    assert "indian law" in result.lede.lower()


def test_an_empty_search_still_reports_a_thin_corpus():
    result = analyse("a real legal question", [], searched=True)

    assert "No supporting provisions were retrieved." in result.lede


def test_a_whole_statute_section_is_not_truncated_in_the_prompt():
    """`build_evidence` carries a section whole; a render cap sized for a
    judgment passage would cut the provisos straight back off."""
    from legal_ai.agents.analyst import _render_evidence
    from legal_ai.retrieval.evidence_builder import SECTION_CHARS

    section = "The offence. " * 100 + "Provided that notice is given within thirty days."
    item = Evidence(
        document_id="act:2189:sec-138",
        document_type="section",
        title="Dishonour of cheque",
        content=section,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )

    rendered = _render_evidence([item])

    assert "thirty days" in rendered
    assert len(section) <= SECTION_CHARS


def test_an_unreadable_reply_says_so_rather_than_answering_blankly(monkeypatch):
    """A blank answer and "the corpus holds nothing" look identical on
    screen. The exception path already said so; an unparseable reply took a
    different route and said nothing at all.
    """
    monkeypatch.setattr(analyst, "generate", lambda *a, **kw: "not json at all")

    result = analyse("a question", [_evidence("act:1:sec-1")])

    assert result.claims == ()
    assert result.lede
    assert "unavailable" in result.lede.lower()


def test_a_reply_with_no_claims_still_reports_its_lede(monkeypatch):
    """Distinct from unreadable: the model answered and found nothing to
    claim, which is a real outcome the prompt asks for."""
    monkeypatch.setattr(
        analyst, "generate",
        lambda *a, **kw: '{"lede": "The material does not answer this.", "claims": []}',
    )

    result = analyse("a question", [_evidence("act:1:sec-1")])

    assert result.claims == ()
    assert result.lede == "The material does not answer this."


def test_a_judgment_extract_is_not_truncated_to_one_passage_in_the_prompt():
    """`build_evidence` carries several passages of a judgment; a render cap
    of 700 chars would show the model the first one and throw the rest away."""
    from legal_ai.agents.analyst import _render_evidence
    from legal_ai.retrieval.evidence_builder import ELLIPSIS, EXTRACT_CHARS

    extract = ("Held on the first point. " * 40) + f"\n{ELLIPSIS}\n" + \
              ("Held on the second point. " * 40)
    item = Evidence(
        document_id="judgment:x",
        document_type="judgment",
        title="X v. Y",
        content=extract,
        provenance=Provenance(
            source=SourceRef(name="SCI", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )

    rendered = _render_evidence([item])

    assert "second point" in rendered
    assert len(extract) <= EXTRACT_CHARS
