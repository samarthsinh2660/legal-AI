"""Knowledge-graph routes. Read-only.

A reader may look at the citation graph; nothing here writes to it. The
corpus is not theirs to edit, and an endpoint that could change it would be
a way to make the law say something it does not.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.graph.repository import (
    MAX_NODES,
    OVERVIEW_BATCH,
    neighbourhood,
    overview,
)
from api.schemas import ErrorResponse
from api.utils.errors import not_found
from api.utils.response import respond, success
from legal_ai.graphdb.client import get_driver

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/overview")
async def graph_overview(
    request: Request,
    view: str = Query(default="judgments", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=OVERVIEW_BATCH, ge=1, le=OVERVIEW_BATCH),
):
    """A batch of the graph, without an anchor.

    `view` is `judgments`, `statutes`, or an Act id such as
    `act:ipc-1860` for that Act's sections. Declared before
    `/{document_id}` so these names are matched as a route rather than as
    a document id.

    Batched at 100: the graph is 50,890 nodes, and a force layout stops
    being readable long before that. `truncated` says another batch
    exists, so the viewer can offer more rather than implying it has shown
    everything.

    `total` is the size of the whole slice, sent on the first batch only.
    Without it "100 nodes" reads as the whole thing; the statutes slice
    holds 36,887.
    """
    driver = get_driver()
    try:
        found = overview(driver, view=view, offset=offset, limit=limit)
    finally:
        driver.close()

    return success({
        "nodes": found.nodes, "edges": found.edges, "truncated": found.truncated,
        "total": found.total,
    })


@router.get("/{document_id}", responses={404: {"model": ErrorResponse}})
async def graph_neighbourhood(
    request: Request,
    document_id: str,
    limit: int = Query(default=60, ge=2, le=MAX_NODES),
):
    """What this document connects to.

    ```
    nodes  [{id, kind, title, hops}]      kind: Judgment | Section | Act | Court
    edges  [{source, target, kind}]       kind: CITES | CITES_SECTION | CONTAINS | DECIDED_BY
    truncated  true when the cap cut it short
    ```

    One step out, and `limit` capped at 120: the point of this view is one
    thing and what touches it. A landmark judgment has ninety-five
    citations, and drawing all of them says less than a list would.

    **Render `truncated` where the reader can see it.** A graph quietly
    missing half its edges is a picture that lies about how connected
    something is.
    """
    driver = get_driver()
    try:
        found = neighbourhood(driver, document_id, limit=limit)
    finally:
        driver.close()

    if found is None:
        return respond(not_found("document"))
    return success({
        "nodes": found.nodes,
        "edges": found.edges,
        "truncated": found.truncated,
    })
