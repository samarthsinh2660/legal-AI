"""The clarification gate -- ask only when a missing fact makes research wrong.

Most questions need no clarification, and asking anyway trains users to
ignore the prompt. The gate therefore fires on an **enumerated** list of
blocking gaps, never on general uncertainty.

A gap is blocking when proceeding without it does not merely degrade the
answer but invalidates the whole run:

    state       several statutes are state-wise. RERA rules, rent control
                and stamp duty differ by state, so researching "which RERA
                provision applies" without a state researches the wrong
                rules entirely.

    date        where the question turns on a limitation period, the answer
                depends on when the cause of action arose.

Deliberately deterministic -- no model call. Whether a topic is state-wise
is a fact about Indian law, not an ambiguity, so a rule states it and a test
pins it. That also means the gate costs nothing and works with no API key.
"""

from __future__ import annotations

import re

from legal_ai.context.models import ThreadContext

# Subjects governed by state-made rules. Matching one of these without a
# known state is the single most common way a run is wasted.
_STATE_DEPENDENT = re.compile(
    r"\b(rera|real estate|builder|promoter|flat|apartment|possession|"
    r"rent|landlord|tenant|eviction|lease deed|"
    r"stamp duty|registration fee|land revenue|mutation|"
    r"shops? and establishment|profession tax)\b",
    re.IGNORECASE,
)

# Questions that turn on how long ago something happened.
_DATE_DEPENDENT = re.compile(
    r"\b(limitation|time.?barred|how long do i have|within what time|"
    r"delay in filing|condonation)\b",
    re.IGNORECASE,
)

STATE_QUESTION = (
    "Which state is this in? Rules under this law are made by each state, "
    "so the answer differs depending on where the matter arose."
)

DATE_QUESTION = (
    "When did this happen? The time limit that applies depends on when the "
    "cause of action arose."
)


def clarification_needed(context: ThreadContext) -> str | None:
    """The one blocking question to ask, or None to proceed.

    Returns at most one question. Asking two at once is how a gate becomes
    a form, and a form is what users abandon.
    """
    text = context.question

    if _STATE_DEPENDENT.search(text) and not context.jurisdiction.state:
        return STATE_QUESTION

    if _DATE_DEPENDENT.search(text) and not context.relevant_date_from:
        return DATE_QUESTION

    return None
