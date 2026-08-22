"""Execute a plan. Deterministic -- no model call anywhere in this module.

The plan says what to do; this decides nothing. That separation is what lets
a canned plan be executed in a test with no API key, and what keeps the cost
of a round knowable before it is spent: a four-step plan costs four tool
calls, never "up to eight, discovered afterwards".

Tools are the Phase 2 contracts, unchanged.
"""

from __future__ import annotations

import inspect

from legal_ai.agents.planner import Plan, PlanStep
from legal_ai.schemas.evidence import Evidence
from legal_ai.tools import graph as graph_tools
from legal_ai.tools import judgments as judgment_tools
from legal_ai.tools import statutes as statute_tools

# Arguments forced on a tool regardless of what the plan asked for.
# Interactive research must not block on the live archive scan; fetching a
# judgment the corpus lacks is corpus growth and belongs on a background
# path, not in a research loop a person is waiting on.
FORCED_ARGS: dict[str, dict] = {
    "search_judgments": {"live": False},
}

# Results a search step returns. The tool default of 5 is tuned for a human
# reading a list. An agent that reranks afterwards needs a much deeper slice:
# hybrid_search already reranks ~50 candidates internally and truncates to
# `limit`, so a small limit means the agent reranks an already-truncated
# pool -- truncating twice and discarding most of what was considered.
DEFAULT_SEARCH_LIMIT = 40

_SEARCH_TOOLS = frozenset({"search_statutes", "search_judgments"})

TOOLS = {
    "search_statutes": statute_tools.search_statutes,
    "get_section": statute_tools.get_section,
    "search_judgments": judgment_tools.search_judgments,
    "get_judgment": judgment_tools.get_judgment,
    "find_citations": graph_tools.find_citations,
    "find_section_citations": graph_tools.find_section_citations,
    "find_judgment_sections": graph_tools.find_judgment_sections,
}


def _as_list(result) -> list[Evidence]:
    if result is None:
        return []
    return list(result) if isinstance(result, list) else [result]


def execute_step(step: PlanStep) -> list[Evidence]:
    """Run one step. A step that fails yields nothing rather than raising --
    one bad step must not lose the results of the steps that worked."""
    tool = TOOLS.get(step.tool)
    if tool is None:
        return []

    # Drop arguments the tool does not accept. A model naming a plausible
    # but wrong parameter would otherwise take down the whole step.
    accepted = set(inspect.signature(tool).parameters)
    args = {name: value for name, value in step.args.items() if name in accepted}
    if step.tool in _SEARCH_TOOLS and "limit" in accepted:
        args.setdefault("limit", DEFAULT_SEARCH_LIMIT)
    args.update(FORCED_ARGS.get(step.tool, {}))

    try:
        return _as_list(tool(**args))
    except Exception:
        return []


def execute_plan(plan: Plan) -> list[Evidence]:
    """Run every step, concatenating results and de-duplicating by id.

    The order here is plan order, which carries no relevance signal --
    ordering is restored by reranking in legal_ai.agents.research. Measured:
    returning this order directly scores MRR 0.338 against 0.467 for plain
    retrieval, because it discards the ranking fusion and reranking produce.
    """
    seen: set[str] = set()
    collected: list[Evidence] = []
    for step in plan.steps:
        for item in execute_step(step):
            key = item.document_id or id(item)
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
    return collected
