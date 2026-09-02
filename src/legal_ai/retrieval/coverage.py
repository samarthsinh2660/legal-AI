"""Codes a question names that the corpus does not hold.

The register is empty. All three criminal codes repealed in 2023 -- the
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
