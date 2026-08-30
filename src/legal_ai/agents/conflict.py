"""Conflict Agent -- have these courts actually split on the provision?

The candidate holdings come from `retrieval/conflict.py`, which picks the
strongest judgment from each of a few courts. This is the half that needs a
model: whether two courts disagree cannot be read off the citation graph,
because the graph records that a judgment cites a section, never what it
held about it.

Three outcomes, not two. CONSISTENT and NOT_CHECKED are different facts, and
collapsing them repeats the defect Phase 6 fixed for verification -- a check
that could not run must never render as a check that passed. The direction
matters both ways here: asserting a split that does not exist makes settled
law look open, while missing one leaves the reader no worse off than the
system was before this existed.

Deliberately narrow. It is not asked which side is right, only whether the
holdings can stand together. Which court binds this reader is a question
about jurisdiction and bench strength that the graph answers better than a
model can.

One call per check, over at most MAX_COURTS holdings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.retrieval.conflict import CourtHolding

# Characters of each judgment put in front of the model. Enough to carry a
# holding, short enough that four of them fit beside the prompt.
MAX_PASSAGE_CHARS = 3000


class ConflictStatus(str, Enum):
    CONFLICT = "CONFLICT"
    CONSISTENT = "CONSISTENT"

    # The check did not run or could not be read. Not a finding about the
    # law -- an absence of one.
    NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class ConflictFinding:
    status: ConflictStatus
    why: str = ""

    # The judgments the split is between, filtered to ones actually put in
    # front of the model.
    document_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_a_split(self) -> bool:
        return self.status is ConflictStatus.CONFLICT


_PROMPT = """You compare how different Indian courts have decided the same point of law.

You are NOT deciding which court is right, and NOT answering the underlying
legal question. Your only question is whether these holdings can stand
together.

Two courts reaching different OUTCOMES on different FACTS is not a conflict
-- courts apply the same rule to different cases every day. A conflict is a
disagreement about the RULE: the same question of law answered differently,
so that a litigant's result would turn on which court heard the matter.

A court distinguishing an earlier case, or applying a settled rule to new
facts, is not a conflict.

If you are unsure, answer CONSISTENT. A split reported where none exists
makes settled law look open, and a reader may reopen a question their own
High Court has closed.

HOLDINGS:
{body}

Reply with JSON only:
{{"status": "CONFLICT" or "CONSISTENT",
  "why": "one sentence naming the rule they differ on",
  "document_ids": ["ids of the judgments that disagree"]}}"""


def _render(holdings: list[CourtHolding]) -> str:
    return "\n\n".join(
        f"[{h.document_id}] {h.court}\n{h.passage[:MAX_PASSAGE_CHARS]}"
        for h in holdings
    )


def check_conflict(
    holdings: list[CourtHolding],
    chain: tuple[str, ...] = DEFAULT_CONFIG.case_model_chain,
) -> ConflictFinding:
    """Whether `holdings` disagree about the rule.

    NOT_CHECKED whenever the question could not be put or the answer could
    not be read -- fewer than two courts, an unreadable reply, or a status
    outside the enum. Never CONSISTENT by default.

    Uses `case_model_chain`: this is the same shape of task as contradiction
    detection over case documents, where Gemma measured recall 1.00 against
    gemini-flash's 0.20 (evals/run_contradictions.py, 2026-08-24).
    """
    courts = {h.court for h in holdings if h.court}
    if len(courts) < 2:
        return ConflictFinding(
            ConflictStatus.NOT_CHECKED, "fewer than two courts to compare"
        )

    raw = generate(
        _PROMPT.format(body=_render(holdings)),
        chain=chain,
        max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
    )

    try:
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        status = ConflictStatus(str(payload.get("status", "")).strip().upper())
    except (ValueError, KeyError, TypeError):
        return ConflictFinding(ConflictStatus.NOT_CHECKED, "conflict reply was unreadable")

    if status is ConflictStatus.NOT_CHECKED:
        # Not the model's to give: it was asked a question with two answers.
        return ConflictFinding(ConflictStatus.NOT_CHECKED, "conflict reply was unreadable")

    # A split must point at judgments the reader can open, so ids that were
    # never in front of the model are dropped rather than shown.
    offered = {h.document_id for h in holdings}
    named = tuple(
        str(i) for i in payload.get("document_ids", []) or () if str(i) in offered
    )
    return ConflictFinding(status, str(payload.get("why", ""))[:200], named)
