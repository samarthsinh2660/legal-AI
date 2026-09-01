from datetime import datetime, timezone

import pytest

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_act_section, write_judgment
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.tools.graph import (
    find_citations,
    find_judgment_sections,
    find_leading_authorities,
    find_section_citations,
)


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


def test_find_leading_authorities_ranks_the_most_cited_first(conn, driver):
    """The point of the tool: a heavily-litigated section returns dozens of
    judgments, and an unranked list leaves the reader to triage them."""
    act = _doc("test:act-7", "act", "Test Act, 2026", "An Act to test ranking.")
    section = _doc(
        "test:act-7:sec-4", "section", "Section 4", "Section four body text.",
        act_id="test:act-7",
    )
    upsert_document(conn, act, embedding=_sparse_vector((1, 1.0)))
    upsert_document(conn, section, embedding=_sparse_vector((2, 1.0)))
    write_act_section(driver, act, section)

    # Twice: CITES_SECTION now requires a judgment to be *about* a section
    # (retrieval.conflict.MIN_MENTIONS), not merely to name it once.
    on_point = (
        "The question under Section 4 of the Test Act, 2026 arises here. "
        "Section 4 of the Test Act, 2026 is therefore decisive."
    )
    leading = _doc("test:j-leading", "judgment", "Leading Case", on_point, court="Test Court")
    leading = leading.model_copy(update={"citation": "[2015] 1 S.C.R. 100"})
    minor = _doc("test:j-minor", "judgment", "Minor Case", on_point, court="Test Court")
    minor = minor.model_copy(update={"citation": "[2016] 2 S.C.R. 200"})
    upsert_document(conn, leading, embedding=_sparse_vector((3, 1.0)))
    upsert_document(conn, minor, embedding=_sparse_vector((4, 1.0)))
    write_judgment(driver, leading, pg_conn=conn)
    write_judgment(driver, minor, pg_conn=conn)

    # Two judgments cite the leading case, none cite the minor one.
    for n, follower_id in enumerate(("test:j-f1", "test:j-f2")):
        follower = _doc(
            follower_id, "judgment", f"Follower {n}",
            on_point + " Following [2015] 1 S.C.R. 100.", court="Test Court",
        )
        upsert_document(conn, follower, embedding=_sparse_vector((10 + n, 1.0)))
        write_judgment(driver, follower, pg_conn=conn)

    results = find_leading_authorities("test:act-7:sec-4", limit=5)
    ranked = [r.document_id for r in results]

    assert ranked[0] == "test:j-leading"
    assert "test:j-minor" in ranked, "an uncited judgment is ranked last, not dropped"


def test_find_leading_authorities_on_a_section_nothing_cites(conn, driver):
    act = _doc("test:act-8", "act", "Test Act, 2026", "An Act nobody litigates.")
    section = _doc(
        "test:act-8:sec-1", "section", "Section 1", "Section one body text.",
        act_id="test:act-8",
    )
    upsert_document(conn, act, embedding=_sparse_vector((20, 1.0)))
    upsert_document(conn, section, embedding=_sparse_vector((21, 1.0)))
    write_act_section(driver, act, section)

    assert find_leading_authorities("test:act-8:sec-1") == []


# --- good law over a real edge ----------------------------------------------
#
# tests/retrieval/test_retrieval_good_law.py already pins the decision rule on
# synthetic input. What is exercised here is the seam under it: an OVERRULED
# written onto a CITES edge in Neo4j, read back and turned into a warning.
# Until the corpus held its first overruling (PRAKASH v. PHULAVATI, overruled
# by VINEETA SHARMA) that path had never run on a real negative, so the
# expensive half of the badge -- the half that says "do not rely on this" --
# had only ever been asserted about a tuple.

def _overrule(driver, overruled_id: str, overruling_id: str) -> None:
    with driver.session() as session:
        session.run(
            """
            MATCH (citing:Judgment {document_id: $citing})
            MATCH (cited:Judgment {document_id: $cited})
            MERGE (citing)-[r:CITES]->(cited)
            SET r.treatment = 'OVERRULED'
            """,
            citing=overruling_id,
            cited=overruled_id,
        )


def test_an_overruled_judgment_comes_back_doubted(conn, driver):
    from legal_ai.retrieval.good_law import GoodLaw
    from legal_ai.tools.graph import is_still_good_law

    overruled = _doc("test:j-overruled", "judgment", "Earlier Case", "the earlier holding", court="Test Court")
    overruling = _doc("test:j-overruling", "judgment", "Later Case", "the earlier holding is wrongly decided", court="Test Court")
    upsert_document(conn, overruled, embedding=_sparse_vector((8, 1.0)))
    upsert_document(conn, overruling, embedding=_sparse_vector((9, 1.0)))
    write_judgment(driver, overruled)
    write_judgment(driver, overruling)
    _overrule(driver, "test:j-overruled", "test:j-overruling")

    result = is_still_good_law("test:j-overruled")

    assert result.status is GoodLaw.DOUBTED
    assert result.overruled_by == ("test:j-overruling",)
    assert result.is_a_warning


def test_the_overruling_judgment_itself_is_not_doubted(conn, driver):
    """The edge points one way. Reading it backwards would condemn every
    judgment that overruled something."""
    from legal_ai.retrieval.good_law import GoodLaw
    from legal_ai.tools.graph import is_still_good_law

    overruled = _doc("test:j-overruled", "judgment", "Earlier Case", "the earlier holding", court="Test Court")
    overruling = _doc("test:j-overruling", "judgment", "Later Case", "wrongly decided", court="Test Court")
    upsert_document(conn, overruled, embedding=_sparse_vector((8, 1.0)))
    upsert_document(conn, overruling, embedding=_sparse_vector((9, 1.0)))
    write_judgment(driver, overruled)
    write_judgment(driver, overruling)
    _overrule(driver, "test:j-overruled", "test:j-overruling")

    assert is_still_good_law("test:j-overruling").status is not GoodLaw.DOUBTED


def test_the_warning_names_the_judgment_that_overruled_it(conn, driver):
    """A warning that does not say what to go and read is not actionable."""
    from legal_ai.agents.draft import render_good_law
    from legal_ai.tools.graph import is_still_good_law

    overruled = _doc("test:j-overruled", "judgment", "Earlier Case", "the earlier holding", court="Test Court")
    overruling = _doc("test:j-overruling", "judgment", "Later Case", "wrongly decided", court="Test Court")
    upsert_document(conn, overruled, embedding=_sparse_vector((8, 1.0)))
    upsert_document(conn, overruling, embedding=_sparse_vector((9, 1.0)))
    write_judgment(driver, overruled)
    write_judgment(driver, overruling)
    _overrule(driver, "test:j-overruled", "test:j-overruling")

    rendered = render_good_law(is_still_good_law("test:j-overruled"))

    assert "test:j-overruling" in rendered
    assert "overruled" in rendered.lower()
