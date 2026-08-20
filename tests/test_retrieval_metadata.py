from datetime import date

import pytest

from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.retrieval.metadata import MetadataFilters, search_metadata


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_empty_filters_produce_no_sql():
    fragment, params = MetadataFilters().to_sql()
    assert fragment == ""
    assert params == []


def test_filters_compile_to_sql_fragment_and_params():
    fragment, params = MetadataFilters(document_type="section", court="Supreme Court of India").to_sql()
    assert "document_type = %s" in fragment
    assert "court = %s" in fragment
    assert fragment.startswith(" AND ")
    assert params == ["section", "Supreme Court of India"]


def test_date_range_filters_compile_to_sql():
    fragment, params = MetadataFilters(
        decision_date_from=date(2020, 1, 1), decision_date_to=date(2021, 12, 31)
    ).to_sql()
    assert "decision_date >= %s" in fragment
    assert "decision_date <= %s" in fragment
    assert params == [date(2020, 1, 1), date(2021, 12, 31)]


def test_search_metadata_resolves_a_real_statutory_reference(conn):
    # Section 18 of RERA is real, already-ingested data (act:2158:sec-18).
    results = search_metadata(
        conn, "What does Section 18 of the Real Estate (Regulation and Development) Act, 2016 say?"
    )

    assert ("act:2158:sec-18", 1.0) in results


def test_search_metadata_returns_empty_for_a_query_with_no_statutory_reference(conn):
    assert search_metadata(conn, "what are my rights when a builder delays possession") == []


def test_search_metadata_respects_document_type_filter(conn):
    results = search_metadata(
        conn,
        "Section 18 of the Real Estate (Regulation and Development) Act, 2016",
        filters=MetadataFilters(document_type="judgment"),
    )
    assert results == []
