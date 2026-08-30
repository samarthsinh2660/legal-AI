"""The Analyst turns retrieved law into statements that can be checked."""

import json
from datetime import datetime, timezone

import pytest

from legal_ai.agents import analyst
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
