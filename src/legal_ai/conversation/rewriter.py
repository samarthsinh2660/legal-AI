"""Rewrite a follow-up into a question retrieval can answer on its own.

"What about Bombay?" retrieves nothing: the referent is in the previous turn,
not in the words. Over 60% of follow-ups carry an unresolved reference like
that, and collapsing the thread into one standalone question before
retrieving is the established fix.

Only the recent turns are sent. The rewriter needs the referent, not the
transcript, and a long history buries it -- the same "lost in the middle"
effect that makes stuffing history counterproductive everywhere else.

**Fails open.** An unreadable reply, an error, a blank or absurdly long
rewrite all fall back to the user's own words. Degrading to today's
behaviour is recoverable; returning nothing is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate

# Turns of context. Enough to carry a referent across a clarification, few
# enough that the current question stays at the end of the prompt.
RECENT_TURNS = 6

# Characters of each turn. An assistant answer runs to paragraphs; the
# rewriter needs its subject, not its reasoning.
TURN_CHARS = 400

# A rewrite longer than this is not a question. Letting it through would
# push the real query out of the retrieval budget.
MAX_QUESTION_CHARS = 400


@dataclass(frozen=True)
class Turn:
    role: str
    content: str


_PROMPT = """Rewrite the user's latest message as a standalone legal question.

The message may refer to something earlier -- "that case", "what about
Bombay", "does it still apply". Resolve those references using the
conversation so the question can be understood with no other context.

Rules:
- Keep it a question, one sentence, under 40 words.
- Preserve every specific the user gave: sections, courts, dates, parties.
- Add nothing they did not say or imply. Do not answer it.
- If the message already stands alone, return it unchanged.

CONVERSATION:
{history}

LATEST USER MESSAGE: {question}

Reply with JSON only: {{"question": "..."}}"""


def _render(turns: list[Turn]) -> str:
    return "\n".join(
        f"{turn.role}: {turn.content[:TURN_CHARS]}" for turn in turns[-RECENT_TURNS:]
    )


def rewrite_question(
    question: str,
    history: list[Turn],
    chain: tuple[str, ...] = DEFAULT_CONFIG.model_chain,
) -> str:
    """`question` with its references resolved, or `question` unchanged.

    Returns the input untouched when there is no history: a first message
    has nothing to resolve against, and a call would spend budget turning a
    complete question into a different one.
    """
    if not history:
        return question

    try:
        raw = generate(
            _PROMPT.format(history=_render(history), question=question),
            chain=chain,
            max_output_tokens=DEFAULT_CONFIG.plan_model_max_tokens,
        )
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        rewritten = str(payload.get("question", "")).strip()
    except Exception:
        return question

    if not rewritten or len(rewritten) > MAX_QUESTION_CHARS:
        return question
    return rewritten
