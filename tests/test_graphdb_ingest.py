# tests/test_graphdb_ingest.py
from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.schemas.evidence import Provenance, SourceRef


def _act(doc_id: str, title: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=title,
        full_text=title,
        content_hash=content_hash(title),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def _section(doc_id: str, title: str, act_id: str) -> CanonicalDocument:
    doc = _act(doc_id, title)
    return doc.model_copy(update={"document_type": "section", "act_id": act_id})


def _judgment(doc_id: str, title: str, court: str, full_text: str) -> CanonicalDocument:
    doc = _act(doc_id, title)
    return doc.model_copy(update={
        "document_type": "judgment", "court": court, "full_text": full_text,
        "content_hash": content_hash(full_text),
    })


@pytest.fixture
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run(
            "MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n"
        )
    d.close()


def test_write_act_section_creates_contains_edge(driver):
    act = _act("test:act-1", "Specific Relief Act, 1963")
    section = _section("test:act-1:sec-6", "Section 6", "test:act-1")

    write_act_section(driver, act, section)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Act {document_id: 'test:act-1'})-[:CONTAINS]->(s:Section {document_id: 'test:act-1:sec-6'})
            RETURN a.title AS act_title, s.title AS section_title
            """
        )
        record = result.single()
    assert record["act_title"] == "Specific Relief Act, 1963"
    assert record["section_title"] == "Section 6"


def test_write_judgment_creates_decided_by_edge(driver):
    judgment = _judgment("test:j-1", "Rame Gowda v. Varadappa Naidu", "Supreme Court of India", "no citations here")

    write_judgment(driver, judgment)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (j:Judgment {document_id: 'test:j-1'})-[:DECIDED_BY]->(c:Court {name: 'Supreme Court of India'})
            RETURN j.title AS title
            """
        )
        record = result.single()
    assert record["title"] == "Rame Gowda v. Varadappa Naidu"


def test_write_judgment_creates_cites_edge_to_already_ingested_judgment(driver):
    cited = _judgment("test:j-cited", "Nair Service Society v. K.C. Alexander", "Supreme Court of India", "AIR 1968 SC 1165")
    write_judgment(driver, cited)

    citing = _judgment(
        "test:j-citing",
        "Rame Gowda v. Varadappa Naidu",
        "Supreme Court of India",
        "This follows AIR 1968 SC 1165 closely.",
    )
    citing = citing.model_copy(update={"citation": "AIR 1968 SC 1165"})
    write_judgment(driver, citing)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (a:Judgment {document_id: 'test:j-citing'})-[:CITES]->(b:Judgment {document_id: 'test:j-cited'})
            RETURN b.title AS title
            """
        )
        record = result.single()
    assert record is not None
    assert record["title"] == "Nair Service Society v. K.C. Alexander"
