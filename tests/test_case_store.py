"""Case persistence -- the container that outlives every research session."""

from datetime import datetime, timezone

import pytest

from legal_ai.case.store import (
    attach_document,
    create_case,
    ensure_case_schema,
    get_case,
    list_cases,
    record_finding,
    record_session,
)
from legal_ai.context.models import EstablishedFinding
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


def test_create_and_load_a_case(conn):
    create_case(
        conn, "test:c1", "Patel v. Shah",
        court="Gujarat High Court", state="Gujarat",
        case_number="SCA/1234/2024", parties=("Kishor Patel", "Rakesh Shah"),
    )
    case = get_case(conn, "test:c1")
    assert case is not None
    assert case.title == "Patel v. Shah"
    assert case.court == "Gujarat High Court"
    assert case.parties == ("Kishor Patel", "Rakesh Shah")


def test_creating_the_same_case_twice_does_not_lose_its_documents(conn):
    # Flow B is a UI wizard; a user can resubmit it. A second create must
    # not wipe what the first attempt already attached.
    create_case(conn, "test:c2", "Patel v. Shah")
    attach_document(conn, "test:c2", "doc-1")
    again = create_case(conn, "test:c2", "Patel v. Shah")
    assert again.document_ids == ("doc-1",)


def test_attaching_the_same_document_twice_is_a_no_op(conn):
    create_case(conn, "test:c3", "A v. B")
    attach_document(conn, "test:c3", "doc-1")
    attach_document(conn, "test:c3", "doc-1")
    assert get_case(conn, "test:c3").document_ids == ("doc-1",)


def test_findings_round_trip_with_their_evidence_ids(conn):
    create_case(conn, "test:c4", "A v. B")
    record_finding(conn, "test:c4", EstablishedFinding(
        claim="Possession was due on 30 June 2021",
        evidence_ids=("act:1791:sec-18", "act:1791:sec-19"),
        depends_on=("jurisdiction",),
    ))
    case = get_case(conn, "test:c4")
    assert len(case.findings) == 1
    finding = case.findings[0]
    assert finding.evidence_ids == ("act:1791:sec-18", "act:1791:sec-19")
    assert finding.depends_on == ("jurisdiction",)
    assert finding.source_case_id == "test:c4"


def test_re_establishing_a_claim_updates_it_rather_than_duplicating(conn):
    # A later session that grounds a claim better should improve the
    # record. Two rows for one claim would show the case as having twice
    # the findings it has.
    create_case(conn, "test:c5", "A v. B")
    record_finding(conn, "test:c5", EstablishedFinding(claim="X applies", evidence_ids=("a",)))
    record_finding(conn, "test:c5", EstablishedFinding(claim="X applies", evidence_ids=("a", "b")))
    case = get_case(conn, "test:c5")
    assert len(case.findings) == 1
    assert case.findings[0].evidence_ids == ("a", "b")


def test_sessions_are_recorded_in_the_order_they_were_asked(conn):
    create_case(conn, "test:c6", "Patel v. Shah")
    for question in ("Can adverse possession apply?", "What proves ownership?", "Limitation period?"):
        record_session(conn, "test:c6", question)
    assert get_case(conn, "test:c6").research_questions == (
        "Can adverse possession apply?", "What proves ownership?", "Limitation period?",
    )


def test_an_unknown_case_is_none_not_an_error(conn):
    assert get_case(conn, "test:missing") is None


def test_listing_cases_does_not_load_their_contents(conn):
    create_case(conn, "test:c7", "A v. B")
    attach_document(conn, "test:c7", "doc-1")
    rows = [r for r in list_cases(conn) if r[0].startswith("test:")]
    assert rows
    case_id, title, updated_at = rows[0]
    assert isinstance(title, str) and isinstance(updated_at, datetime)


def test_deleting_a_case_takes_its_children_with_it(conn):
    create_case(conn, "test:c8", "A v. B")
    attach_document(conn, "test:c8", "doc-1")
    record_session(conn, "test:c8", "q")
    conn.execute("DELETE FROM cases WHERE case_id = 'test:c8'")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM case_documents WHERE case_id = 'test:c8'")
        assert cur.fetchone()[0] == 0
