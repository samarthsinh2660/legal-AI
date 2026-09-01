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
    return _compiled().invoke(inputs)


def _compiled():
    global _graph
    if _graph is None:
        from legal_ai.graph.build import build_research_graph

        _graph = build_research_graph()
    return _graph


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


# What each node is doing, in the reader's language. The keys are the graph's
# own node names, so a renamed node shows as itself rather than silently
# dropping out of the list.
STEP_LABELS = {
    "document": "Reading your documents",
    "context_builder": "Understanding the question",
    "clarification": "Checking what is missing",
    "research": "Searching statutes and judgments",
    "analyst": "Drafting the analysis",
    "verification": "Checking every claim against its source",
    "draft": "Assembling the answer",
}


async def research_with_progress(inputs: dict):
    """Run the graph, yielding one event per completed node, then the answer.

    Real steps, not a timer: each event is emitted when a node actually
    finishes, so a slow search shows as a slow step rather than a progress
    bar that has learned to lie. `design/UX_FLOWS.md` is explicit that this
    pane "shows real work, never fake thinking".

    A 114-second wait with no feedback reads as a hung page. This does not
    make it faster; it makes it legible.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    def pump() -> None:
        # `stream` is a blocking generator, so it runs in a thread and hands
        # each update back through the loop -- the same reason `research`
        # uses to_thread.
        try:
            state = {}
            for update in _compiled().stream(inputs):
                for node, produced in update.items():
                    state.update(produced or {})
                    loop.call_soon_threadsafe(queue.put_nowait, ("step", node))
            loop.call_soon_threadsafe(queue.put_nowait, ("done", state))
        except Exception as exc:  # noqa: BLE001 - reported, then re-raised to the caller
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, (_DONE, None))

    task = loop.run_in_executor(None, pump)
    # One deadline for the whole run. Per-event timeouts reset on each node,
    # so a graph emitting a step every 299s would run unbounded while the
    # docstring claimed the wait was capped.
    deadline = loop.time() + read_timeout()
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            kind, payload = await asyncio.wait_for(queue.get(), timeout=remaining)
            if kind is _DONE:
                return
            if kind == "error":
                # Yielded, not raised. The response is already 200 with its
                # headers sent, so an exception here truncates the stream
                # with no event and no way for a client to tell it from a
                # completed one.
                yield "error", payload
                return
            yield kind, payload
    except asyncio.TimeoutError:
        log.warning("research stream timed out")
        yield "timeout", TimeoutError("Research did not finish within the time limit.")
    finally:
        task.cancel()
