"""Analyst Agent -- turn retrieved law into statements that can be checked.

Research returns a pile of provisions. That is not an answer, and more
importantly it is not a *checkable* answer: the summary it used to produce
ended "Sources: a, b, c", and nothing said which sentence rested on which
source. Every statement was therefore unverifiable, and the groundedness
check built in Phase 3 has never run on anything.

This produces claims instead:

    Claim("a promoter who misses the possession date must refund with
           interest", ("act:2158:sec-18",))

Each carries its own ids, so verification is a lookup against what was
actually retrieved rather than a model re-reading another model's paragraph
and judging it. That is what keeps the check from being able to hallucinate.

Cost is unchanged in the common case: this replaces `supervisor.summarise`
rather than adding to it. One model call per question.

The ids a claim carries are **validated here against what was retrieved**.
A model asked to cite will sometimes produce a plausible id that was never
in front of it, and an invented citation in a legal answer is the worst
failure this system has. Unknown ids are dropped, which turns a fabricated
citation into a visibly unsupported claim -- exactly what the verifier is
for.
"""

from __future__ import annotations

import json

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.context.models import DocumentFacts
from legal_ai.llm.client import generate
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.evidence import Evidence
from legal_ai.schemas.verification import Claim

# Provisions put in front of the model. Beyond this the tail is the least
# relevant retrieval, and a longer prompt buys noise.
MAX_EVIDENCE_SHOWN = 12

# Characters of each provision shown. Enough to state what it provides
# without pasting an entire Act into the prompt.
PASSAGE_CHARS = 700

PROMPT = """You are an Indian legal analyst. Below are provisions and
authorities retrieved for a question, each with an identifier in [brackets].

QUESTION
{question}

{case}

RETRIEVED LAW
{evidence}

Write the analysis as separate factual statements. Each statement must be
one thing the law says, and must cite the identifiers it rests on --
copied exactly from the brackets above.

Rules:
- Use ONLY the material above. Do not add law from memory.
- Every claim needs at least one identifier from the list above.
- If the material does not answer the question, say so in "lede" and
  return few or no claims. That is a correct answer, not a failure.
- Do not invent an identifier. If nothing above supports a statement, do
  not make the statement.

Return ONLY JSON:
{{"lede": "one or two sentences answering the question directly",
  "claims": [{{"text": "...", "evidence_ids": ["..."]}}]}}"""


def _render_evidence(evidence: list[Evidence]) -> str:
    return "\n\n".join(
        f"[{item.document_id}] {item.title or ''}\n{item.content[:PASSAGE_CHARS]}"
        for item in evidence[:MAX_EVIDENCE_SHOWN]
        if item.document_id
    )


def _render_case(documents: tuple[DocumentFacts, ...]) -> str:
    if not documents:
        return ""
    lines = ["THE CLIENT'S OWN DOCUMENTS SAY"]
    for facts in documents:
        for label, values in (
            ("parties", facts.parties),
            ("dates", facts.dates),
            ("terms", facts.clauses),
            ("asserts", facts.claims),
            ("raises", facts.issues),
        ):
            if values:
                lines.append(f"  {label}: " + "; ".join(values[:6]))
    return "\n".join(lines) + "\n"


def _parse(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except (ValueError, IndexError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def analyse(
    question: str,
    evidence: list[Evidence],
    documents: tuple[DocumentFacts, ...] = (),
) -> AnalysisResult:
    """Claims for `question`, each grounded in retrieved Evidence.

    Returns an empty result rather than raising when the model is
    unreachable or its reply is unusable. An empty analysis produces an
    answer that says nothing, which a reader can see; a fabricated one
    would not be visible at all.
    """
    if not evidence:
        return AnalysisResult(lede="No supporting provisions were retrieved.")

    available = {item.document_id for item in evidence if item.document_id}

    try:
        parsed = _parse(
            generate(
                PROMPT.format(
                    question=question,
                    case=_render_case(documents),
                    evidence=_render_evidence(evidence),
                ),
                max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
            )
        )
    except Exception:
        return AnalysisResult(
            lede=f"Retrieved {len(evidence)} provisions; analysis was unavailable."
        )

    claims: list[Claim] = []
    dropped: list[str] = []
    for item in parsed.get("claims") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        # Only ids that were actually in front of the model survive. A
        # plausible-looking invention becomes an unsupported claim the
        # verifier will surface, rather than a citation a reader trusts.
        cited = [str(i).strip() for i in (item.get("evidence_ids") or []) if str(i).strip()]
        ids = tuple(i for i in cited if i in available)
        dropped.extend(i for i in cited if i not in available)
        claims.append(Claim(text=text, evidence_ids=ids))

    lede = str(parsed.get("lede") or "").strip()
    return AnalysisResult(
        claims=tuple(claims), lede=lede, dropped_ids=tuple(dict.fromkeys(dropped))
    )
