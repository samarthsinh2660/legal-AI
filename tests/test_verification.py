"""Milestone 8 -- groundedness and coverage.

Groundedness inspects what was said. Coverage inspects what was NOT said,
which is the failure a user actually experiences: an answer that is entirely
true and quietly incomplete.
"""

import pytest

from legal_ai.knowledge.static.db import get_connection
from legal_ai.verification.coverage import MAX_SUGGESTIONS, _act_of, suggest_missed_sections
from legal_ai.verification.groundedness import Claim, check_groundedness

REAL = "act:2158:sec-18"
ALSO_REAL = "act:2158:sec-19"
FAKE = "act:9999:sec-does-not-exist"


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.close()


# ------------------------------------------------------------ groundedness

def test_a_claim_citing_a_real_document_is_grounded(conn):
    result = check_groundedness([Claim("promoter must refund", (REAL,))], conn)
    assert result.all_grounded


def test_a_claim_citing_nothing_is_unsupported(conn):
    result = check_groundedness([Claim("the law says so", ())], conn)
    assert result.unsupported[0][1] == "cites no evidence"


def test_a_claim_citing_an_invented_document_is_unsupported(conn):
    # The failure this check exists for: a fabricated citation reads exactly
    # like a real one until the id is looked up.
    result = check_groundedness([Claim("invented provision", (FAKE,))], conn)
    assert not result.all_grounded
    assert "do not exist" in result.unsupported[0][1]


def test_a_claim_citing_a_real_document_the_thread_never_saw_is_unsupported(conn):
    # True by luck is not the same as researched, and must not read the same.
    result = check_groundedness(
        [Claim("cites a real but unretrieved section", (REAL,))],
        conn,
        available_ids={ALSO_REAL},
    )
    assert "never retrieved" in result.unsupported[0][1]


def test_a_claim_is_grounded_when_the_thread_did_retrieve_it(conn):
    result = check_groundedness(
        [Claim("cites what was retrieved", (REAL,))], conn, available_ids={REAL}
    )
    assert result.all_grounded


def test_claims_are_partitioned_not_all_or_nothing(conn):
    result = check_groundedness(
        [Claim("good", (REAL,)), Claim("bad", (FAKE,)), Claim("none", ())], conn
    )
    assert len(result.grounded) == 1
    assert len(result.unsupported) == 2


def test_unsupported_texts_are_reportable_for_the_answer(conn):
    # On exhausting the re-research cap the answer still ships with these
    # flagged, rather than silently dropping them.
    result = check_groundedness([Claim("unsupported thing", (FAKE,))], conn)
    assert result.unsupported_texts == ["unsupported thing"]


def test_no_claims_is_vacuously_grounded(conn):
    assert check_groundedness([], conn).all_grounded


def test_groundedness_needs_no_model():
    # It cannot hallucinate, which is why it runs first.
    import inspect

    import legal_ai.verification.groundedness as module

    assert "generate" not in inspect.getsource(module)


# ---------------------------------------------------------------- coverage

def test_act_id_is_derived_from_a_section_id():
    assert _act_of("act:2158:sec-18") == "act:2158"
    assert _act_of("judgment:ik-123") is None
    assert _act_of("act:2158") is None


def test_coverage_suggests_related_sections_of_a_cited_act(conn):
    suggestions = suggest_missed_sections(
        conn, [REAL], {REAL}, "refund for delayed possession"
    )
    assert suggestions
    assert all(doc_id.startswith("act:2158:") for doc_id, _title in suggestions)


def test_coverage_never_suggests_what_was_already_retrieved(conn):
    suggestions = suggest_missed_sections(
        conn, [REAL], {REAL, ALSO_REAL}, "rights of the allottee"
    )
    assert ALSO_REAL not in {doc_id for doc_id, _title in suggestions}


def test_coverage_is_capped_so_the_prompt_does_not_become_noise(conn):
    suggestions = suggest_missed_sections(conn, [REAL], set(), "penalty and compensation")
    assert len(suggestions) <= MAX_SUGGESTIONS


def test_coverage_of_a_judgment_citation_suggests_nothing(conn):
    # The stand-in only understands Act structure.
    assert suggest_missed_sections(conn, ["judgment:ik-123"], set(), "anything") == []


def test_coverage_of_no_citations_suggests_nothing(conn):
    assert suggest_missed_sections(conn, [], set(), "anything") == []


# ------------------------------------------------------- graph integration

def test_the_graph_loops_back_to_research_on_an_unsupported_claim(monkeypatch):
    from legal_ai.graph.build import build_research_graph

    # Claims come from the Analyst now, so the fabricated one is injected
    # there rather than into the initial state -- the Analyst re-runs on
    # every pass, which is what lets the loop reconsider newly researched
    # findings, and would overwrite anything seeded on the channel.
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("a fabricated holding", (FAKE,))]},
    )
    graph = build_research_graph()
    result = graph.invoke({
        "question": "what is the punishment for murder",
    })
    # Bounded: it re-researches, then ships with the gap flagged rather than
    # looping forever or silently dropping the claim.
    assert result["verification_passes"] == 2
    assert result["unsupported_claims"] == ["a fabricated holding"]
    assert result["answer"]


def test_the_graph_does_not_loop_when_every_claim_is_grounded(monkeypatch):
    from datetime import datetime, timezone

    from legal_ai.graph.build import build_research_graph
    from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef

    retrieved = Evidence(
        content="Return of amount and compensation.",
        document_id=REAL,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("promoter must refund", (REAL,))]},
    )
    result = build_research_graph().invoke({
        "question": "what is the punishment for murder",
        "findings": [retrieved],
    })
    assert result["verification_passes"] == 1
    assert result["unsupported_claims"] == []


def test_a_claim_citing_a_real_document_the_thread_never_retrieved_still_loops(monkeypatch):
    # Cited correctly but never actually looked at: true by luck, which the
    # answer must not present as researched.
    from legal_ai.graph.build import build_research_graph

    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("promoter must refund", (REAL,))]},
    )
    result = build_research_graph().invoke({
        "question": "what is the punishment for murder",
    })
    assert result["unsupported_claims"] == ["promoter must refund"]
