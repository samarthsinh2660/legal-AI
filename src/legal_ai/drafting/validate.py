"""Check a drafted document before it becomes a file.

Deterministic, and deliberately so. A second model call could review a
draft, but every defect worth catching here is mechanical: a citation that
was never retrieved, a document reciting itself as already sent, a
paragraph carrying an authority and no text. A regex catches those every
time; a reviewer catches them most of the time, a second slower, for the
price of a call. CLAUDE.md section 4.

The judgment a model *is* needed for -- whether this is even the right
instrument for the matter -- the drafter reports in `warnings`.

Failures are returned, never raised. The caller decides whether to refuse
the draft or repair it, and either way the reason has to survive.
"""

from __future__ import annotations

import re

from legal_ai.drafting.models import DraftStructure

# A document reciting the step it is itself taking: a notice that says a
# notice was sent, an application that says an application was made. The
# document then cites itself.
_ALREADY_TAKEN = re.compile(
    r"\b(demand |statutory |legal )?(notice|application|complaint)\b[^.]{0,80}\b"
    r"(was|were|had been|has been)\s+(sent|issued|served|dispatched|filed|made)\b",
    re.IGNORECASE,
)


def validate(draft: DraftStructure, retrieved: set[str]) -> list[str]:
    """Every rule this draft breaks, in the order they are worth reading.

    `retrieved` is the set of document ids actually put in front of the
    drafter. A paragraph citing anything else is a fabricated citation,
    which is the worst failure this feature has.
    """
    failures: list[str] = []
    paragraphs = [p for block in draft.sections for p in block.paragraphs]

    for paragraph in paragraphs:
        for authority in paragraph.authorities:
            if authority not in retrieved:
                failures.append(
                    f"cites {authority!r}, which was not retrieved for this draft"
                )
        if paragraph.authorities and not paragraph.text.strip():
            failures.append("carries a citation with no text under it")

    for paragraph in paragraphs:
        if _ALREADY_TAKEN.search(paragraph.text):
            failures.append(
                "recites the step this document is itself taking as already "
                f"taken: {paragraph.text[:70]!r}"
            )
            break

    if not draft.title.strip():
        failures.append("has no title, so nothing says what it is")
    if not paragraphs:
        failures.append("has no paragraphs in it")
    elif not any(p.authorities for p in paragraphs):
        failures.append("rests on no law the conversation established")

    return failures
