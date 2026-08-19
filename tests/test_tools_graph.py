from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.graph import find_citations, find_judgment_sections, find_section_citations


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _doc(
    doc_id: str,
    doc_type: str,
    title: str,
    text: str,
    act_id: str | None = None,
    court: str | None = None,
) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=title,
        act_id=act_id,
        court=court,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="Test Source", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Test",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


@pytest.fixture
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run("MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n")
    d.close()


def test_find_citations_returns_cited_judgment_as_evidence(conn, driver):
    citing_text = "This case follows (2019) 8 SCC 729 closely."
    cited = _doc("test:j-cited", "judgment", "Cited Case", "the cited judgment full text", court="Test Court")
    citing = _doc("test:j-citing", "judgment", "Citing Case", citing_text, court="Test Court")
    cited = cited.model_copy(update={"citation": "(2019) 8 SCC 729"})
    upsert_document(conn, cited, embedding=_sparse_vector((5, 1.0)))
    upsert_document(conn, citing, embedding=_sparse_vector((6, 1.0)))
    write_judgment(driver, cited)
    write_judgment(driver, citing)

    results = find_citations("test:j-citing")

    assert len(results) == 1
    assert results[0].document_id == "test:j-cited"
    assert results[0].content == "the cited judgment full text"


def test_find_citations_returns_empty_list_when_no_citations(conn, driver):
    judgment = _doc("test:j-lonely", "judgment", "Lonely Case", "no citations here", court="Test Court")
    upsert_document(conn, judgment, embedding=_sparse_vector((7, 1.0)))
    write_judgment(driver, judgment)

    assert find_citations("test:j-lonely") == []


def test_find_section_citations_and_find_judgment_sections_are_symmetric(conn, driver):
    act = _doc("test:act-3", "act", "Test Act, 2026", "An Act to test things.")
    section = _doc("test:act-3:sec-9", "section", "Section 9", "Section nine body text.", act_id="test:act-3")
    judgment_text = "The Authority under Section 9 of the Test Act, 2026 held..."
    judgment = _doc("test:j-sec", "judgment", "Section-Citing Case", judgment_text, court="Test Court")

    upsert_document(conn, act, embedding=_sparse_vector((8, 1.0)))
    upsert_document(conn, section, embedding=_sparse_vector((9, 1.0)))
    upsert_document(conn, judgment, embedding=_sparse_vector((10, 1.0)))
    write_act_section(driver, act, section)
    write_judgment(driver, judgment, pg_conn=conn)

    citing_judgments = find_section_citations("test:act-3:sec-9")
    assert len(citing_judgments) == 1
    assert citing_judgments[0].document_id == "test:j-sec"

    cited_sections = find_judgment_sections("test:j-sec")
    assert len(cited_sections) == 1
    assert cited_sections[0].document_id == "test:act-3:sec-9"
    assert cited_sections[0].content == "Section nine body text."
