"""LLM query rewriting -- the cheapest AI intervention to measure.

A user writes "builder did not give possession"; the statute says "promoter
fails to give possession". Retrieval cannot bridge that on its own. One
model call per question rewrites the grievance into statutory vocabulary.

This is a probe, not the research agent. It measures whether a model helps
retrieval at all, before Phase 3 commits to a full plan-execute loop.
"""

from __future__ import annotations

from legal_ai.llm.client import generate

PROMPT = """You are helping search a corpus of Indian statutory sections.

Rewrite the user's question as a short search query using the vocabulary an
Indian statute would actually use. Prefer the terms a section heading or
operative clause would contain. Do not name a section number unless the user
did. Output ONLY the query, under 15 words.

Question: {question}"""


def rewrite_query(question: str) -> str:
    """Statutory-vocabulary rewrite of `question`.

    Falls back to the original question if the model returns nothing, so a
    degraded rewrite never leaves the caller with an empty search.
    """
    rewritten = generate(PROMPT.format(question=question)).split("\n")[0].strip()
    return rewritten or question
