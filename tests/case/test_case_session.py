"""Flow A (research then attach) and Flow B (case then research)."""

from datetime import datetime, timezone

import pytest

from legal_ai.case.session import save_to_case, start_session
from legal_ai.case.store import create_case, ensure_case_schema, get_case, record_finding
from legal_ai.context.models import DocumentFacts, EstablishedFinding
from legal_ai.knowledge.static.db import get_connection
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_case_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM cases WHERE case_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def _evidence(document_id: str) -> Evidence:
    return Evidence(
        content="text",
        document_id=document_id,
        document_type="section",
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
    )


def test_a_thread_needs_no_case(conn):
    # A plain question of law must not require inventing a matter first.
    context = start_session(conn, "What is the limitation period for a cheque bounce complaint?")
    assert context.case_id is None
    assert context.established_findings == ()


def test_flow_b_seeds_the_thread_from_what_the_case_established(conn):
    create_case(conn, "test:s1", "Patel v. Shah")
    record_finding(conn, "test:s1", EstablishedFinding(
        claim="Section 18 applies", evidence_ids=("act:2016:sec-18",),
    ))
    context = start_session(conn, "What proves ownership?", case_id="test:s1")
    assert context.case_id == "test:s1"
    assert [f.claim for f in context.established_findings] == ["Section 18 applies"]


def test_flow_b_records_the_question_against_the_case(conn):
    create_case(conn, "test:s2", "Patel v. Shah")
    start_session(conn, "Can adverse possession apply?", case_id="test:s2")
    assert get_case(conn, "test:s2").research_questions == ("Can adverse possession apply?",)


def test_an_unknown_case_still_researches(conn):
    # Losing the seed degrades an answer; refusing to research loses it.
    context = start_session(conn, "Limitation period?", case_id="test:nope")
    assert context.question == "Limitation period?"
    assert context.established_findings == ()


def test_flow_a_attaches_a_finished_session_to_a_case(conn):
    create_case(conn, "test:s3", "Patel v. Shah")
    save_to_case(
        conn, "test:s3", "Does Section 18 apply?",
        findings=(EstablishedFinding(claim="Section 18 applies", evidence_ids=("act:2016:sec-18",)),),
    )
    case = get_case(conn, "test:s3")
    assert case.research_questions == ("Does Section 18 apply?",)
    assert case.findings[0].evidence_ids == ("act:2016:sec-18",)


def test_saving_with_no_findings_still_records_what_was_researched(conn):
    # "Save to case" must always leave a trace, not silently record nothing.
    create_case(conn, "test:s4", "Patel v. Shah")
    save_to_case(conn, "test:s4", "Does Section 18 apply?",
                 evidence=[_evidence("act:2016:sec-18"), _evidence("act:2016:sec-19")])
    case = get_case(conn, "test:s4")
    assert len(case.findings) == 1
    assert case.findings[0].claim == "Does Section 18 apply?"
    assert case.findings[0].evidence_ids == ("act:2016:sec-18", "act:2016:sec-19")


def test_the_case_carries_evidence_ids_not_evidence_text(conn):
    # A finding must stay checkable against the corpus. Copying passages in
    # would let the case and the law drift apart at the next amendment.
    create_case(conn, "test:s5", "Patel v. Shah")
    save_to_case(conn, "test:s5", "q", evidence=[_evidence("act:2016:sec-18")])
    assert "text" not in str(get_case(conn, "test:s5").findings)


def test_documents_reach_the_context_through_the_session(conn):
    create_case(conn, "test:s6", "Patel v. Shah")
    facts = DocumentFacts(document_id="doc-1", parties=("Kishor Patel",), issues=("gujarat land dispute",))
    context = start_session(conn, "What proves ownership?", case_id="test:s6", documents=(facts,))
    assert context.document_ids == ("doc-1",)
    # A document naming a state settles jurisdiction the question never gave.
    assert context.jurisdiction.state == "Gujarat"


def test_a_later_session_sees_the_earlier_one(conn):
    # The fourth question about a matter must not re-derive the first three.
    create_case(conn, "test:s7", "Patel v. Shah")
    save_to_case(conn, "test:s7", "Does Section 18 apply?",
                 findings=(EstablishedFinding(claim="Section 18 applies", evidence_ids=("a",)),))
    later = start_session(conn, "What is the refund rate?", case_id="test:s7")
    assert [f.claim for f in later.established_findings] == ["Section 18 applies"]
