"""What a question reaches for that the corpus does not hold.

Two gaps. A **repealed code** whose replacement we hold, and a subject
worked out in **state-made rules**, of which we hold none at all.

The repealed register is empty. All three criminal codes repealed in 2023 -- the
IPC, the CrPC and the Indian Evidence Act -- were ingested on 2026-09-02
(scripts/ingest_repealed_codes.py), and they were the only entries. There
is nothing left to warn about, so every question now gets no note.

The mechanism stays because the entry criterion below is narrow and
mechanical, and the corpus is a fraction of Indian law: the next
repealed-code-with-a-held-replacement gets one tuple here rather than a
rebuild of a path that reaches the reader through DraftAnswer, the API
payload and the answer view.

Deterministic: whether we hold an Act is a fact about our shelf, not an
ambiguity. No model call, so the note costs nothing.
"""

from __future__ import annotations

import re

# (pattern, repealed code, what we hold instead). Only codes that are BOTH
# absent and have a held replacement belong here -- a note naming a
# replacement we do not hold either would send the reader nowhere, and a
# note about a code we now hold would send them away from it.
_REPEALED: tuple[tuple[re.Pattern[str], str, str], ...] = ()


# Subjects worked out in state-made rules rather than the central Act. The
# corpus holds central legislation only -- no state Act, no state rule -- so
# on these the parent Act gives the framework and never the number the
# reader wants. Same list as `context.clarification`, which asks *which*
# state; this says we would not hold it either way.
_STATE_MADE = re.compile(
    r"\b(rera|real estate|builder|promoter|flat|apartment|possession|"
    r"rent|landlord|tenant|eviction|lease deed|"
    r"stamp duty|registration fee|land revenue|mutation|"
    r"shops? and establishment|profession tax)\b",
    re.IGNORECASE,
)

_STATE_NOTE = (
    "This corpus holds central legislation only. The rules under this law "
    "are made by each state, and none of them are in it, so what follows is "
    "the central Act's framework rather than the rate, period or fee your "
    "state prescribes. Check the state rules before relying on a number."
)


def coverage_note(question: str | None) -> str | None:
    """A sentence naming what we do not hold, or None.

    One note only. A repealed code is reported ahead of a state-rules gap:
    both are true of a question that names both, and the specific one is
    worth more of the reader's attention.
    """
    text = (question or "").strip()
    if not text:
        return None

    for pattern, repealed, replacement in _REPEALED:
        if pattern.search(text):
            return (
                f"This corpus does not hold {repealed}. It holds "
                f"{replacement}, which replaced it on 1 July 2024. An "
                f"offence committed before that date is still charged under "
                f"the older code, so check the section number against it "
                f"rather than relying on what follows."
            )

    if _STATE_MADE.search(text):
        return _STATE_NOTE
    return None
