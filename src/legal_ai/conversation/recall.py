"""Answer a follow-up out of the claims the thread already established.

Until 2026-09 the ANSWER route returned the previous assistant turn word for
word. That is defensible for "which of those binds me", and indefensible for
anything else: asked "what is my client's name, which flat, and how much has
she paid" in an answered thread, the reader got the previous answer's lede
and the previous answer's claims, with nothing on screen saying it was a
repeat. A correct route produced a broken product.

**The model never writes an identifier and never writes a claim.** It is
given the stored claims, numbered, and returns numbers plus a lede. Every
claim text, every evidence id and every bucket in the composed answer is
copied from storage. The analyst validates model-written ids against what
was retrieved (`agents/analyst.py`); here the same failure is made
unrepresentable instead, because the material is already structured and
there is no reason to let a model retype it.

**A carried claim keeps its bucket.** Re-emitting an `unchecked` claim as a
`key_element` would turn "nobody looked" into "we looked and it holds" on
the strength of a second model call that looked at no evidence at all. Where
the same text was stored twice in different buckets, the least reassuring
one wins.

**Deterministic before model** (CLAUDE.md §4): a thread holding no stored
claims cannot be composed from, and a model call cannot discover that. It is
a dict lookup, so it happens first and the call is never made.

Returning None is a real outcome, not a failure to hide. The caller says so
plainly; falling back to the replay is what this module exists to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.schemas.answer import DraftAnswer
from legal_ai.schemas.verification import Claim

# Stored answers read back for one composition. Matches the history the
# router and rewriter see: past this the referent is not in the thread the
# user is looking at.
RECENT_ANSWERS = 8

# Claims put in front of the model. Beyond this the prompt is a transcript,
# and the "lost in the middle" effect that bounds the rewriter applies here
# for the same reason.
MAX_CLAIMS_SHOWN = 40

# A lede longer than this is not a lede -- it is the model writing its own
# answer over material it was told only to summarise.
MAX_LEDE_CHARS = 600

# The order the reader sees, and therefore the order the numbering follows:
# `agents/draft.render` prints the four slots in exactly this sequence.
_ORDER = ("key_elements", "partially_supported", "needs_verification", "unchecked")

# Least reassuring first. A text stored in two buckets keeps the earliest
# match here, so a claim can only ever move down this list, never up.
_REASSURANCE = ("needs_verification", "unchecked", "partially_supported",
                "key_elements")

_PROMPT = """Below are statements this conversation has already established,
each numbered. Answer the user's question using ONLY these statements.

STATEMENTS
{claims}

QUESTION
{question}

Rules:
- Cite statements by number. Do not rewrite them and do not add new ones.
- Use nothing outside the list, not even law you know.
- If the statements do not answer the question, return an empty list. That
  is a correct outcome, not a failure.

Return ONLY JSON:
{{"claims": [1, 2], "lede": "one or two sentences answering the question"}}"""


@dataclass(frozen=True)
class _Stored:
    """One claim as the thread stored it, with the bucket it was in."""

    text: str
    bucket: str
    evidence_ids: tuple[str, ...] = ()
    applicable_law: tuple[str, ...] = ()
    key_judgments: tuple[str, ...] = ()
    support_not_checked: bool = False


def _collect(answers: list[dict[str, Any]]) -> list[_Stored]:
    """Every claim in `answers`, deduplicated, weakest bucket winning."""
    seen: dict[str, _Stored] = {}
    for answer in answers[-RECENT_ANSWERS:]:
        if not isinstance(answer, dict):
            continue
        law = tuple(answer.get("applicable_law") or ())
        judgments = tuple(answer.get("key_judgments") or ())
        quick = bool(answer.get("support_not_checked"))
        for bucket in _ORDER:
            for item in answer.get(bucket) or ():
                if isinstance(item, dict):
                    text = str(item.get("text") or "").strip()
                    ids = tuple(
                        str(i).strip()
                        for i in (item.get("evidence_ids") or ())
                        if str(i).strip()
                    )
                else:
                    text, ids = str(item).strip(), ()
                if not text:
                    continue
                stored = _Stored(text, bucket, ids, law, judgments, quick)
                previous = seen.get(text)
                if previous is None or _REASSURANCE.index(
                    bucket
                ) < _REASSURANCE.index(previous.bucket):
                    seen[text] = stored
    return list(seen.values())[:MAX_CLAIMS_SHOWN]


def _parse(raw: str) -> dict:
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, IndexError):
        return {}


def _selected(parsed: dict, claims: list[_Stored]) -> list[_Stored]:
    """The claims the model chose, by number. Anything else is dropped."""
    chosen: list[_Stored] = []
    for number in parsed.get("claims") or ():
        if isinstance(number, bool) or not isinstance(number, int):
            continue
        if 1 <= number <= len(claims):
            stored = claims[number - 1]
            if stored not in chosen:
                chosen.append(stored)
    return chosen


def answer_from_thread(
    question: str,
    answers: list[dict[str, Any]],
    chain: tuple[str, ...] = DEFAULT_CONFIG.model_chain,
) -> DraftAnswer | None:
    """A new answer to `question` over the claims `answers` already hold.

    None when the thread holds no claims, when none of them answer the
    question, or when the model is unreachable or unreadable. The caller
    must say so rather than substituting an earlier reply.
    """
    claims = _collect(answers)
    if not claims:
        return None

    rendered = "\n".join(
        f"{n}. {stored.text}" for n, stored in enumerate(claims, start=1)
    )
    try:
        parsed = _parse(
            generate(
                _PROMPT.format(claims=rendered, question=question),
                chain=chain,
                max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
            )
        )
    except Exception:
        return None

    chosen = _selected(parsed, claims)
    if not chosen:
        return None

    lede = str(parsed.get("lede") or "").strip()[:MAX_LEDE_CHARS]
    by_bucket = {bucket: [] for bucket in _ORDER}
    for stored in chosen:
        by_bucket[stored.bucket].append(stored)

    key_elements = tuple(
        Claim(text=stored.text, evidence_ids=stored.evidence_ids)
        for stored in by_bucket["key_elements"]
    )
    cited = {i for stored in chosen for i in stored.evidence_ids}

    # The ids keep the classification the answer that retrieved them made.
    # Re-deriving statute from judgment here, with no Evidence in hand,
    # would be a guess at the shape of an identifier.
    law = {i for stored in chosen for i in stored.applicable_law} & cited
    judgments = {i for stored in chosen for i in stored.key_judgments} & cited

    return DraftAnswer(
        question=question,
        lede=lede,
        key_elements=key_elements,
        applicable_law=tuple(sorted(law)),
        key_judgments=tuple(sorted(judgments)),
        needs_verification=tuple(s.text for s in by_bucket["needs_verification"]),
        unchecked=tuple(s.text for s in by_bucket["unchecked"]),
        partially_supported=tuple(s.text for s in by_bucket["partially_supported"]),
        support_not_checked=any(s.support_not_checked for s in chosen),
        citations=tuple(sorted(cited)),
    )
