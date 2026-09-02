"""Whether a message is a legal question at all.

Runs before the router and before any model call. A greeting is a fact
about the string, not an ambiguity, so it is settled by a pattern rather
than by a model -- the same rule as `context.clarification`.

Without this gate the planner is asked to plan a corpus search for every
message and its output contract has no way to decline, so it invents an
angle: "thanks!" was answered with the law on gratuity.

Patterns match the WHOLE message. "hi, can I claim a refund?" is a legal
question that opens with a greeting, and swallowing it would be far worse
than letting a bare "hi" through to the graph.
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    GREETING = "GREETING"
    THANKS = "THANKS"
    CAPABILITY = "CAPABILITY"

    # Anything else, including everything ambiguous. The gate only fires on
    # what it positively recognises.
    LEGAL = "LEGAL"


_GREETING = re.compile(
    r"(hi|hello|hey|yo|namaste|good\s+(morning|afternoon|evening|day))"
    r"([\s,!.]+(there|again|team|sir|ma'?am))?"
    r"([\s,!.]*(are\s+you\s+there|you\s+there|how\s+are\s+you))?",
    re.IGNORECASE,
)

_THANKS = re.compile(
    r"(ok(ay)?|great|perfect|cool|nice)?[\s,!.]*"
    r"(thanks|thank\s+you|thx|ty|cheers)"
    r"[\s,!.]*(a\s+lot|so\s+much|very\s+much)?",
    re.IGNORECASE,
)

_CAPABILITY = re.compile(
    r"(help"
    r"|who\s+are\s+you"
    r"|what\s+(are|is)\s+(you|this)"
    r"|what\s+can\s+(you|this)\s+do"
    r"|what\s+do\s+you\s+do"
    r"|how\s+(do|does)\s+(you|this)\s+work"
    r"|how\s+do\s+i\s+use\s+(you|this))",
    re.IGNORECASE,
)

_REPLIES = {
    Intent.GREETING: (
        "Hello. Ask a legal question and I will search the statutes and "
        "judgments we hold, then show you what each part of the answer "
        "rests on."
    ),
    Intent.THANKS: "You're welcome. Ask another question whenever you need to.",
    Intent.CAPABILITY: (
        "I research Indian law over primary sources: Central statutes from "
        "India Code and Supreme Court judgments, searched for each question "
        "you ask.\n\n"
        "Every part of an answer is marked with what it rests on, and "
        "separately with whether that source was checked, only partly "
        "supports the claim, contradicts it, or could not be checked at "
        "all. Where the corpus does not hold the answer I will say so "
        "rather than guess -- state rules and High Court decisions are "
        "largely outside it.\n\n"
        "I am not a lawyer and this is not legal advice."
    ),
}

# Long messages are questions, whatever they open with. Well above a
# greeting and well below anything a lawyer would type.
_MAX_CHARS = 60


def classify(message: str | None) -> Intent:
    """What kind of message this is.

    LEGAL for anything not positively recognised, so an unrecognised
    message costs a research run rather than a wrong canned reply.
    """
    text = (message or "").strip()
    if not text or len(text) > _MAX_CHARS:
        return Intent.LEGAL

    stripped = text.strip(" \t\n?!.,")
    for intent, pattern in (
        (Intent.GREETING, _GREETING),
        (Intent.THANKS, _THANKS),
        (Intent.CAPABILITY, _CAPABILITY),
    ):
        if pattern.fullmatch(stripped):
            return intent
    return Intent.LEGAL


def reply_for(intent: Intent) -> str | None:
    """The fixed reply, or None for a message that must be researched."""
    return _REPLIES.get(intent)
