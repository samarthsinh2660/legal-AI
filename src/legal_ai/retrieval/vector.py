"""Vector search over the canonical store -- semantic similarity signal.

Returns (document_id, distance) rather than whole documents so the fan-in
can fuse cheaply and fetch full text only for the survivors.

Scores are cosine DISTANCE: lower is better.

Separate from knowledge.static.store.find_similar, which stays unfiltered
because other callers depend on that behaviour.
"""

from __future__ import annotations

import psycopg

from legal_ai.knowledge.static.embeddings import embed
from legal_ai.retrieval.metadata import MetadataFilters

# Relevance floor: nearest-neighbour search has no notion of "nothing here
# is relevant", so without this a meaningless query still returns the
# least-distant documents in the corpus.
#
# Model-specific -- re-measure whenever EMBEDDING_MODEL changes. Current
# value separates real legal queries (<= ~0.51) from nonsense (>= ~0.66)
# for all-mpnet-base-v2.
DEFAULT_MAX_DISTANCE = 0.60


def search_vector(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
    max_distance: float | None = DEFAULT_MAX_DISTANCE,
) -> list[tuple[str, float]]:
    """Semantically nearest documents, excluding ones beyond the relevance floor.

    Pass max_distance=None to disable the floor and get raw nearest
    neighbours (useful for diagnostics, or for re-measuring the threshold).
    """
    filter_sql, filter_params = (filters or MetadataFilters()).to_sql()
    query_embedding = embed(query)

    def distance_clause(column: str) -> tuple[str, list]:
        if max_distance is None:
            return "", []
        return f" AND ({column} <=> %s::vector) <= %s", [query_embedding, max_distance]

    doc_distance_sql, doc_distance_params = distance_clause("embedding")
    chunk_distance_sql, chunk_distance_params = distance_clause("c.embedding")

    with conn.cursor() as cur:
        # Whole-document vectors: short documents that were embedded intact.
        cur.execute(
            f"""
            SELECT document_id, embedding <=> %s::vector AS distance
            FROM documents
            WHERE embedding IS NOT NULL{filter_sql}{doc_distance_sql}
            ORDER BY distance ASC
            LIMIT %s
            """,
            [query_embedding, *filter_params, *doc_distance_params, limit],
        )
        rows = list(cur.fetchall())

        # Chunk vectors: long documents, whose own embedding is NULL because
        # a truncated whole-document vector would misrepresent them.
        chunk_filter_sql, _ = (filters or MetadataFilters()).to_sql(alias="d")
        cur.execute(
            f"""
            SELECT c.document_id, c.embedding <=> %s::vector AS distance
            FROM document_chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.embedding IS NOT NULL{chunk_filter_sql}{chunk_distance_sql}
            ORDER BY distance ASC
            LIMIT %s
            """,
            [query_embedding, *filter_params, *chunk_distance_params, limit],
        )
        rows.extend(cur.fetchall())

    # A document may match through several chunks; report it once, at its
    # best distance, so one long document cannot crowd out the results.
    best: dict[str, float] = {}
    for document_id, distance in rows:
        distance = float(distance)
        if document_id not in best or distance < best[document_id]:
            best[document_id] = distance

    return sorted(best.items(), key=lambda item: item[1])[:limit]
