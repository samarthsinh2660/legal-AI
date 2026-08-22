"""One research agent: owns one angle, returns a compressed finding.

Control flow lives here, in code. The model is consulted at exactly two
bounded points per round and each produces data, never actions:

    1. plan      what to search      (legal_ai.agents.planner)
    2. assess    is this enough      (below)

Everything between them -- executing the plan, validating what came back,
deciding whether to loop -- is deterministic. The loop terminates on
`max_rounds`, never on the model choosing to stop.

Compression exists so a supervisor receives summaries rather than every
retrieved document. The evidence ids are appended structurally rather than
left to the model, because a summary that loses them makes every downstream
claim ungroundable and the groundedness check then fails open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from legal_ai.agents.executor import execute_plan
from legal_ai.agents.planner import build_plan
from legal_ai.agents.validator import validate
from legal_ai.llm.client import generate
from legal_ai.retrieval.rerank import rerank as rerank_candidates
from legal_ai.schemas.evidence import Evidence

from legal_ai.config import DEFAULT_CONFIG

# Set in legal_ai.config.settings, which carries the reasoning.
DEFAULT_MAX_ROUNDS = DEFAULT_CONFIG.max_agent_rounds
DEFAULT_LIMIT = DEFAULT_CONFIG.limit_per_angle


def rank_by_relevance(angle: str, evidence: list[Evidence], limit: int) -> list[Evidence]:
    """Order collected evidence by relevance to the angle.

    A plan's steps each return ranked results, but concatenating those lists
    produces plan order, which carries no relevance signal. Measured:
    skipping this step scores MRR 0.338 against 0.467 for plain retrieval --
    the agent was discarding the ranking that fusion and reranking exist to
    produce. The cross-encoder scores each passage against the angle
    directly, which is exactly the comparison that was lost.
    """
    if len(evidence) <= 1:
        return evidence[:limit]

    by_id = {item.document_id: item for item in evidence if item.document_id}
    pairs = [(doc_id, item.content[:2000]) for doc_id, item in by_id.items()]
    try:
        ranked = rerank_candidates(angle, pairs, limit=limit)
    except Exception:
        return evidence[:limit]
    return [by_id[doc_id] for doc_id, _score in ranked if doc_id in by_id]

ASSESS_PROMPT = """You are checking whether research on one angle is done.

Angle: {angle}

Retrieved so far:
{findings}

If these cover the angle, reply exactly: SUFFICIENT
Otherwise reply with one short line naming what is still missing."""

COMPRESS_PROMPT = """Summarise these retrieved legal provisions for a
colleague researching: {angle}

{findings}

Write at most 150 words. State what the provisions say. Do not add law that
is not shown above."""


@dataclass(frozen=True)
class ResearchResult:
    angle: str
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    rounds: int = 0
    dropped: list[tuple[str, str]] = field(default_factory=list)


def _render(evidence: list[Evidence]) -> str:
    return "\n\n".join(
        f"[{item.document_id}] {item.title or ''}\n{item.content[:600]}" for item in evidence
    )


def assess(angle: str, evidence: list[Evidence]) -> str | None:
    """None when the angle is covered, else what is still missing.

    A model failure is treated as "covered" so a flaky API stops the loop
    rather than spinning it -- the cap would catch it anyway, at cost.
    """
    if not evidence:
        return "nothing was retrieved"
    try:
        reply = generate(ASSESS_PROMPT.format(angle=angle, findings=_render(evidence)))
    except Exception:
        return None
    return None if reply.strip().upper().startswith("SUFFICIENT") else reply.strip()[:200]


def compress(angle: str, evidence: list[Evidence]) -> str:
    """Summarise, then append the evidence ids structurally.

    Appending rather than instructing is deliberate. Asking the model to
    keep the ids would make the phase's highest-risk failure depend on it
    complying; appending makes losing them impossible.
    """
    if not evidence:
        return "No supporting provisions were retrieved for this angle."
    try:
        summary = generate(COMPRESS_PROMPT.format(angle=angle, findings=_render(evidence)))
    except Exception:
        summary = f"Retrieved {len(evidence)} provisions for: {angle}"

    ids = ", ".join(item.document_id for item in evidence if item.document_id)
    return f"{summary.strip()}\n\nSources: {ids}"


def research_angle(
    angle: str,
    context: str = "",
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_steps: int = 8,
    limit: int = DEFAULT_LIMIT,
    conn: psycopg.Connection | None = None,
) -> ResearchResult:
    """Research one angle and return a compressed, validated finding.

    `conn` is optional. When omitted this opens its own connection, so
    angles running in parallel each get one -- a psycopg connection is not
    thread-safe, and sharing one would either corrupt state or force
    validation to silently fall back to structural checks only.
    """
    owned_conn = None
    if conn is None:
        from legal_ai.knowledge.static.db import get_connection

        try:
            owned_conn = get_connection()
            conn = owned_conn
        except Exception:
            # No database reachable: structural validation still runs.
            conn = None

    try:
        return _research_angle(angle, context, max_rounds, max_steps, limit, conn)
    finally:
        if owned_conn is not None:
            owned_conn.close()


def _research_angle(
    angle: str,
    context: str,
    max_rounds: int,
    max_steps: int,
    limit: int,
    conn: psycopg.Connection | None,
) -> ResearchResult:
    collected: list[Evidence] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    gap = ""
    rounds = 0

    for _ in range(max_rounds):
        rounds += 1
        plan = build_plan(f"{angle} {gap}".strip(), context=context, max_steps=max_steps)
        if not plan:
            break

        result = validate(execute_plan(plan), conn=conn)
        dropped.extend(result.dropped)
        for item in result.kept:
            if item.document_id not in seen:
                seen.add(item.document_id)
                collected.append(item)

        missing = assess(angle, collected)
        if missing is None:
            break
        gap = missing

    ranked = rank_by_relevance(angle, collected, limit=limit)
    return ResearchResult(
        angle=angle,
        summary=compress(angle, ranked),
        evidence=ranked,
        rounds=rounds,
        dropped=dropped,
    )
