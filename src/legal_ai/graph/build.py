"""Assemble and compile the research graph.

The stage order is fixed and no model chooses it. That is what makes the
pipeline measurable: an execution path that changes every run cannot be
evaluated against a benchmark.

The only conditional edges are the two bounded loops -- clarification
halting for user input, and verification sending unsupported claims back to
research. Both terminate on a cap in graph.configuration, never on a model
deciding it is finished.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from legal_ai.graph import nodes
from legal_ai.graph.configuration import DEFAULT_CONFIG, GraphConfig
from legal_ai.graph.state import ResearchState


def _after_clarification(state: ResearchState) -> str:
    """Halt for the user rather than researching a question that a missing
    fact makes unanswerable -- a wrong state invalidates the whole run."""
    return END if state.get("clarification_needed") else "research"


def _after_verification(state: ResearchState, config: GraphConfig) -> str:
    """Re-research unsupported claims, up to the cap.

    The edge back to research is wired now but never taken: nothing produces
    claims until the Analyst lands in Phase 5, so there is nothing to find
    unsupported. Milestone 8 changes only this predicate, not the graph.

    The cap is checked first regardless, so the loop can never run away once
    the predicate goes live. On exhaustion the answer still ships with the
    unsupported claims flagged -- dropping them silently would leave a user
    unable to tell a short answer from an incomplete one.
    """
    if state.get("verification_passes", 0) >= config.max_verification_passes:
        return "draft"
    if state.get("unsupported_claims"):
        return "research"
    return "draft"


def build_research_graph(
    config: GraphConfig = DEFAULT_CONFIG,
    checkpointer: MemorySaver | None = None,
):
    """Compile the research graph.

    `checkpointer` persists a thread so it survives a restart; pass None for
    a one-shot run.
    """
    graph = StateGraph(ResearchState)

    graph.add_node("document", nodes.document)
    graph.add_node("context_builder", nodes.context_builder)
    graph.add_node("clarification", nodes.clarification)
    graph.add_node("research", nodes.research)
    graph.add_node("analyst", nodes.analyst)
    graph.add_node("verification", nodes.verification)
    graph.add_node("draft", nodes.draft)

    graph.add_edge(START, "document")
    graph.add_edge("document", "context_builder")
    graph.add_edge("context_builder", "clarification")
    graph.add_conditional_edges(
        "clarification", _after_clarification, {"research": "research", END: END}
    )
    graph.add_edge("research", "analyst")
    graph.add_edge("analyst", "verification")
    graph.add_conditional_edges(
        "verification",
        lambda state: _after_verification(state, config),
        {"research": "research", "draft": "draft"},
    )
    graph.add_edge("draft", END)

    return graph.compile(checkpointer=checkpointer)


research_graph = build_research_graph()
