"""Execute a plan. Deterministic -- no model call anywhere in this module.

The plan says what to do; this decides nothing. That separation is what lets
a canned plan run in a test with no API key, and what makes the cost of a
round knowable before it is spent: a four-step plan costs four tool calls,
never "up to eight, discovered afterwards".

Tool binding and invocation policy live in legal_ai.tools.registry, so an
agent never learns which source a result came from.
"""

from __future__ import annotations

from legal_ai.agents.planner import Plan, PlanStep
from legal_ai.schemas.evidence import Evidence
from legal_ai.tools.registry import get_tool, resolve_args


def _as_list(result) -> list[Evidence]:
    if result is None:
        return []
    return list(result) if isinstance(result, list) else [result]


def execute_step(step: PlanStep) -> list[Evidence]:
    """Run one step. A step that fails yields nothing rather than raising --
    one bad step must not lose the results of the steps that worked."""
    tool = get_tool(step.tool)
    if tool is None:
        return []
    try:
        return _as_list(tool(**resolve_args(step.tool, step.args)))
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
