# tests/graph/test_graphdb_treatment.py
"""The model pass that fills in CITES.treatment.

The deterministic half is `ingestion/treatment_table.py`, tested separately.
This covers what the model pass must never do: overwrite a reading the
reporter already stated, and record a shrug as though it were a reading.
Both would corrupt the only signal `good_law` has, and neither would be
visible in the answer -- a wrong treatment renders exactly like a right one.
"""

from datetime import datetime, timezone

import pytest

import legal_ai.graphdb.treatment as treatment_pass
from legal_ai.agents.treatment import Treatment, TreatmentFinding
from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.treatment import classify_untreated
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef

# The citing judgment's text has to contain the cited case's citation for
# `extract_citation_contexts` to find a passage to classify.
CITING_TEXT = (
    "This Court considered the decision in Ram v. Shyam, [2015] 4 S.C.R. 676, "
    "at length. For the reasons that follow we are unable to agree with the "
    "view taken therein, and it is accordingly held to be wrongly decided."
)


def _judgment(doc_id: str, text: str, citation: str | None = None) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="judgment",
        title=doc_id,
        court="Supreme Court of India",
        citation=citation,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="Test", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
            licence="Test",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )


@pytest.fixture
def graph():
    """A citing judgment, a cited judgment, and one untreated CITES edge."""
    conn = get_connection()
    upsert_document(conn, _judgment("test:t-citing", CITING_TEXT))
    upsert_document(conn, _judgment("test:t-cited", "The judgment under appeal."))
    conn.commit()

    driver = get_driver()
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Judgment {document_id: 'test:t-citing'})
            MERGE (b:Judgment {document_id: 'test:t-cited'})
            SET b.citation_key = '20154SCR676'
            MERGE (a)-[:CITES]->(b)
            """
        )
    yield driver, conn
    with driver.session() as session:
        session.run("MATCH (n) WHERE n.document_id STARTS WITH 'test:' DETACH DELETE n")
    driver.close()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    conn.commit()
    conn.close()


def _stub(monkeypatch, treatment: Treatment, why: str = "test stub"):
    """Answer for the fixture's own edge only, and record what was asked.

    The pass runs against the whole graph, and the graph is the real corpus.
    Answering for anything but `test:t-cited` would write a treatment onto a
    real citation -- an invented OVERRULED is precisely the failure this
    subsystem exists to prevent, and it would reach a reader as a warning on
    a judgment nobody examined.
    """
    calls = []

    def fake(pairs):
        calls.append(list(pairs))
        return [
            TreatmentFinding(
                citation=citation,
                treatment=treatment if citation == "test:t-cited" else Treatment.NOT_CHECKED,
                why=why,
            )
            for citation, _context in pairs
        ]

    monkeypatch.setattr(treatment_pass, "classify_treatments", fake)
    return calls


def _asked_about(calls) -> set[str]:
    return {citation for batch in calls for citation, _context in batch}


def _treatment_of(driver) -> str | None:
    with driver.session() as session:
        return session.run(
            "MATCH (:Judgment {document_id: 'test:t-citing'})-[r:CITES]->() "
            "RETURN r.treatment AS t"
        ).single()["t"]


def test_an_untreated_edge_is_classified(graph, monkeypatch):
    driver, conn = graph
    _stub(monkeypatch, Treatment.OVERRULED)

    result = classify_untreated(driver, conn, limit=5)

    assert result.written == 1
    assert result.counts == {"OVERRULED": 1}
    assert _treatment_of(driver) == "OVERRULED"


def test_a_shrug_writes_nothing(graph, monkeypatch):
    # NOT_CHECKED is what an edge with no treatment already reads as.
    # Recording it would make an unexamined edge look examined.
    driver, conn = graph
    _stub(monkeypatch, Treatment.NOT_CHECKED)

    result = classify_untreated(driver, conn, limit=5)

    assert result.written == 0
    assert _treatment_of(driver) is None


def test_an_edge_the_reporter_already_stated_is_not_reclassified(graph, monkeypatch):
    # The reporter's own table beat the model outright and cost nothing.
    # Spending a call to overwrite it would be worse than free -- it would
    # replace a printed fact with a guess.
    driver, conn = graph
    with driver.session() as session:
        session.run(
            "MATCH (:Judgment {document_id: 'test:t-citing'})-[r:CITES]->() "
            "SET r.treatment = 'FOLLOWED'"
        )
    calls = _stub(monkeypatch, Treatment.OVERRULED)

    classify_untreated(driver, conn, limit=5)

    assert "test:t-cited" not in _asked_about(calls), "already treated, still asked"
    assert _treatment_of(driver) == "FOLLOWED"


def test_no_call_is_spent_when_nothing_is_untreated(graph, monkeypatch):
    driver, conn = graph
    with driver.session() as session:
        session.run(
            "MATCH (:Judgment {document_id: 'test:t-citing'})-[r:CITES]->() "
            "SET r.treatment = 'CONSIDERED'"
        )
    calls = _stub(monkeypatch, Treatment.OVERRULED)

    classify_untreated(driver, conn, limit=5)

    assert "test:t-cited" not in _asked_about(calls)
    assert _treatment_of(driver) == "CONSIDERED"


def test_the_call_budget_is_respected(graph, monkeypatch):
    driver, conn = graph
    calls = _stub(monkeypatch, Treatment.FOLLOWED)

    classify_untreated(driver, conn, limit=0)

    assert calls == [], "a zero budget still spent a call"


# --- the batch lookup the draft node uses ---------------------------------


def test_lookup_reports_an_overruling(graph):
    from legal_ai.retrieval.good_law import GoodLaw, good_law_lookup
    driver, _conn = graph
    with driver.session() as session:
        session.run(
            "MATCH (:Judgment {document_id:'test:t-citing'})-[r:CITES]->() "
            "SET r.treatment = 'OVERRULED'"
        )

    result = good_law_lookup(driver, ["test:t-cited"])["test:t-cited"]

    assert result.status is GoodLaw.DOUBTED
    assert result.overruled_by == ("test:t-citing",)


def test_one_unclassified_citation_withholds_the_clean_bill(graph):
    # Any citing judgment we failed to classify could be the overruling, so
    # a single unclassified edge is enough to withhold NO_NEGATIVE_TREATMENT.
    from legal_ai.retrieval.good_law import GoodLaw, good_law_lookup
    driver, _conn = graph
    with driver.session() as session:
        session.run(
            """
            MATCH (b:Judgment {document_id:'test:t-cited'})
            MERGE (c:Judgment {document_id:'test:t-other'})
            MERGE (c)-[r:CITES]->(b) SET r.treatment = 'FOLLOWED'
            """
        )

    result = good_law_lookup(driver, ["test:t-cited"])["test:t-cited"]

    assert result.status is GoodLaw.NOT_CHECKED


def test_every_citation_classified_and_none_negative_is_clean(graph):
    from legal_ai.retrieval.good_law import GoodLaw, good_law_lookup
    driver, _conn = graph
    with driver.session() as session:
        session.run(
            "MATCH (:Judgment {document_id:'test:t-citing'})-[r:CITES]->() "
            "SET r.treatment = 'FOLLOWED'"
        )

    result = good_law_lookup(driver, ["test:t-cited"])["test:t-cited"]

    assert result.status is GoodLaw.NO_NEGATIVE_TREATMENT
    assert result.checked == ("test:t-citing",)


def test_a_judgment_nothing_cites_is_not_checked(graph):
    from legal_ai.retrieval.good_law import GoodLaw, good_law_lookup
    driver, _conn = graph

    result = good_law_lookup(driver, ["test:t-citing"])["test:t-citing"]

    # Absence of citing judgments here is absence of coverage, never
    # absence of overrulings.
    assert result.status is GoodLaw.NOT_CHECKED
