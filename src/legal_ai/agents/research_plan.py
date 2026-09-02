"""One call turns a question into angles and their statutory queries.

Replaces four separate calls -- decompose, rewrite, plan, and a per-angle
planner -- that all produced the same kind of thing: a query. A question at
three angles used to cost 13 model calls; it now costs one here plus one to
summarise.

The queries must be in the vocabulary a statute uses, not the user's. That
single property is the largest measured gain in the project: MRR 0.467 to
0.670 on the 50-question benchmark, more than the whole reranking mechanism
contributes. A user writes "builder did not give possession"; the statute
says "promoter fails to give possession", and retrieval cannot bridge that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate

PROMPT = """You are planning a search of an Indian legal corpus of statutes
and judgments.

{context}

Question: {question}

FIRST decide whether this is a legal question at all. A greeting, a thank
you, a question about what this tool does, or anything else with no legal
issue in it is NOT a legal question. For those, return an empty array []
and nothing else. Do not invent a legal angle for a message that has none.

Otherwise, break the question into the distinct legal angles it raises --
different remedies, forums, or statutes. **Prefer ONE angle.** Most
questions have one. Use more only where the question raises separate legal
problems researched in different statutes. At most {max_angles}.

For each angle give a search query in the vocabulary an Indian STATUTE
would use, not the words a member of the public would use. The corpus holds
the statutes themselves, so a query phrased as a grievance will not match.
"builder did not hand over my flat" must be phrased as "promoter fails to
give possession return of amount".

Return ONLY a JSON array of {{"angle": "...", "query": "..."}}."""


@dataclass(frozen=True)
class Angle:
    angle: str
    query: str


def plan_research(
    question: str,
    context: str = "",
    max_angles: int = 3,
    chain: tuple[str, ...] | None = None,
) -> list[Angle]:
    """Angles and their statutory queries, in one call.

    Falls back to a single angle using the question verbatim, so a model
    failure degrades to plain retrieval rather than stopping the run.
    """
    fallback = [Angle(angle=question, query=question)]
    try:
        raw = generate(
            PROMPT.format(
                question=question,
                context=context or "No additional context.",
                max_angles=max_angles,
            ),
            # `chain` pins one model for a benchmark run. Without it a run
            # can slide down the chain partway through, so early questions
            # are answered by a different model than later ones and the
            # score blends them -- which is not one measurement.
            **({"chain": chain} if chain else {}),
            max_output_tokens=DEFAULT_CONFIG.plan_model_max_tokens,
        )
    except Exception:
        return fallback

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except ValueError:
        return fallback
    if not isinstance(parsed, list):
        return fallback

    # An array the model deliberately left empty says "no legal issue here".
    # Checked before the items are read, so it stays distinct from a reply
    # whose items were malformed -- that is a garbled answer, and dropping a
    # real question on it would be far worse than one wasted search.
    if not parsed:
        return []

    angles = [
        Angle(angle=str(item["angle"]).strip(), query=str(item["query"]).strip())
        for item in parsed
        if isinstance(item, dict) and item.get("angle") and item.get("query")
    ]
    return angles[:max_angles] or fallback
