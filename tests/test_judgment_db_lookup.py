"""_check_db: title matching happens in SQL, not by pulling the corpus."""

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
    result = _check_db("Ramesh Kumar vs State of Kerala")
    assert result is not None
    assert result.document is not None
    assert result.document.document_id == "test:j1"
    assert result.source == "database"


def test_partial_title_above_the_threshold_still_matches(stored):
    # A user rarely types the full cause title; "Sunita Devi Union India"
    # is 4 of 4 significant words, all present in j2's title.
    result = _check_db("Sunita Devi Union India")
    assert result is not None and result.document.document_id == "test:j2"


def test_an_unrelated_query_matches_nothing(stored):
    assert _check_db("insolvency resolution professional appointment") is None


def test_words_shorter_than_the_word_pattern_do_not_inflate_overlap(stored):
    # "vs" and "of" are below the 3-letter floor on both sides, so they
    # can neither be required of a candidate nor lift a weak match over
    # the threshold.
    assert _check_db("vs of") is None


def test_a_query_with_no_usable_words_returns_none(stored):
    assert _check_db("!! ?? ..") is None


def test_the_threshold_is_a_fraction_of_the_query_not_the_title(stored):
    # One shared word out of five is 0.2 -- below the bar -- even though
    # the shared word is distinctive. Matching on the query's side keeps
    # a long stored title from being matched by a single lucky hit.
    assert DB_TITLE_WORD_OVERLAP_THRESHOLD > 0.2
    assert _check_db("Ramesh contract breach damages arbitration") is None
