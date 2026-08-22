"""Rewrite a question into the vocabulary a statute would use.

The single largest measured gain in the project. On the 50-question
benchmark, rewriting before searching moves MRR from 0.467 to 0.670 and
recall@5 from 64% to 86% -- more than the entire reranking mechanism
contributes.

It closes a gap retrieval cannot close on its own. A user writes "builder
did not give possession"; the statute says "promoter fails to give
possession". No amount of fusion or reranking bridges that, because neither
side of the comparison contains the other's words.

Measured and rejected: fusing the original query with the rewrite scored
0.584, worse than the rewrite alone. The rewrite is not a second opinion to
blend -- it is simply a better query.

Lives here rather than in retrieval because it is a model call, and
retrieval stays deterministic: hybrid_search must remain testable without an
API key, and callers that do not want to spend a call must not be forced to.
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

    Falls back to the original on any failure, so a degraded rewrite never
    leaves the caller with an empty or missing search.
    """
    try:
        rewritten = generate(PROMPT.format(question=question)).split("\n")[0].strip()
    except Exception:
        return question
    return rewritten or question
