"""Keyword search over the canonical store -- exact legal terminology.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

This is Postgres native full-text search ranked with ts_rank_cd, which is
TF-IDF-family -- deliberately NOT called BM25 anywhere, because it is not
BM25. Real BM25 would need an external engine or the ParadeDB pg_search
extension; that trade was made explicitly in the design, and having exact
keyword matching at all matters far more here than the ranking formula.

websearch_to_tsquery (rather than plainto_tsquery) parses user input the
way a search box does: quoted phrases and negation with '-' work, and
malformed input degrades gracefully instead of raising.
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
