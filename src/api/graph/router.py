"""Knowledge-graph routes. Read-only.

A reader may look at the citation graph; nothing here writes to it. The
corpus is not theirs to edit, and an endpoint that could change it would be
a way to make the law say something it does not.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.graph.repository import MAX_HOPS, MAX_NODES, neighbourhood
from api.schemas import ErrorResponse
from api.utils.errors import not_found
from api.utils.response import respond, success
from legal_ai.graphdb.client import get_driver

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{document_id}", responses={404: {"model": ErrorResponse}})
async def graph_neighbourhood(
    request: Request,
    document_id: str,
    hops: int = Query(default=1, ge=1, le=MAX_HOPS),
    limit: int = Query(default=60, ge=2, le=MAX_NODES),
):
    """What this document connects to.

    ```
    nodes  [{id, kind, title, hops}]      kind: Judgment | Section | Act | Court
    edges  [{source, target, kind}]       kind: CITES | CITES_SECTION | CONTAINS | DECIDED_BY
    truncated  true when the cap cut it short
    ```

    `hops` is capped at 2 and `limit` at 120, because the point of this view
    is one thing and what touches it. A landmark judgment has ninety-five
    citations, and drawing all of them says less than a list would.

    **Render `truncated` where the reader can see it.** A graph quietly
    missing half its edges is a picture that lies about how connected
    something is.
    """
    driver = get_driver()
    try:
        found = neighbourhood(driver, document_id, hops=hops, limit=limit)
    finally:
        driver.close()

    if found is None:
        return respond(not_found("document"))
    return success({
        "nodes": found.nodes,
        "edges": found.edges,
        "truncated": found.truncated,
    })
