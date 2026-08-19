"""Vector search over the canonical store -- semantic similarity.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The existing knowledge.static.store.find_similar is deliberately left
untouched: several callers depend on its current unfiltered behaviour.
This adds MetadataFilters support and returns ids rather than whole
documents, so the fan-in can fuse cheaply and fetch full text only once,
at the end, for the documents that actually survive.

Scores are cosine DISTANCE -- lower is better -- matching find_similar and
the pgvector <=> operator.
"""

from __future__ import annotations

import psycopg

from legal_ai.knowledge.static.embeddings import embed
from legal_ai.retrieval.metadata import MetadataFilters

# Relevance floor. Nearest-neighbour search always returns *something* --
# it has no notion of "nothing here is relevant" -- so without a floor a
# meaningless query still returns the least-distant documents in the
# corpus, and an agent could ground a legal answer in them. That failure
# mode is worse than returning nothing.
#
# Derived by measurement against the real ~36k-document corpus on
# 2026-08-19, not picked by feel:
#   nonsense queries      best distance 0.716 - 0.724
#   real legal questions  best distance 0.264 - 0.468
# 0.65 sits in the empty gap between those two ranges.
#
# This constant is specific to the current embedding model
# (all-MiniLM-L6-v2). Re-measure it when the model changes -- the
# embeddings provider abstraction (Milestone 5 sub-project 2) will change
# it, and a stale threshold would silently distort recall.
DEFAULT_MAX_DISTANCE = 0.65


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

    distance_sql = ""
    distance_params: list = []
    if max_distance is not None:
        distance_sql = " AND (embedding <=> %s::vector) <= %s"
        distance_params = [query_embedding, max_distance]

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT document_id, embedding <=> %s::vector AS distance
            FROM documents
            WHERE embedding IS NOT NULL{filter_sql}{distance_sql}
            ORDER BY distance ASC
            LIMIT %s
            """,
            [query_embedding, *filter_params, *distance_params, limit],
        )
        rows = cur.fetchall()

    return [(document_id, float(distance)) for document_id, distance in rows]
