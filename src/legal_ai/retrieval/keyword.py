"""Keyword search over the canonical store -- exact legal terminology signal.

Postgres native full-text search, ranked with ts_rank_cd. This is
TF-IDF-family, not BM25; naming it keyword search rather than BM25 is
deliberate. Real BM25 would require an external engine or the ParadeDB
pg_search extension.

Uses websearch_to_tsquery rather than plainto_tsquery so quoted phrases
and '-' negation work, and malformed input degrades instead of raising.

Requires the search_vector column and its GIN index (see
knowledge.static.db.ensure_retrieval_schema).
"""

from __future__ import annotations

import psycopg

from legal_ai.retrieval.metadata import MetadataFilters


def search_keyword(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
) -> list[tuple[str, float]]:
    filter_sql, filter_params = (filters or MetadataFilters()).to_sql()

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT document_id,
                   ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) AS rank
            FROM documents
            WHERE search_vector @@ websearch_to_tsquery('english', %s){filter_sql}
            ORDER BY rank DESC, document_id ASC
            LIMIT %s
            """,
            [query, query, *filter_params, limit],
        )
        rows = cur.fetchall()

    return [(document_id, float(rank)) for document_id, rank in rows]
