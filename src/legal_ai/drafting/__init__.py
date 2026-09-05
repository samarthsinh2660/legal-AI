"""Turn a conversation into a document.

One model call, then a deterministic check. A second call could review the
draft, but every defect worth catching is mechanical -- a citation that was
never retrieved, a document reciting itself as already sent -- and
`validate` catches those every time rather than most of the time.
CLAUDE.md section 4.

No document types. There was a registry of them, each with its own prompt,
its own template and a rule deciding which conversations it fitted, and it
answered "no document fits this thread" to almost every question anyone
asked -- there is one entry for every hundred documents Indian practice
uses. The model now chooses the document the conversation calls for and
lays it out in sections, which is what every legal document is.

A draft that fails validation is returned with its failures rather than
raised: the caller decides whether to refuse it or repair it, and either
way the reason has to survive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.drafting.models import DraftStructure, Paragraph, Section
from legal_ai.drafting.prompt import DRAFT_PROMPT
from legal_ai.drafting.validate import validate
from legal_ai.llm.client import generate


@dataclass(frozen=True)
class DraftResult:
    structure: DraftStructure | None
    # Rules the draft breaks. Empty on a draft fit to render.
    failures: tuple[str, ...] = ()


def draft(matter: str, conversation: str, law: str, retrieved: set[str]) -> DraftResult:
    """A document drafted from one conversation, checked before it returns.

    `retrieved` is the set of ids actually put in front of the model. A
    paragraph citing anything else is a fabricated citation, which is the
    worst failure this feature has.
    """
    if not retrieved:
        return DraftResult(
            None, ("this conversation has not established any law to draft from",)
        )

    try:
        raw = generate(
            DRAFT_PROMPT.format(matter=matter, conversation=conversation, law=law),
            max_output_tokens=DEFAULT_CONFIG.draft_model_max_tokens,
        )
    except Exception:
        return DraftResult(None, ("the model was unreachable",))

    parsed = _parse(raw)
    if parsed is None:
        return DraftResult(None, ("the model's reply could not be read as a draft",))

    structure = _structure(parsed)
    return DraftResult(structure, tuple(validate(structure, retrieved)))


def _parse(raw: str) -> dict | None:
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _structure(parsed: dict) -> DraftStructure:
    return DraftStructure(
        title=_text(parsed.get("title")),
        subject=_text(parsed.get("subject")),
        addressed_to=_text(parsed.get("addressed_to")),
        on_behalf_of=_text(parsed.get("on_behalf_of")),
        sections=tuple(
            _section(block)
            for block in parsed.get("sections") or []
            if isinstance(block, dict)
        ),
        needs_input=tuple(_text(n) for n in parsed.get("needs_input") or [] if _text(n)),
        warnings=tuple(_text(w) for w in parsed.get("warnings") or [] if _text(w)),
    )


def _section(block: dict) -> Section:
    return Section(
        heading=_text(block.get("heading")),
        paragraphs=tuple(
            Paragraph(
                text=_text(item.get("text")),
                authorities=tuple(
                    _text(a) for a in item.get("authorities") or [] if _text(a)
                ),
            )
            for item in block.get("paragraphs") or []
            if isinstance(item, dict) and _text(item.get("text"))
        ),
    )


def _text(value) -> str:
    return str(value).strip() if value is not None else ""
