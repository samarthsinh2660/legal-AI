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
    from legal_ai.retrieval.hybrid import hybrid_search
    from legal_ai.retrieval.metadata import MetadataFilters

    if not q.strip():
        return respond(invalid_request("A search needs something to search for."))

    filters = MetadataFilters(document_type=None if kind == "all" else kind)
    try:
        results = hybrid_search(q.strip(), limit=limit, filters=filters)
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
