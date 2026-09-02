"""Verification Agent -- does the cited text actually support the claim?

Stage 6 of the funnel in `verification/pipeline.py`, and the only stage that
reasons rather than looks up. It lives in `agents/` with the other roles
that call a model: bounded reasoning over material an orchestrator chose,
returning structure the caller can act on. The stages before it are lookups
http://gmail.com/and stay in `verification/`.

The only question in verification that needs a model. Everything before it
is a lookup or a string comparison, and a model would be worse at those, not
merely slower: asked whether a document exists, a model may guess, while a
database cannot.

This is the check for **misgrounding** -- a real case, correctly cited, for a
proposition it does not support. Stanford RegLab found rates of 17-33% on
tools built over curated proprietary corpora and called it more dangerous
than an invented case, because it survives every mechanical check: the id
resolves, the document is real, the retrieval log confirms we read it.

Two constraints hold this in place:

**It may only add rejections.** A stage that can approve is a stage that can
hallucinate an approval, which would put a hallucination-checker in the
business of laundering hallucinations. Anything the earlier stages rejected
stays rejected.

**It never sees INSUFFICIENT_EVIDENCE as an option.** Whether we retrieved
material capable of settling a claim is a fact about retrieval, not a
judgement. Offering it as a verdict would give the model an escape hatch on
exactly the hard claims this check exists for.

One batched call per answer, not one per claim.
"""

from __future__ import annotations

import json

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.schemas.verification import Claim, ClaimVerdict, Verdict

STAGE = "semantic"

# Characters of a cited document put in front of the model. A section runs
# well under this; a judgment does not, and the head of a judgment is its
# headnote and issue -- the part that states what it decided.
MAX_SOURCE_CHARS = 6000

_PROMPT = """You are a verification checker for Indian legal research. Your
job is NOT to answer the question or to say whether the claim is good law.
It is one narrower thing: does the text quoted below actually say this?

For each numbered claim, return ONE verdict:

SUPPORTED
    The cited text states this, or it follows directly and necessarily.
PARTIALLY_SUPPORTED
    The cited text is about this, but the claim overstates it, drops a
    condition the text imposes, widens who or what it covers, or adds
    something the text does not carry.
UNSUPPORTED
    The cited text does not address this proposition at all.

THE RULE THAT MATTERS MOST
Judge only against the text supplied. A claim that is perfectly correct
Indian law, but is not stated in this text, is UNSUPPORTED. Recalling the
law from memory defeats the entire purpose of this check -- the answer being
verified was itself written by a model, so agreeing with it from memory
verifies nothing.

WHEN YOU ARE UNSURE
Prefer the more cautious verdict. A claim wrongly flagged costs a reader a
second look. A claim wrongly approved is a false statement of law presented
as checked, which is the failure this system exists to prevent.

OTHER RULES
- A claim with several parts is SUPPORTED only if the text supports every
  part. If one part is supported and another is not, that is
  PARTIALLY_SUPPORTED.
- A claim citing several sections is SUPPORTED if the sections together
  support it. They need not each support all of it.
- If a cited text shows as "(text unavailable)", judge on what remains; if
  nothing remains, return UNSUPPORTED.
- Ignore amendment footnotes and bracketed editorial marks in the text.

WORKED EXAMPLES

Text: "He shall be liable on demand to return the amount received."
Claim: "He must return the amount on demand."            -> SUPPORTED
Claim: "He must return the amount automatically."        -> PARTIALLY_SUPPORTED
       (the text requires a demand; the claim removes it)
Claim: "He is liable to imprisonment for two years."     -> UNSUPPORTED
       (the text creates a money liability, not an offence)

Text: "A person may apply to the District Magistrate for a certificate."
Claim: "An application is made to the District Magistrate."  -> SUPPORTED
Claim: "The Magistrate must decide within thirty days."      -> UNSUPPORTED
       (no time limit appears in the text, however reasonable it sounds)

Return JSON only, one entry per claim, no prose around it:
{{"verdicts": [{{"n": 1, "verdict": "SUPPORTED", "why": "<short reason>"}}]}}

CLAIMS AND THEIR CITED TEXT
{body}
"""



def _render(claims: list[Claim], sources: dict[str, str]) -> str:
    blocks = []
    for index, claim in enumerate(claims, start=1):
        cited = "\n".join(
            f"  [{doc_id}] {sources.get(doc_id, '(text unavailable)')[:MAX_SOURCE_CHARS]}"
            for doc_id in claim.evidence_ids
        )
        blocks.append(f"{index}. CLAIM: {claim.text}\n   CITED TEXT:\n{cited}")
    return "\n\n".join(blocks)


def check_support(
    claims: list[Claim],
    sources: dict[str, str],
    chain: tuple[str, ...] = DEFAULT_CONFIG.model_chain,
) -> tuple[list[ClaimVerdict], int]:
    """Verdicts for `claims`, and the number of model calls made.

    Returns UNSUPPORTED for anything the model does not rule on. A claim the
    checker could not reach a verdict about must not read as one it
    approved.
    """
    if not claims:
        return [], 0

    raw = generate(
        _PROMPT.format(body=_render(claims, sources)),
        chain=chain,
        max_output_tokens=DEFAULT_CONFIG.extraction_model_max_tokens,
    )

    by_index: dict[int, tuple[Verdict, str]] = {}
    try:
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        for item in payload.get("verdicts", []):
            try:
                verdict = Verdict(str(item.get("verdict", "")).strip().upper())
            except ValueError:
                # An unrecognised label is not a licence to approve.
                continue
            if verdict is Verdict.INSUFFICIENT_EVIDENCE:
                # Not this stage's to give: see the module docstring.
                continue
            by_index[int(item["n"])] = (verdict, str(item.get("why", ""))[:200])
    except (ValueError, KeyError, TypeError):
        # A malformed reply fails closed. Every claim is reported
        # unsupported, which is visible and recoverable; silently treating
        # them as checked would not be.
        return [
            ClaimVerdict(claim, Verdict.UNSUPPORTED, "verifier reply was unreadable", STAGE)
            for claim in claims
        ], 1

    verdicts = []
    for index, claim in enumerate(claims, start=1):
        verdict, why = by_index.get(
            index, (Verdict.UNSUPPORTED, "verifier returned no verdict for this claim")
        )
        verdicts.append(ClaimVerdict(claim, verdict, why, STAGE))
    return verdicts, 1
