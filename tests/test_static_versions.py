"""Amendment handling: superseded statute text survives re-ingestion."""

from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.store import (
    get_document,
    get_text_as_on,
    list_versions,
    upsert_document,
)
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, text: str, ingested_at: datetime) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="section",
        title=f"Title for {doc_id}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=ingested_at,
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=ingested_at,
    )


AT_2019 = datetime(2019, 1, 1, tzinfo=timezone.utc)
AT_2022 = datetime(2022, 1, 1, tzinfo=timezone.utc)
AT_2026 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
        cur.execute("DELETE FROM document_versions WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_unchanged_text_is_not_versioned(conn):
    # Re-ingesting an unchanged Act is the overwhelmingly common case --
    # it must not fill the history table with identical copies.
    upsert_document(conn, _doc("test:v1", "original text", AT_2019))
    upsert_document(conn, _doc("test:v1", "original text", AT_2022))
    assert list_versions(conn, "test:v1") == []


def test_amended_text_keeps_the_old_version(conn):
    upsert_document(conn, _doc("test:v2", "original text", AT_2019))
    upsert_document(conn, _doc("test:v2", "amended text", AT_2022))

    current = get_document(conn, "test:v2")
    assert current is not None and current.full_text == "amended text"

    history = list_versions(conn, "test:v2")
    assert [v.full_text for v in history] == ["original text"]
    assert history[0].observed_from == AT_2019
    assert history[0].observed_until == AT_2022


def test_as_on_a_date_before_the_amendment_returns_the_old_text(conn):
    # The text that governs is the one in force when the cause of action
    # arose. Quoting today's text for a 2020 dispute is a wrong answer,
    # not a stale one.
    upsert_document(conn, _doc("test:v3", "original text", AT_2019))
    upsert_document(conn, _doc("test:v3", "amended text", AT_2022))

    at_2020 = get_text_as_on(conn, "test:v3", datetime(2020, 6, 1, tzinfo=timezone.utc))
    assert at_2020 is not None
    assert at_2020.full_text == "original text"
    assert at_2020.is_current is False


def test_as_on_a_date_after_the_amendment_returns_the_current_text(conn):
    upsert_document(conn, _doc("test:v4", "original text", AT_2019))
    upsert_document(conn, _doc("test:v4", "amended text", AT_2022))

    now = get_text_as_on(conn, "test:v4", AT_2026)
    assert now is not None
    assert now.full_text == "amended text"
    assert now.is_current is True
    assert now.observed_until is None


def test_two_amendments_resolve_to_the_middle_version(conn):
    upsert_document(conn, _doc("test:v5", "first", AT_2019))
    upsert_document(conn, _doc("test:v5", "second", AT_2022))
    upsert_document(conn, _doc("test:v5", "third", AT_2026))

    assert len(list_versions(conn, "test:v5")) == 2
    mid = get_text_as_on(conn, "test:v5", datetime(2023, 1, 1, tzinfo=timezone.utc))
    assert mid is not None and mid.full_text == "second"


def test_text_that_never_changed_answers_from_the_live_row(conn):
    upsert_document(conn, _doc("test:v6", "never amended", AT_2019))
    result = get_text_as_on(conn, "test:v6", datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert result is not None
    assert result.full_text == "never amended"
    assert result.is_current is True


def test_unknown_document_returns_none(conn):
    assert get_text_as_on(conn, "test:missing", AT_2026) is None


def test_text_reverting_to_an_earlier_wording_keeps_both_versions(conn):
    # A correction to a bad scrape can put back text we already stored.
    # Keyed on content_hash this would collide; the surrogate version_id
    # is what makes an A -> B -> A history representable.
    upsert_document(conn, _doc("test:v7", "text A", AT_2019))
    upsert_document(conn, _doc("test:v7", "text B", AT_2022))
    upsert_document(conn, _doc("test:v7", "text A", AT_2026))
    assert [v.full_text for v in list_versions(conn, "test:v7")] == ["text A", "text B"]
