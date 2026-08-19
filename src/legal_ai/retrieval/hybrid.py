"""Hybrid retrieval -- fan the query out across signals, fuse, expand, build.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The three signals produce mutually incomparable scores: cosine distance
(lower is better), ts_rank_cd (higher is better, unbounded), and exact
match (boolean). Normalising those against each other would be arbitrary
and fragile, so fusion is by RANK, via Reciprocal Rank Fusion.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.retrieval.evidence_builder import build_evidence
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.retrieval.keyword import search_keyword
from legal_ai.retrieval.metadata import MetadataFilters, search_metadata
from legal_ai.retrieval.vector import search_vector
from legal_ai.schemas.evidence import Evidence

# The constant from the original RRF paper (Cormack et al., 2009). Large
# enough that the gap between rank 1 and rank 2 does not dominate agreement
# between signals -- which is the whole point of fusing.
RRF_K = 60

# Each signal returns more candidates than the caller asked for, so fusion
# has room to promote documents that several signals agree on but none
# ranked first.
_SIGNAL_OVERFETCH = 3


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked lists by rank: score(d) = sum over lists of 1 / (k + rank).

    Input scores are ignored on purpose -- only position matters, which is
    what makes incomparable scales safe to combine.
    """
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (document_id, _score) in enumerate(ranked, start=1):
            fused[document_id] = fused.get(document_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))


def hybrid_search(
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
    expand_graph: bool = False,
) -> list[Evidence]:
    """Retrieve the most relevant stored documents for `query`.

    Searches only what is already in the store. Fetching new judgments from
    live external sources is a different job, done by
    legal_ai.tools.judgments.search_judgments.

    `expand_graph` defaults to False on measured evidence, not preference.
    Measured 2026-08-19 on the real corpus for "builder failed to give
    possession on time refund": expansion added six documents, of which one
    was relevant (RERA s.31) and five were noise (the New Delhi Municipal
    Council Act among them). The graph is simply too sparse to help yet --
    six judgments, so most CITES/CITES_SECTION edges do not exist. Turn it
    back on (and re-measure) once the judgment corpus is substantially
    larger; the machinery is built and tested, it is just not earning its
    place at this corpus size.
    """
    fetch = limit * _SIGNAL_OVERFETCH
    conn = get_connection()
    try:
        signal_results = [
            search_keyword(conn, query, limit=fetch, filters=filters),
            search_vector(conn, query, limit=fetch, filters=filters),
            search_metadata(conn, query, limit=fetch, filters=filters),
        ]
        fused = reciprocal_rank_fusion(signal_results)

        if expand_graph and fused:
            seeds = [document_id for document_id, _score in fused[:limit]]
            driver = get_driver()
            try:
                expanded = expand_via_graph(driver, seeds, limit=fetch)
            finally:
                driver.close()
            if expanded:
                fused = reciprocal_rank_fusion([fused, expanded])

        top_ids = [document_id for document_id, _score in fused[:limit]]
        return build_evidence(conn, top_ids)
    finally:
        conn.close()
