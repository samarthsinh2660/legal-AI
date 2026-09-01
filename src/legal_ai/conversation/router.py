"""Whether a message needs the corpus, or the answer already given.

"Which of those binds me?" is about the reply on screen. Running the
research fan-out for it spends thirty seconds and several model calls
re-finding what the user is looking at.

The asymmetry decides every fallback here. Answering from memory when the
user wanted fresh law is a *wrong answer*; researching something we could
have answered from memory is *slow*. So an unreadable reply, an unknown
label and an error all route to RESEARCH.

Some messages never reach the model. "Still good law" is precisely the
question a stale answer gets wrong, and no classifier should be able to
decide it is answerable from a reply given ten minutes ago.
"""

from __future__ import annotations

import json
import re
from enum import Enum

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.conversation.rewriter import RECENT_TURNS, TURN_CHARS, Turn
from legal_ai.llm.client import generate


class Route(str, Enum):
    # Run the research graph.
    RESEARCH = "RESEARCH"

    # Answer from the conversation so far.
    ANSWER = "ANSWER"


# Currency words. `ThreadContext.needs_current_law` already bypasses caches
# for these; the same instinct applies to answering from a stale turn.
# Each alternative carries its own boundary: a trailing \b after a stem
# like "overrul" can never match, because "overruled" continues the word.
_ALWAYS_RESEARCH = re.compile(
    r"\bstill good law\b|\boverrul\w*|\bcurrent position\b|\blatest\b"
    r"|\brecent\w*|\bas of\b|\bamend\w*|\brepeal\w*|\bup to date\b"
    r"|\bnowadays\b|\bsince then\b",
    re.IGNORECASE,
)

_PROMPT = """Decide whether the user's latest message needs a fresh search of
the legal corpus, or can be answered from the conversation so far.

ANSWER -- it is about the answer already given: which authority is stronger,
what a cited case said, a summary, a clarification of wording.

RESEARCH -- it needs law not yet retrieved: a new question, a different
provision, another court, anything about whether law has changed.

If you are unsure, answer RESEARCH. Answering from memory when the user
wanted fresh law gives them a wrong answer; researching unnecessarily only
makes them wait.

CONVERSATION:
{history}

LATEST USER MESSAGE: {question}

Reply with JSON only: {{"route": "ANSWER" or "RESEARCH"}}"""


def route_message(
    question: str,
    history: list[Turn],
    chain: tuple[str, ...] = DEFAULT_CONFIG.model_chain,
) -> Route:
    """Where `question` should go.

    RESEARCH with no model call for a first message, or for anything asking
    about currency.
    """
    if not history or _ALWAYS_RESEARCH.search(question or ""):
        return Route.RESEARCH

    rendered = "\n".join(
        f"{turn.role}: {turn.content[:TURN_CHARS]}" for turn in history[-RECENT_TURNS:]
    )
    try:
        raw = generate(
            _PROMPT.format(history=rendered, question=question),
            chain=chain,
            max_output_tokens=DEFAULT_CONFIG.plan_model_max_tokens,
        )
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        return Route(str(payload.get("route", "")).strip().upper())
    except Exception:
        return Route.RESEARCH
