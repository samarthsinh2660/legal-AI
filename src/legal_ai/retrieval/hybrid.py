"""Hybrid retrieval -- fan a query across signals, fuse, expand, build Evidence.

The signals produce mutually incomparable scores: cosine distance (lower
is better), ts_rank_cd (higher is better, unbounded) and exact match
(boolean). Fusion is therefore by rank, via Reciprocal Rank Fusion, which
avoids having to normalise those scales against each other.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.retrieval.evidence_builder import build_evidence
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.retrieval.keyword import search_keyword
from legal_ai.retrieval.metadata import MetadataFilters, search_metadata
from legal_ai.retrieval.rerank import rerank as rerank_candidates
from legal_ai.retrieval.vector import best_passages, search_vector
from legal_ai.schemas.evidence import Evidence

# Standard RRF constant (Cormack et al., 2009). Large enough that the gap
# between rank 1 and rank 2 does not outweigh agreement between signals.
RRF_K = 60

# Signals over-fetch so fusion can promote documents several signals agree
# on, even when none ranked them first.
_SIGNAL_OVERFETCH = 3

# Shortlist size handed to the reranker. Deliberately generous: the largest
# measured gains came from documents sitting at ranks 20-35, which a
# shorter shortlist would simply never show the reranker.
RERANK_CANDIDATES = 50


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked lists: score(d) = sum over lists of 1 / (k + rank).

    Input scores are ignored; only position matters, which is what makes
    incomparable scales safe to combine.
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
    # OFF for now: measured effect is nil today because the citation edges
    # it would traverse barely exist yet. Can be turned on once the corpus
    # is much bigger -- re-measure first, see the docstring below.
    expand_graph: bool = False,
    rerank: bool = True,
) -> list[Evidence]:
    """Retrieve the most relevant stored documents for `query`.

    Searches only what is already stored; fetching new judgments from live
    sources is legal_ai.tools.judgments.search_judgments.

    `rerank` runs a cross-encoder over the top RERANK_CANDIDATES results.
    On by default because it is load-bearing, not polish: without it this
    pipeline measured MRR 0.299 on the benchmark, with it 0.530 -- both at
    18 judgments; see PHASE_7 §4 for the current, lower numbers. It costs
    roughly a second or two per query on CPU; pass rerank=False, or set
    RERANK_MODEL to the lighter L-6, where latency matters more.

    `expand_graph` is OFF, and stays off on measurement rather than on
    assumption.

    It was first left off when the citation edges it traverses barely
    existed. Re-measured 2026-08-28 at 7,200 judgments and 521 CITES
    edges, on the 50-question set:

        expand_graph=False    MRR 0.325   recall@10 56%
        expand_graph=True     MRR 0.318   recall@10 60%

    No measurable effect, for +0.5s per query. Re-measure again before
    switching it on -- more edges can mean more noise, since a
    heavily-cited section expands into hundreds of loosely-related
    candidates. If it hurts then, the fix is edge weighting (down-weight
    hub nodes, require agreement across several seeds), not simply
    disabling it again.

    Note that every question in that dataset expects a statute section, so
    the benchmark can detect harm from expansion but cannot measure what a
    judgment-citation graph would win. That needs a judgment eval set,
    which does not exist yet. The explicit graph tools in
    legal_ai.tools.graph answer structural questions directly and need no
    such tuning.
    """
    # With reranking on, the signals must return at least the shortlist the
    # reranker expects -- otherwise the deep candidates it exists to rescue
    # are never retrieved in the first place.
    fetch = limit * _SIGNAL_OVERFETCH
    if rerank:
        fetch = max(fetch, RERANK_CANDIDATES)

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

        if rerank and fused:
            shortlist = [document_id for document_id, _score in fused[:RERANK_CANDIDATES]]
            passages = best_passages(conn, query, shortlist)
            reranked = rerank_candidates(query, passages, limit=limit)
            if reranked:
                return build_evidence(
                    conn, [document_id for document_id, _score in reranked], query=query
                )

        top_ids = [document_id for document_id, _score in fused[:limit]]
        return build_evidence(conn, top_ids, query=query)
    finally:
        conn.close()
