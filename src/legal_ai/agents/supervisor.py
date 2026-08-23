"""Research a question: plan the angles, search them, summarise.

One or two model calls per question, regardless of how many angles:

    1. plan_research   question -> angles + statutory queries
    2. summarise       ONLY when the findings are too long to hand over as
                       they are -- summarising can only lose detail, so it
                       is not worth a call on a short result

An earlier version made five calls at one angle and thirteen at three --
decompose, then rewrite, plan, assess and compress per angle. Rewrite and
plan produced the same thing (a query) and decompose produced it a third
time, so they are one call now. Assess is gone: with the queries chosen up
front there is nothing for a second round to reconsider that a wider search
would not have caught first.

Control flow is code. The model decides how many angles and how to phrase
the queries -- both ambiguity. It never decides what runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from legal_ai.agents.research_plan import Angle, plan_research
from legal_ai.agents.validator import validate
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.retrieval.rerank import rerank as rerank_candidates
from legal_ai.schemas.evidence import Evidence
from legal_ai.tools.registry import get_tool, resolve_args

SUMMARISE_PROMPT = """Summarise these retrieved Indian legal provisions for
a colleague researching: {question}

{findings}

At most 150 words. State what the provisions say. Do not add law that is not
shown above."""


@dataclass(frozen=True)
class ResearchResult:
    question: str
    angles: list[Angle] = field(default_factory=list)
    summary: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def agents_spawned(self) -> int:
        """Angles searched. Tracked as a cost metric -- a lookup question
        staying at 1 is the signal that decomposition is not over-firing."""
        return len(self.angles)


def _search(query: str) -> list[Evidence]:
    """One statutory search. No model call."""
    tool = get_tool("search_statutes")
    try:
        return list(tool(**resolve_args("search_statutes", {"query": query})))
    except Exception:
        return []


def _rank(question: str, evidence: list[Evidence], limit: int) -> list[Evidence]:
    """Order the union by relevance to the original question.

    Measured 2026-08-23, and it settles an argument. The alternative --
    fusing each angle's ranked list by RRF, on the reasoning that each list
    is already ranked against its own statutory query -- scored MRR 0.508
    against this cross-encoder's 0.542. Preserving per-angle order loses
    more than it saves: the cross-encoder scores each passage against what
    was actually asked, and that comparison is worth more than the ordering
    it overwrites.
    """
    by_id = {item.document_id: item for item in evidence if item.document_id}
    if len(by_id) <= 1:
        return list(by_id.values())[:limit]
    try:
        ranked = rerank_candidates(
            question, [(doc_id, item.content[:2000]) for doc_id, item in by_id.items()],
            limit=limit,
        )
    except Exception:
        return list(by_id.values())[:limit]
    return [by_id[doc_id] for doc_id, _score in ranked if doc_id in by_id]


def summarise(question: str, evidence: list[Evidence]) -> str:
    """Findings for the caller, summarised only when they are too long.

    Below `summarise_above_chars` the provisions are handed over as they
    are: a model call there costs latency and quota to *lose* detail, since
    the titles and passages already say what a reader needs. The threshold
    is the point where a list stops being readable at a glance.

    When a summary is made, the Evidence ids are appended structurally
    rather than asked for. A summary that loses them makes every downstream
    claim ungroundable, and that must not depend on a model complying.
    """
    if not evidence:
        return "No supporting provisions were retrieved."

    rendered = "\n\n".join(
        f"[{item.document_id}] {item.title or ''}\n{item.content[:600]}" for item in evidence
    )
    ids = ", ".join(item.document_id for item in evidence if item.document_id)

    if len(rendered) <= DEFAULT_CONFIG.summarise_above_chars:
        return f"{rendered}\n\nSources: {ids}"

    try:
        text = generate(
            SUMMARISE_PROMPT.format(question=question, findings=rendered),
            max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
        )
    except Exception:
        text = f"Retrieved {len(evidence)} provisions."
    return f"{text.strip()}\n\nSources: {ids}"


def research(
    question: str,
    context: str = "",
    max_angles: int = DEFAULT_CONFIG.max_concurrent_research_units,
    limit: int = DEFAULT_CONFIG.limit_per_angle,
    conn: psycopg.Connection | None = None,
) -> ResearchResult:
    """Plan, search every angle, validate, rank, summarise."""
    angles = plan_research(question, context=context, max_angles=max_angles)

    collected: list[Evidence] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for angle in angles:
        result = validate(_search(angle.query), conn=conn)
        dropped.extend(result.dropped)
        for item in result.kept:
            if item.document_id not in seen:
                seen.add(item.document_id)
                collected.append(item)

    ranked = _rank(question, collected, limit=limit)
    return ResearchResult(
        question=question,
        angles=angles,
        summary=summarise(question, ranked),
        evidence=ranked,
        dropped=dropped,
    )
