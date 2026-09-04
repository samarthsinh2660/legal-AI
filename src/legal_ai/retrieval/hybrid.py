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
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.retrieval.graph_search import expand_via_graph
from legal_ai.retrieval.type_floor import apply_type_floor
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


def _exact_first(ranked_ids: list[str], exact_ids: list[str]) -> list[str]:
    """`ranked_ids` with exact statutory matches moved to the front.

    A reference resolved to a document id is ground truth, not a candidate:
    search_metadata returns it or nothing. Ranking it against the other
    signals loses it twice over. RRF deliberately damps a single signal's
    rank-1 vote, so two signals agreeing on a near-miss outscore it; and the
    cross-encoder then scores the section's text against the question, which
    for a question about dates rather than substance reads as a poor match.
    Measured on evals/datasets/retrieval_citations.json: "Section 138 ...
    has the 15-day period expired" resolved s.138 at rank 1, which became
    rank 43 after reranking and rank 75 after fusing both passes.
    """
    if not exact_ids:
        return ranked_ids
    pinned = list(dict.fromkeys(exact_ids))
    seen = set(pinned)
    return pinned + [document_id for document_id in ranked_ids if document_id not in seen]


def _with_floor(conn, ranked_ids: list[str], limit: int, enabled: bool) -> list[str]:
    """`ranked_ids` cut to `limit`, keeping one statute in view when asked."""
    if not enabled or not ranked_ids:
        return ranked_ids[:limit]
    rows = conn.execute(
        "SELECT document_id, document_type FROM documents WHERE document_id = ANY(%s)",
        (ranked_ids,),
    ).fetchall()
    return apply_type_floor(ranked_ids, dict(rows), limit)


def _fused_order(query: str, also: str | None, search_once) -> list[str]:
    """Document ids for `query`, fused with those for `also`.

    The reader's own wording and the statutory rewrite find different
    things: measured over evals/datasets/retrieval.json, rewriting alone
    rescued three questions that missed and broke eight that worked.
    Fusing both scored MRR 0.469 against 0.311 raw and 0.350 rewritten,
    and recall@1 36% against 16%.

    Fusion is by rank, so the two lists' incomparable scores never meet.
    """
    first = search_once(query)
    if not also or also.strip() == query.strip():
        return first
    second = search_once(also)
    fused = reciprocal_rank_fusion([
        [(document_id, 0.0) for document_id in first],
        [(document_id, 0.0) for document_id in second],
    ])
    return [document_id for document_id, _score in fused]


def hybrid_search(
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
    # OFF for now: measured effect is nil today because the citation edges
    # it would traverse barely exist yet. Can be turned on once the corpus
    # is much bigger -- re-measure first, see the docstring below.
    expand_graph: bool = False,
    rerank: bool = True,
    type_floor: bool | None = None,
    also: str | None = None,
) -> list[Evidence]:
    """Retrieve the most relevant stored documents for `query`.

    `also` is a second phrasing of the same question -- typically the
    statutory rewrite where `query` is the reader's own words. Both are
    searched and the results fused by rank; see `_fused_order` for the
    numbers. It costs a second retrieval, so pass it only where the
    rewrite already exists.

    Searches only what is already stored; fetching new judgments from live
    sources is legal_ai.tools.judgments.search_judgments.

    `rerank` runs a cross-encoder over the top RERANK_CANDIDATES results.
    On by default because it is load-bearing, not polish: without it this
    pipeline measures MRR 0.345 on the versioned 50-question benchmark,
    with it 0.467. (An older 15-query set reported 0.299 to 0.530; that set
    was never committed and is not comparable.) It costs
    roughly a second or two per query on CPU; pass rerank=False, or set
    RERANK_MODEL to the lighter L-6, where latency matters more.

    `expand_graph` is OFF, and stays off on measurement rather than on
    assumption.

    It was first left off when the citation edges it traverses barely
    existed. Re-measured 2026-08-28 at 7,200 judgments and 521 CITES
    edges, on the 50-question set:

        expand_graph=False    MRR 0.325   recall@10 56%
        expand_graph=True     MRR 0.318   recall@10 60%

    (Measured at 7,204 judgments, before type interleaving.)

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
    # None means "use the configured default", so a caller that says
    # nothing follows Configuration and a caller that passes a value wins.
    if type_floor is None:
        type_floor = DEFAULT_CONFIG.interleave_result_types

    fetch = limit * _SIGNAL_OVERFETCH
    if rerank:
        fetch = max(fetch, RERANK_CANDIDATES)

    conn = get_connection()
    try:
        def search_once(one: str) -> list[str]:
            signal_results = [
                search_keyword(conn, one, limit=fetch, filters=filters),
                search_vector(conn, one, limit=fetch, filters=filters),
                search_metadata(conn, one, limit=fetch, filters=filters),
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
                shortlist = [
                    document_id for document_id, _score in fused[:RERANK_CANDIDATES]
                ]
                passages = best_passages(conn, one, shortlist)
                # Rerank the whole shortlist, not the top `limit`: the
                # statute the floor promotes is usually below the cut, and
                # truncating first would leave nothing to promote.
                reranked = rerank_candidates(one, passages, limit=len(shortlist))
                if reranked:
                    return [document_id for document_id, _score in reranked]

            return [document_id for document_id, _score in fused]

        # Resolved before fusion so a match survives it. Both phrasings are
        # tried: the planner's statutory rewrite drops the "Section N of the
        # X Act" word order the parser needs, so on the rewrite alone the
        # lookup is silent.
        exact_ids = [document_id for document_id, _score in
                     search_metadata(conn, query, limit=fetch, filters=filters)]
        if also:
            exact_ids += [document_id for document_id, _score in
                          search_metadata(conn, also, limit=fetch, filters=filters)]

        order = _fused_order(query, also, search_once)
        ordered = _with_floor(conn, order, limit, type_floor)
        return build_evidence(
            conn, _exact_first(ordered, exact_ids)[:limit], query=query
        )
    finally:
        conn.close()
