"""_check_db: title matching happens in SQL, not by pulling the corpus.

_check_db returns a ranked list of CanonicalDocument. It used to return a
single JudgmentSearchResult, which was what limited the lazy cache to
growing one judgment per lookup.
"""

from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.judgments.dynamic_search import (
    DB_TITLE_WORD_OVERLAP_THRESHOLD,
    _check_db,
)
from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef

AT = datetime(2026, 8, 24, tzinfo=timezone.utc)


def _judgment(doc_id: str, title: str) -> CanonicalDocument:
    text = "judgment body " * 40
    return CanonicalDocument(
        document_id=doc_id,
        document_type="judgment",
        title=title,
        full_text=text,
        content_hash=content_hash(text + doc_id),
        provenance=Provenance(
            source=SourceRef(name="test", url="https://x", source_type="primary"),
            retrieved_at=AT,
            licence="test",
            attribution_required=False,
        ),
        ingested_at=AT,
    )


@pytest.fixture
def stored():
    connection = get_connection()
    ensure_schema(connection)
    upsert_document(connection, _judgment("test:j1", "Ramesh Kumar vs State of Kerala"))
    upsert_document(connection, _judgment("test:j2", "Sunita Devi vs Union of India"))
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_finds_the_matching_judgment_by_title(stored):
    found = _check_db("Ramesh Kumar vs State of Kerala")
    assert [d.document_id for d in found] == ["test:j1"]


def test_partial_title_above_the_threshold_still_matches(stored):
    # A user rarely types the full cause title; "Sunita Devi Union India"
    # is 4 of 4 significant words, all present in j2's title.
    found = _check_db("Sunita Devi Union India")
    assert [d.document_id for d in found] == ["test:j2"]


def test_an_unrelated_query_matches_nothing(stored):
    assert _check_db("insolvency resolution professional appointment") == []


def test_words_shorter_than_the_word_pattern_do_not_inflate_overlap(stored):
    # "vs" and "of" are below the 3-letter floor on both sides, so they
    # can neither be required of a candidate nor lift a weak match over
    # the threshold.
    assert _check_db("vs of") == []


def test_a_query_with_no_usable_words_returns_none(stored):
    assert _check_db("!! ?? ..") == []


def test_the_threshold_is_a_fraction_of_the_query_not_the_title(stored):
    # One shared word out of five is 0.2 -- below the bar -- even though
    # the shared word is distinctive. Matching on the query's side keeps
    # a long stored title from being matched by a single lucky hit.
    assert DB_TITLE_WORD_OVERLAP_THRESHOLD > 0.2
    assert _check_db("Ramesh contract breach damages arbitration") == []


# --- multi-result lookup (the lazy cache grew one document per query) ---

def test_the_db_check_returns_as_many_as_asked_for(stored):
    from legal_ai.ingestion.judgments.dynamic_search import _check_db

    # Both stored titles share "vs" only, which is below the word floor, so
    # a query covering both must name words from each.
    found = _check_db("Ramesh Kumar State Kerala", limit=5)
    assert [d.document_id for d in found] == ["test:j1"]


def test_the_db_check_still_honours_the_threshold(stored):
    from legal_ai.ingestion.judgments.dynamic_search import _check_db

    assert _check_db("insolvency resolution professional", limit=5) == []


def test_a_lookup_stops_at_one(stored):
    from legal_ai.ingestion.judgments.dynamic_search import search_judgment

    result = search_judgment("Ramesh Kumar vs State of Kerala", live=False)
    assert result.found
    assert len(result.documents) == 1
    # `document` stays available for callers that want exactly one.
    assert result.document.document_id == "test:j1"


def test_discovery_asks_for_more_than_one(stored):
    from legal_ai.ingestion.judgments.dynamic_search import search_judgments

    # Only one stored judgment matches, so this reports a partial result
    # rather than pretending it filled the request.
    result = search_judgments("Ramesh Kumar State Kerala", limit=5, live=False)
    assert result.found
    assert len(result.documents) == 1
    assert "1 of 5 requested" in result.notes[0]


def test_nothing_stored_and_no_live_search_reports_both_facts(stored):
    from legal_ai.ingestion.judgments.dynamic_search import search_judgments

    result = search_judgments("wholly unrelated arbitration query", limit=5, live=False)
    assert result.found is False
    assert "live search was not attempted" in result.notes[0]


def test_the_judgment_fetch_limit_is_far_below_the_statute_limit():
    # A statute result is a row already in Postgres; a judgment result is a
    # PDF fetched from a third party. Forty of those answers one question
    # with forty outbound requests.
    from legal_ai.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.judgment_search_limit < DEFAULT_CONFIG.search_limit
