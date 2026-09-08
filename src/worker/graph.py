"""Run the research graph, bounded, and report each node as it finishes.

Synchronous, because the worker is. The async version this replaces existed
to keep a blocking graph off an HTTP event loop; a worker has no loop to
protect, so the pump, the executor and the thread-safe queue all go away.

The deadline bounds what is watched, not what runs: Python cannot interrupt
a blocking call, so a run past its deadline keeps spending model budget
until it returns. Stopping one properly means checking between nodes, which
is where the caller already checks whether the run still exists.
"""

from __future__ import annotations

import logging
import os
import time

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 300.0

_graph = None


def read_timeout() -> float:
    """Read per run so it can be tuned without a code change, and so a bad
    value degrades to the default instead of refusing to start."""
    raw = os.environ.get("LEGAL_AI_RESEARCH_TIMEOUT")
    try:
        return float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _compiled():
    """The graph, assembled once.

    Assembling the nodes is pure setup, and doing it per job would put that
    cost on every question for no benefit. Also the seam the tests fake:
    driving a job needs no model, no network and no LangGraph internals.
    """
    global _graph
    if _graph is None:
        from legal_ai.graph.build import build_research_graph

        _graph = build_research_graph()
    return _graph


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


def stream_graph(inputs: dict):
    """Yield `("step", node)` per node, `("findings", …)` once, then `("done", state)`.

    Real steps, not a timer: each event is emitted when a node actually
    finishes, so a slow search shows as a step that sits there. The progress
    pane is required to show real work and never fake thinking, and a bar
    that advances on a clock is the thing that rule forbids.

    A failure is yielded rather than raised. The caller has already told the
    reader the run started and has a row to close; an exception escaping
    here would leave that row saying "running" forever.
    """
    # A question with no attached documents still runs the `document` node,
    # which returns immediately having read nothing. Announcing "Reading
    # your documents" for it claims work that did not happen, so the step is
    # suppressed rather than the node skipped -- the graph shape stays fixed.
    skip = set() if inputs.get("document_ids") else {"document"}
    deadline = time.monotonic() + read_timeout()
    state: dict = {}
    reported = False
    try:
        # An update the graph has produced is never discarded, and a graph
        # that has finished is never called a timeout -- both were wrong
        # before, and both threw away an answer that had already been paid
        # for. The two are told apart by asking for one more update:
        # a finished generator raises StopIteration at once, so the probe
        # costs nothing, while a graph with more to do reveals itself.
        stream = _compiled().stream(inputs)
        overrun = False
        while True:
            try:
                update = next(stream)
            except StopIteration:
                break
            if overrun:
                log.warning("research passed its deadline with work left")
                yield "timeout", None
                return
            for node, produced in update.items():
                state.update(produced or {})
                if node not in skip:
                    yield "step", node
                # Announced once, as soon as retrieval has paid for itself,
                # so a worker that dies later still leaves the evidence
                # behind for whoever picks the run up.
                if node == "research" and not reported and state.get("findings"):
                    reported = True
                    yield "findings", list(state["findings"])
            if time.monotonic() > deadline:
                overrun = True
    except Exception as exc:  # noqa: BLE001 - reported to the caller as a value
        yield "error", exc
        return
    yield "done", state
