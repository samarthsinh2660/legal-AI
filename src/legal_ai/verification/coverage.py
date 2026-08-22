"""Coverage -- did the research miss something it should have found?

Groundedness inspects what was said. **Nothing inspects what was not said**,
and that is the failure a user actually experiences: an answer that is
entirely true and quietly incomplete.

The real answer is the active layer -- "threads like this relied on Section
X, which this run never retrieved" -- but that data does not exist until
Phase 6 builds the write side. Until then this runs a deterministic
stand-in over the graph edges that already exist: if the answer cites a
section, does its parent Act contain closely-related sections that were
never retrieved?

The stand-in is crude and will raise false prompts. It is a placeholder for
Phase 6 and should be judged as one -- its value is that the *slot* exists
and runs, not that its suggestions are reliable.
"""

from __future__ import annotations

import psycopg

# Sections suggested per answer. A long list is noise, and noise in a
# "you may have missed this" prompt is worse than silence.
MAX_SUGGESTIONS = 5


def _act_of(section_id: str) -> str | None:
    """Parent Act id of a section id like `act:2158:sec-18`."""
    parts = section_id.split(":")
    return f"{parts[0]}:{parts[1]}" if len(parts) >= 3 and parts[0] == "act" else None


def suggest_missed_sections(
    conn: psycopg.Connection,
    cited_ids: list[str],
    retrieved_ids: set[str],
    query: str,
) -> list[tuple[str, str]]:
    """Sections of a cited Act that this run never retrieved.

    Returns (document_id, title), ranked by similarity to `query` so the
    suggestions are at least on topic rather than merely adjacent.
    """
    acts = {act for act in (_act_of(doc_id) for doc_id in cited_ids) if act}
    if not acts:
        return []

    from legal_ai.knowledge.static.embeddings import embed

    exclude = list(retrieved_ids | set(cited_ids))
    # MATERIALIZED is load-bearing, not decoration. Ordering by distance
    # under a selective WHERE lets the HNSW index scan globally and then
    # discard nearly everything, returning nothing at all -- the same
    # approximate-index behaviour Phase 2 hit. A plain CTE does not help,
    # because Postgres inlines it and the index comes straight back;
    # MATERIALIZED forces the filter to run first. A single Act is a few
    # dozen rows, so the exact scan that follows is cheap.
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH candidates AS MATERIALIZED (
                SELECT document_id, title, embedding
                FROM documents
                WHERE document_type = 'section'
                  AND act_id = ANY(%s)
                  AND NOT (document_id = ANY(%s))
                  AND embedding IS NOT NULL
            )
            SELECT document_id, title
            FROM candidates
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (list(acts), exclude, embed(query), MAX_SUGGESTIONS),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]
