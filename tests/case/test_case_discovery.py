"""Finding judgments by issue -- the gap the lazy fetch path never covered.

The archive index carries court, year, judge, party, citation and CNR, and
no subject column, so "cases about drugs" has nothing there to match.
Full-text search is the only route from an issue to a case name.
"""

import pytest

from legal_ai.context.builder import build_thread_context
from legal_ai.retrieval.case_law import court_filter, section_identifiers, wants_case_law


# ------------------------------------------------------------ the gate

def test_a_question_asking_for_judgments_fires():
    for question in (
        "give me supreme court cases about drugs",
        "what have the courts held on commercial quantity bail",
        "delhi high court judgments on delayed possession",
        "is there any precedent for this",
        "what is the settled law on section 138",
    ):
        assert wants_case_law(question), question


def test_a_plain_statute_lookup_does_not_fire():
    # Discovery reaches a third party. Paying that on every statute lookup
    # costs every user seconds for something they did not ask for.
    for question in (
        "what does section 138 say",
        "what is the punishment for murder",
        "which provision covers refund of amount paid to a promoter",
        "limitation period for a cheque bounce complaint",
    ):
        assert not wants_case_law(question), question


# ---------------------------------------------------------- court filter

def test_a_court_named_in_the_question_is_used():
    assert court_filter("supreme court cases on bail") == "supremecourt"
    assert court_filter("delhi high court judgments on possession") == "delhi"
    assert court_filter("bombay high court view on this") == "bombay"


def test_the_case_file_supplies_the_court_when_the_question_does_not():
    context = build_thread_context("what have the courts held about this gujarat land dispute")
    assert court_filter("what have the courts held", context) == "gujarat"


def test_a_court_named_in_the_question_beats_the_case_file():
    # A Gujarat matter routinely turns on a Supreme Court authority.
    # Inheriting the case's High Court would hide the binding precedent.
    context = build_thread_context("gujarat land dispute")
    assert court_filter("what has the supreme court held", context) == "supremecourt"


def test_no_court_anywhere_searches_everything():
    assert court_filter("what have the courts held on bail") is None


# ------------------------------------------------- section identifiers

def test_sections_render_the_way_a_judgment_cites_them(monkeypatch):
    # "Cognizance of offences" says nothing about cheques. Measured
    # 2026-08-24: bare titles returned Kesavananda Bharati for a
    # cheque-bounce question.
    class _Act:
        title = "The Negotiable Instruments Act, 1881"

    import legal_ai.knowledge.static.store as store

    monkeypatch.setattr(store, "get_document", lambda conn, doc_id: _Act())

    class _E:
        document_type = "section"
        document_id = "act:1881:sec-138"

    assert section_identifiers([_E()], conn=None) == [
        "Section 138 Negotiable Instruments Act, 1881"
    ]


def test_non_sections_are_skipped(monkeypatch):
    class _Judgment:
        document_type = "judgment"
        document_id = "judgment:ik-1"

    assert section_identifiers([_Judgment()], conn=None) == []


def test_the_number_of_identifiers_is_capped(monkeypatch):
    import legal_ai.knowledge.static.store as store

    class _Act:
        title = "Some Act, 1999"

    monkeypatch.setattr(store, "get_document", lambda conn, doc_id: _Act())

    class _E:
        document_type = "section"

        def __init__(self, n):
            self.document_id = f"act:1:sec-{n}"

    assert len(section_identifiers([_E(i) for i in range(10)], conn=None, limit=3)) == 3


# ------------------------------------------------ wiring into research

from datetime import datetime, timezone

from legal_ai.agents import supervisor as sup
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef


def _evidence(doc_id, doc_type="section"):
    return Evidence(
        content="text",
        document_id=doc_id,
        document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="x", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


def _plan(monkeypatch, query="q"):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"a","query":"%s"}]' % query)
    monkeypatch.setattr(sup, "generate", lambda p, **kw: "s")
    monkeypatch.setattr(sup, "_search",
        lambda q, limit, filters=None, also=None: [_evidence("act:1:sec-18")])


def test_a_statute_question_does_not_reach_a_third_party(monkeypatch):
    _plan(monkeypatch)
    monkeypatch.setattr(sup, "_discover",
        lambda *a, **k: pytest.fail("discovery must not fire for a statute lookup"))
    result = sup.research("what does section 138 say")
    assert [e.document_id for e in result.evidence] == ["act:1:sec-18"]


def test_a_case_question_adds_judgments_to_the_statutes(monkeypatch):
    _plan(monkeypatch)
    monkeypatch.setattr(sup, "_discover",
        lambda *a, **k: [_evidence("judgment:ik-1", "judgment")])
    result = sup.research("what have the courts held on this")
    assert [e.document_id for e in result.evidence] == ["act:1:sec-18", "judgment:ik-1"]


def test_discovery_can_be_forced_on_or_off(monkeypatch):
    _plan(monkeypatch)
    monkeypatch.setattr(sup, "_discover", lambda *a, **k: [_evidence("judgment:ik-1", "judgment")])
    forced_on = sup.research("what does section 138 say", discover_cases=True)
    assert any(e.document_type == "judgment" for e in forced_on.evidence)
    forced_off = sup.research("give me supreme court cases", discover_cases=False)
    assert not any(e.document_type == "judgment" for e in forced_off.evidence)


def test_a_failing_discovery_does_not_lose_the_statutes(monkeypatch):
    # Discovery is additive. A third party being down must not cost the
    # caller provisions that were already retrieved.
    _plan(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("indiankanoon unreachable")

    monkeypatch.setattr("legal_ai.tools.judgments.discover_judgments", boom)
    result = sup.research("what have the courts held on this")
    assert [e.document_id for e in result.evidence] == ["act:1:sec-18"]


def test_the_sections_just_found_become_the_second_query(monkeypatch):
    # A section number is what a judgment quotes, so it is a far stronger
    # handle on case law than the user's own wording -- and it is grounded.
    _plan(monkeypatch)
    seen = {}

    def capture(question, section_queries=None, court=None, limit=5, store=True):
        seen["question"] = question
        seen["sections"] = section_queries
        seen["court"] = court
        return []

    monkeypatch.setattr("legal_ai.tools.judgments.discover_judgments", capture)
    # Patched on the supervisor, which imported the name directly.
    monkeypatch.setattr(sup, "section_identifiers",
                        lambda ev, conn, limit=3: ["Section 18 RERA Act, 2016"])
    sup.research("what has the supreme court held about possession")
    assert seen["sections"] == ["Section 18 RERA Act, 2016"]
    assert seen["court"] == "supremecourt"


def test_a_duplicate_judgment_is_not_added_twice(monkeypatch):
    _plan(monkeypatch)
    monkeypatch.setattr(sup, "_search",
        lambda q, limit, filters=None, also=None: [_evidence("judgment:ik-1", "judgment")])
    monkeypatch.setattr(sup, "_discover",
        lambda *a, **k: [_evidence("judgment:ik-1", "judgment")])
    result = sup.research("what have the courts held")
    assert len(result.evidence) == 1
