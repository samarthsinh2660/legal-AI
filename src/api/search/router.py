"""Search routes -- the corpus, directly.

The same retrieval a thread uses, without the agents around it: a reader who
knows what they are looking for should not have to ask a question to find it.

Read-only, and never a substitute for a researched answer -- results here
carry no verification, because nothing has been claimed about them yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.schemas import ErrorResponse
from api.utils.errors import invalid_request
from api.utils.response import respond, success

router = APIRouter(prefix="/search", tags=["search"])


def _statutory_phrasing(question: str) -> str | None:
    """`question` in the vocabulary a statute uses, or None.

    The planner's own call, so search and chat rewrite the same way. It is
    one model call, which is why search is slower than it was; the raw
    phrasing is still searched alongside, so nothing is lost when the
    rewrite is wrong.
    """
    from legal_ai.agents.research_plan import plan_research

    angles = plan_research(question, max_angles=1)
    return angles[0].query if angles else None

MAX_RESULTS = 50


@router.get("", responses={400: {"model": ErrorResponse}})
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=400),
    kind: str = Query(default="all", pattern="^(all|judgment|section)$"),
    limit: int = Query(default=20, ge=1, le=MAX_RESULTS),
):
    """Search the stored corpus.

    Hybrid retrieval: keyword, vector and metadata fused, then reranked --
    the same path a thread takes, so a document found here is one the
    research agents could also find.

    Results are **unverified by construction**. Nothing has been claimed
    about them, so there is nothing to check; a client must not render them
    with the badges an answer's citations carry.
    """
    from legal_ai.retrieval import hybrid
    from legal_ai.retrieval.metadata import MetadataFilters

    if not q.strip():
        return respond(invalid_request("A search needs something to search for."))

    filters = MetadataFilters(document_type=None if kind == "all" else kind)

    # A statute is written in statutory words and searched for in a
    # lawyer's. Searching both and fusing scores MRR 0.404 against 0.333
    # for the reader's phrasing alone. Chat has done this since 2026-09-02;
    # search passing the raw phrase made the same corpus answer worse here.
    query, also = q.strip(), None
    try:
        rewritten = _statutory_phrasing(q.strip())
    except Exception:
        rewritten = None
    if rewritten and rewritten != q.strip():
        query, also = rewritten, q.strip()

    try:
        results = hybrid.hybrid_search(query, limit=limit, filters=filters, also=also)
    except Exception:
        # Retrieval reaches two stores and an embedder; a reader gets a
        # sentence, and the traceback stays in the log.
        import logging

        logging.getLogger(__name__).exception("search failed")
        from api.utils.errors import internal_error

        return respond(internal_error("Search failed. See server logs."))

    return success([
        {
            "document_id": item.document_id,
            "kind": item.document_type,
            "title": item.title,
            "citation": getattr(item, "citation", None),
            "court": getattr(item, "court", None),
            "extract": (item.content or "")[:400],
        }
        for item in results
        if item.document_id
    ])
