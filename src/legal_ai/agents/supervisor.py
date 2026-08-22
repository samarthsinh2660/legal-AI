"""The supervisor: decompose a question into angles, fan out, decide when done.

It makes exactly two judgements. How many angles, and go again or stop.
Everything else in the pipeline is fixed, which is what makes the pipeline
measurable.

**There is no split-versus-single mode.** The supervisor emits a list of
angles; a list of one *is* the single-agent case, and per the prompt below
that is the expected common case. A lookup question must not spawn three
agents.

Caps are enforced here in code, never in the prompt. A prompt is a request;
a cap is a guarantee.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import psycopg

from legal_ai.agents.research import ResearchResult, research_angle
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.schemas.evidence import Evidence

DECOMPOSE_PROMPT = """You are planning research on an Indian legal question.

Question: {question}

Break this into the distinct legal angles it raises -- different remedies,
different forums, different statutes, or a limitation question. Two angles
must not be rephrasings of each other.

**Prefer a single angle.** Most questions have one. Use more only when the
question genuinely raises separate legal problems that would be researched
in different statutes. "What is the punishment for murder" is one angle.
"My builder is late, what are my options" is several: the statutory refund
remedy, and which forum hears it.

At most {max_angles} angles. Return ONLY a JSON array of short strings."""


@dataclass(frozen=True)
class SupervisorResult:
    question: str
    angles: list[str] = field(default_factory=list)
    findings: list[ResearchResult] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def agents_spawned(self) -> int:
        """Tracked as a cost metric: a lookup question staying at 1 is the
        signal that decomposition is not over-firing."""
        return len(self.findings)


def decompose(question: str, max_angles: int) -> list[str]:
    """Angles to research. Always returns at least the question itself.

    A model failure degrades to single-angle research rather than stopping
    the run -- one angle is a valid plan, not an error.
    """
    try:
        raw = generate(DECOMPOSE_PROMPT.format(question=question, max_angles=max_angles))
    except Exception:
        return [question]

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except ValueError:
        return [question]

    if not isinstance(parsed, list):
        return [question]
    angles = [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
    return angles[:max_angles] or [question]


def supervise(
    question: str,
    context: str = "",
    max_angles: int = DEFAULT_CONFIG.max_concurrent_research_units,
    max_rounds: int = DEFAULT_CONFIG.max_agent_rounds,
    max_steps: int = DEFAULT_CONFIG.max_plan_steps,
    limit_per_angle: int = DEFAULT_CONFIG.limit_per_angle,
    conn: psycopg.Connection | None = None,
) -> SupervisorResult:
    """Decompose, research each angle in parallel, merge the evidence.

    Angles run concurrently because they are independent; the cap on
    `max_angles` bounds both the parallelism and the API spend.

    Merging is by first appearance across angles rather than by re-ranking
    the union. Each angle's list is already ranked against *its own* angle,
    and a single re-rank against the original question would discard that --
    the evidence for a limitation angle scores poorly against a question
    about refunds even when it is exactly what was asked for.
    """
    angles = decompose(question, max_angles=max_angles)

    def run(angle: str) -> ResearchResult:
        return research_angle(
            angle,
            context=context,
            max_rounds=max_rounds,
            max_steps=max_steps,
            limit=limit_per_angle,
            # Only share the caller's connection when nothing runs in
            # parallel; otherwise each angle opens its own.
            conn=conn if len(angles) == 1 else None,
        )

    if len(angles) == 1:
        findings = [run(angles[0])]
    else:
        # A psycopg connection is not thread-safe, so each angle opens its
        # own (see research_angle); the caller's is not shared across threads.
        with ThreadPoolExecutor(max_workers=len(angles)) as pool:
            findings = list(pool.map(run, angles))

    merged: list[Evidence] = []
    seen: set[str] = set()
    for position in range(max(len(f.evidence) for f in findings) if findings else 0):
        for finding in findings:
            if position >= len(finding.evidence):
                continue
            item = finding.evidence[position]
            if item.document_id in seen:
                continue
            seen.add(item.document_id)
            merged.append(item)

    return SupervisorResult(
        question=question, angles=angles, findings=findings, evidence=merged
    )
