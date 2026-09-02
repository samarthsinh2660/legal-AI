"""Codes a question names that the corpus does not hold.

Of the three criminal codes repealed in 2023 only the Indian Evidence Act
is still absent; the IPC and the CrPC were ingested on 2026-09-02
(scripts/ingest_ipc_crpc.py). An offence committed before 1 July 2024 is
still charged under the old code, so asking about Evidence Act s.65B is a
live question, not a stale one -- and answering it from the replacement
without saying so would be a claim about the law we cannot make.

Deterministic: whether we hold an Act is a fact about our shelf, not an
ambiguity. No model call, so the note costs nothing.
"""

from __future__ import annotations

import re

# (pattern, repealed code, what we hold instead). Only codes that are BOTH
# absent and have a held replacement belong here -- a note naming a
# replacement we do not hold either would send the reader nowhere, and a
# note about a code we now hold would send them away from it.
_REPEALED = (
    (
        re.compile(r"\b(indian evidence act|evidence act, 1872)\b", re.IGNORECASE),
        "the Indian Evidence Act, 1872",
        "the Bharatiya Sakshya Adhiniyam, 2023",
    ),
)


def coverage_note(question: str | None) -> str | None:
    """A sentence naming what we do not hold, or None.

    One note, for the first code matched. Two would bury the point.
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
    return None
