from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.schemas.evidence import Provenance, SourceRef


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
def driver():
    d = get_driver()
    yield d
    with d.session() as session:
        session.run("MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n")
    d.close()


def test_expand_finds_sections_contained_by_a_seed_act(driver):
    act = _doc("test:g-act", "act", "Test Act, 2026", "An Act.")
    section = _doc("test:g-act:sec-1", "section", "Section 1", "Body.", act_id="test:g-act")
    write_act_section(driver, act, section)

    results = expand_via_graph(driver, ["test:g-act"])

    assert "test:g-act:sec-1" in [doc_id for doc_id, _score in results]


def test_expand_excludes_the_seeds_themselves(driver):
    act = _doc("test:g-act2", "act", "Test Act, 2026", "An Act.")
    section = _doc("test:g-act2:sec-1", "section", "Section 1", "Body.", act_id="test:g-act2")
    write_act_section(driver, act, section)

    results = expand_via_graph(driver, ["test:g-act2"])

    assert "test:g-act2" not in [doc_id for doc_id, _score in results]


def test_expand_ranks_a_document_reached_by_two_seeds_above_one_reached_by_one(driver):
    shared = _doc("test:g-shared", "section", "Shared Section", "Body.", act_id="test:g-a")
    act_a = _doc("test:g-a", "act", "Act A", "Body.")
    act_b = _doc("test:g-b", "act", "Act B", "Body.")
    lonely = _doc("test:g-lonely", "section", "Lonely Section", "Body.", act_id="test:g-b")
    write_act_section(driver, act_a, shared)
    write_act_section(driver, act_b, shared)
    write_act_section(driver, act_b, lonely)

    results = expand_via_graph(driver, ["test:g-a", "test:g-b"])
    scores = dict(results)

    assert scores["test:g-shared"] > scores["test:g-lonely"]


def test_expand_returns_empty_for_no_seeds(driver):
    assert expand_via_graph(driver, []) == []


def test_expand_returns_empty_when_a_seed_has_no_neighbours(driver):
    judgment = _doc("test:g-lone-judg", "judgment", "Lone Case", "no citations here", court="Test Court")
    write_judgment(driver, judgment)

    assert expand_via_graph(driver, ["test:g-lone-judg"]) == []
