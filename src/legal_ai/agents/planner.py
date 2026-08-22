"""The plan a research agent emits, and the model call that produces it.

The LLM never calls a tool. It emits a plan -- data -- and the executor runs
it. That keeps control flow in code, makes the stage testable with a canned
plan and no model, and makes cost knowable before it is spent.

The prompt's single most important instruction is to phrase queries in
**statutory vocabulary rather than the user's**. Measured on 2026-08-21
against the 50-question benchmark, that one change moves MRR from 0.467 to
0.670 -- more than the entire reranking mechanism contributes. A user writes
"builder did not give possession"; the statute says "promoter fails to give
possession", and retrieval cannot bridge that on its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from legal_ai.agents.rewrite import rewrite_query
from legal_ai.llm.client import generate

# Tools a plan may name. A step naming anything else is dropped rather than
# executed, so a hallucinated tool cannot reach the executor.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "search_statutes",
        "get_section",
        "search_judgments",
        "get_judgment",
        "find_citations",
        "find_section_citations",
        "find_judgment_sections",
    }
)


@dataclass(frozen=True)
class PlanStep:
    tool: str
    args: dict


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]

    def __bool__(self) -> bool:
        return bool(self.steps)


PROMPT = """You are planning a search of an Indian legal corpus of statutes
and judgments. You do not call tools; you write a plan that will be executed
for you.

{context}

Research angle: {angle}

Write queries in the vocabulary an Indian STATUTE would use, not the words a
member of the public would use. The corpus contains the statutes themselves,
so a query phrased as a grievance will not match. For example "builder did
not hand over my flat" should be planned as "promoter fails to give
possession return of amount".

Available tools:
  search_statutes       {{"query": "..."}}
  get_section           {{"act_id": "act:1234", "section_number": "18"}}
  search_judgments      {{"query": "..."}}
  get_judgment          {{"document_id": "judgment:..."}}
  find_citations        {{"judgment_id": "judgment:..."}}
  find_section_citations {{"section_id": "act:1234:sec-18"}}
  find_judgment_sections {{"judgment_id": "judgment:..."}}

Use get_section only when you already know the act_id. Prefer one or two
well-phrased searches over many vague ones. At most {max_steps} steps.

Return ONLY a JSON array of steps, each {{"tool": "...", "args": {{...}}}}."""


def parse_plan(raw: str, max_steps: int) -> Plan:
    """Parse a model response into a Plan, dropping anything malformed.

    Unknown tools, non-object args and non-list responses are discarded
    rather than trusted -- a hallucinated step must not reach the executor.
    Truncates to `max_steps`, so the cap holds even if the model ignores it.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except ValueError:
        return Plan(steps=())
    if not isinstance(parsed, list):
        return Plan(steps=())

    steps: list[PlanStep] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        args = item.get("args", {})
        if tool in ALLOWED_TOOLS and isinstance(args, dict):
            steps.append(PlanStep(tool=tool, args=args))
    return Plan(steps=tuple(steps[:max_steps]))


def build_plan(angle: str, context: str = "", max_steps: int = 8) -> Plan:
    """Ask the model for a plan for one research angle.

    The plan always *starts* with a search on a dedicated statutory-vocabulary
    rewrite of the angle. That single rewrite is the largest measured gain in
    the project -- MRR 0.467 to 0.670 on the 50-question benchmark, more than
    the whole reranking mechanism contributes -- and it is too valuable to
    leave to whether the planner happens to phrase its first query well. The
    planner's own steps follow it.

    Returns an empty Plan if everything fails; the caller decides whether an
    empty plan is a retry or a dead end, rather than an exception unwinding
    the whole research stage.
    """
    steps: list[PlanStep] = []

    rewritten = rewrite_query(angle)
    if rewritten:
        steps.append(PlanStep(tool="search_statutes", args={"query": rewritten}))

    prompt = PROMPT.format(
        context=context or "No additional context.", angle=angle, max_steps=max_steps
    )
    try:
        planned = parse_plan(generate(prompt), max_steps=max_steps)
    except Exception:
        planned = Plan(steps=())

    # De-duplicate: a planner query identical to the rewrite wastes a call.
    seen = {(step.tool, str(step.args)) for step in steps}
    for step in planned.steps:
        key = (step.tool, str(step.args))
        if key not in seen:
            seen.add(key)
            steps.append(step)

    return Plan(steps=tuple(steps[:max_steps]))
