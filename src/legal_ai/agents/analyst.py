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
from legal_ai.retrieval.evidence_builder import EXTRACT_CHARS
from legal_ai.schemas.verification import Claim

# Provisions put in front of the model. Beyond this the tail is the least
# relevant retrieval, and a longer prompt buys noise.
MAX_EVIDENCE_SHOWN = 12

# Characters of each provision shown. Enough to state what it provides
# without pasting an entire Act into the prompt.
_UNAVAILABLE = "Retrieved {n} provisions; analysis was unavailable."

# Evidence arrives already budgeted by `retrieval.evidence_builder` -- a
# section whole, anything longer as its nearest few passages. A smaller cap
# here would only undo that: it used to be 700, which showed the model the
# first passage of a multi-passage judgment extract and dropped the rest.
SECTION_CHARS = 4000

# Said when the planner found no legal issue to search for. Carries no
# legal disclaimer: there is no legal information here to disclaim.
OUT_OF_SCOPE = (
    "I only research Indian law -- statutes and judgments -- so I cannot "
    "help with that. Ask a legal question and I will search the corpus and "
    "show you what the answer rests on."
)

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
        f"[{item.document_id}] {item.title or ''}\n"
        f"{item.content[:max(SECTION_CHARS, EXTRACT_CHARS)]}"
        for item in evidence[:MAX_EVIDENCE_SHOWN]
        if item.document_id
    )


def _render_case(
    documents: tuple[DocumentFacts, ...], case_description: str | None = None
) -> str:
    if not documents and not case_description:
        return ""
    lines = []
    if case_description:
        # Reaches the planner via context.serialization.render; this is the
        # only other place it needs to reach, since this node writes the answer.
        lines.append(f"THE MATTER (as the user described it): {case_description[:600]}")
    if documents:
        lines.append("THE CLIENT'S OWN DOCUMENTS SAY")
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
    searched: bool = True,
    case_description: str | None = None,
) -> AnalysisResult:
    """Claims for `question`, each grounded in retrieved Evidence.

    Returns an empty result rather than raising when the model is
    unreachable or its reply is unusable. An empty analysis produces an
    answer that says nothing, which a reader can see; a fabricated one
    would not be visible at all.
    """
    if not evidence and not documents and not case_description:
        # Two different facts. `searched=False` means no angle was planned,
        # so nothing was looked for; reporting that as an empty corpus
        # would tell the reader we looked.
        if not searched:
            return AnalysisResult(lede=OUT_OF_SCOPE)
        return AnalysisResult(lede="No supporting provisions were retrieved.")
    # A document-content question ("what is the cheque number") has no
    # statutory angle, so the planner rightly returns none and evidence is
    # empty -- but the case's own material can still answer it. Only true
    # emptiness (no evidence, no case, no documents) is out of scope.

    available = {item.document_id for item in evidence if item.document_id}

    try:
        parsed = _parse(
            generate(
                PROMPT.format(
                    question=question,
                    case=_render_case(documents, case_description),
                    evidence=_render_evidence(evidence),
                ),
                max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
            )
        )
    except Exception:
        return AnalysisResult(lede=_UNAVAILABLE.format(n=len(evidence)))

    # An unreadable reply is the same outcome as an unreachable model, and
    # must not take a different route: `_parse` returns {} rather than
    # raising, which produced a blank answer indistinguishable from "the
    # corpus holds nothing".
    if not parsed:
        return AnalysisResult(lede=_UNAVAILABLE.format(n=len(evidence)))

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
