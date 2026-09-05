"""Check a drafted structure before it becomes a file.

Deterministic, and deliberately so. A second model call could review a
draft, but every defect worth catching here is mechanical: a citation that
was never retrieved, an amount written as a figure, a notice that recites
itself as already sent. A regex catches those every time; a reviewer
catches them most of the time, a second slower, for the price of a call.
CLAUDE.md section 4.

The judgment a model *is* needed for -- whether this is even the right
instrument for the matter -- the drafter already reports in `warnings`.

Failures are returned, never raised. The caller decides whether to repair
the draft or refuse it, and a refusal must say which rule failed.
"""

from __future__ import annotations

import re

from legal_ai.drafting.models import DraftStructure

# The token the drafter must write where the amount belongs. Filled from
# the record because the demand must equal the cheque exactly; a rupee's
# difference invalidates the notice (Kaveri Plastics v Mahdoom Bawa, 2025).
AMOUNT_TOKEN = "{{amount}}"

# A currency mark, written with a word boundary so "two years," does not
# read as "Rs" followed by a comma -- which it did, because the figure was
# once `[\d,]+` and a lone comma satisfied it. A money figure must start
# with a digit.
_CURRENCY = r"(?:\bRs\.?|\bINR\b|₹)"
_FIGURE = r"\d[\d,]*(?:\.\d+)?"

# A currency mark or figure next to the token: the drafter starting to
# write the amount the template is going to supply.
_CURRENCY_BESIDE_TOKEN = re.compile(
    rf"(?:{_CURRENCY}|{_FIGURE})\s*" + re.escape(AMOUNT_TOKEN)
    + r"|" + re.escape(AMOUNT_TOKEN) + rf"\s*(?:{_CURRENCY}|{_FIGURE})",
    re.IGNORECASE,
)

# A figure written as money anywhere in the prose.
_BARE_AMOUNT = re.compile(rf"{_CURRENCY}\s*{_FIGURE}", re.IGNORECASE)

# The notice reciting a demand notice as already sent. The document is
# itself the demand, so this makes it cite itself.
_ALREADY_SENT = re.compile(
    r"\b(demand |statutory |legal )?notice\b[^.]{0,80}\b"
    r"(was |were |had been |has been )?(sent|issued|served|dispatched)\b",
    re.IGNORECASE,
)


def validate(
    draft: DraftStructure,
    retrieved: set[str],
    *,
    needs_demand: bool = True,
    needs_facts: bool = True,
) -> list[str]:
    """Every rule this draft breaks, in the order they are worth reading.

    `retrieved` is the set of document ids actually put in front of the
    drafter. A ground citing anything else is a fabricated citation.

    `needs_demand` is false for a document that does not make one, and
    `needs_facts` for one that need not rest on any. An opinion ends in a
    conclusion rather than a demand, and an opinion on a question of pure
    law has no facts -- its prompt tells it to return none rather than
    invent a client's circumstances, so requiring them here refused a draft
    for doing exactly as it was told.
    """
    failures: list[str] = []

    for ground in draft.grounds:
        if ground.authority not in retrieved:
            failures.append(
                f"cites {ground.authority!r}, which was not retrieved for this draft"
            )
        if not ground.text.strip():
            failures.append(f"ground on {ground.authority} carries no text")

    body = _body(draft)

    if _CURRENCY_BESIDE_TOKEN.search(body):
        failures.append(
            f"writes a currency mark or figure beside {AMOUNT_TOKEN}; the "
            "template supplies those"
        )
    if _BARE_AMOUNT.search(body):
        failures.append(
            "states an amount as a figure; it must be the "
            f"{AMOUNT_TOKEN} token, filled from the record"
        )

    for fact in draft.facts:
        if _ALREADY_SENT.search(fact):
            failures.append(
                "recites a notice as already sent, but this document is "
                f"itself the demand: {fact[:70]!r}"
            )

    if needs_facts and not draft.facts:
        failures.append("states no facts")
    if not draft.grounds:
        failures.append("rests on no provision")
    if needs_demand and (draft.demand is None or not draft.demand.what.strip()):
        failures.append("demands nothing")

    # An address we do not hold must be asked for, not left blank for
    # someone to miss on the way to the post office. Only where the document
    # is served on somebody: an opinion goes to the client who asked for it.
    if needs_demand:
        for party, role in ((draft.recipient, "recipient"), (draft.sender, "sender")):
            if not _real(party.address) and not draft.needs_input:
                failures.append(f"has no {role} address and does not ask for one")

    return failures


def _body(draft: DraftStructure) -> str:
    """Every piece of prose the drafter wrote, as one string."""
    parts = [
        draft.subject,
        *draft.facts,
        *(ground.text for ground in draft.grounds),
        draft.consequence,
        *draft.annexures,
    ]
    if draft.demand is not None:
        parts.append(draft.demand.what)
    return "\n".join(parts)


def _real(address: str) -> bool:
    """Whether an address is an address rather than a placeholder for one."""
    text = (address or "").strip()
    if not text:
        return False
    return not (text.startswith(("[", "{{")) or text.lower().startswith("address"))
