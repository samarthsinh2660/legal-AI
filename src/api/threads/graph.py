"""Run the research graph, bounded, off the event loop.

The graph is synchronous and slow, so calling it from an async handler would
block the loop and stall every other request including `/health`.

The timeout bounds the client's wait, not the run: Python cannot interrupt a
blocking call, so a timed-out request keeps spending model budget until it
finishes. Cancelling properly needs a job queue.
"""

from __future__ import annotations

import asyncio
import logging
import os

from api.utils.errors import Ok, Result, timeout as timeout_failure

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0

_graph = None


def run_graph(inputs: dict) -> dict:
    """Invoke the compiled research graph. Blocking, called in a thread.

    Compiled once and reused: `build_research_graph` assembles nodes and is
    pure setup, but doing it per request would put that cost on every
    question for no benefit.

    This is also the seam the tests fake. Keeping the graph call in one
    named function means a test of the HTTP layer needs no model, no
    network and no database, and does not have to reach into LangGraph
    internals to say so.

    It does not catch: whatever the graph raises is by definition
    unexpected, and the router's outermost boundary handles it once.
    """
    global _graph
    if _graph is None:
        from legal_ai.graph.build import build_research_graph

        _graph = build_research_graph()
    return _graph.invoke(inputs)


async def research(inputs: dict) -> Result:
    """Run the graph off the event loop, bounded by the timeout.

    The timeout is the one outcome caught here, because it is an expected
    one: a slow question is not a bug, and the router needs it as a value
    to map to 504.
    """
    timeout = read_timeout()
    try:
        return Ok(await asyncio.wait_for(asyncio.to_thread(run_graph, inputs), timeout))
    except asyncio.TimeoutError:
        log.warning("research timed out after %ss", timeout)
        return timeout_failure("Research did not finish within the time limit.")


def read_timeout() -> float:
    """Read per request so it can be tuned without a code change, and so a
    bad value degrades to the default instead of refusing to start."""
    raw = os.environ.get("LEGAL_AI_RESEARCH_TIMEOUT")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
