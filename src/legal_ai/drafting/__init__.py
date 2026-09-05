"""Turn a thread into a document.

One model call, then a deterministic check. A second call could review the
draft, but every defect worth catching is mechanical -- a citation that was
never retrieved, an amount written as a figure, a notice reciting itself as
already sent -- and `validate` catches those every time rather than most of
the time. CLAUDE.md section 4.

The model returns structure only. The template supplies the letterhead
frame, the formal opening, the clause numbering and the signature block, so
a two-page notice costs about 500 words of generation.

A draft that fails validation is returned with its failures rather than
raised: the caller decides whether to show the reader a refusal or to
repair it, and either way the reason has to survive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.drafting.models import Demand, DraftStructure, Ground, Party
from legal_ai.drafting.prompt import NOTICE_PROMPT, OPINION_PROMPT
from legal_ai.drafting.validate import validate
from legal_ai.llm.client import generate

@dataclass(frozen=True)
class DocumentType:
    """A document we can draft, and the law it is built on.

    The list of types is fixed because each one is a .docx a person designed
    in Word; a type with no template is a document we cannot produce. What
    is *not* fixed is which of them a given conversation can support, and
    that is what `rests_on` decides.

    `rests_on` holds id prefixes, not exact ids. A cheque-bounce thread may
    settle s.142 and s.139 without ever citing s.138, and it is still the
    conversation this notice belongs to -- an exact section match would
    refuse it. The prefix is the Act, because a document type is built on an
    Act's scheme rather than on one provision of it.

    Offered where it does not belong, a draft can only fail: the drafter is
    told to omit any ground the retrieved law does not support, so there is
    nothing left. A criminal conspiracy thread was offered a cheque-bounce
    notice on 2026-09-05 and got "rests on no provision" for it.
    """

    value: str
    label: str
    # Id prefixes. Empty means any law at all will do, which is true of an
    # opinion: it advises on whatever the conversation settled.
    rests_on: tuple[str, ...]
    prompt: str
    # False for a document that advises rather than demands.
    makes_a_demand: bool = True
    # False where the document may rest on pure law. A question asked in
    # the abstract has no facts, and inventing some would be worse.
    rests_on_facts: bool = True


# Every document with a template. Fixed, because the templates are files;
# `available_types` is what makes the offer depend on the conversation.
DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    # Works on any thread that established any law. An opinion has no
    # statutory form to satisfy, so there is nothing for the wrong subject
    # matter to invalidate -- which is why it is the one always on offer.
    DocumentType(
        value="legal_opinion",
        label="Legal opinion",
        rests_on=(),
        prompt=OPINION_PROMPT,
        makes_a_demand=False,
        rests_on_facts=False,
    ),
    # An instrument with a form the statute fixes, so it is offered only
    # where the conversation is about that Act. The NI Act's cheque scheme
    # runs s.138 to s.142; a thread anywhere in it is the right one.
    DocumentType(
        value="s138_demand_notice",
        label="Cheque bounce demand notice",
        rests_on=("act:2189:",),
        prompt=NOTICE_PROMPT,
    ),
)


def available_types(authorities: set[str]) -> tuple[DocumentType, ...]:
    """The document types this conversation has established the law for.

    A type with no `rests_on` needs only that the thread settled something.
    A thread that established nothing can be drafted into nothing at all,
    whatever the type: there would be no law to write the document from.
    """
    if not authorities:
        return ()
    return tuple(
        document_type
        for document_type in DOCUMENT_TYPES
        if not document_type.rests_on
        or any(
            authority.startswith(prefix)
            for prefix in document_type.rests_on
            for authority in authorities
        )
    )


def _known(value: str) -> DocumentType | None:
    return next((t for t in DOCUMENT_TYPES if t.value == value), None)


@dataclass(frozen=True)
class DraftResult:
    structure: DraftStructure | None
    # Rules the draft breaks. Empty on a draft fit to render.
    failures: tuple[str, ...] = ()


def draft(
    document_type: str,
    matter: str,
    conversation: str,
    law: str,
    retrieved: set[str],
    values: dict[str, str] | None = None,
) -> DraftResult:
    """A drafted document from one thread, checked before it is returned.

    `retrieved` is the set of ids actually put in front of the model. A
    ground citing anything else is a fabricated citation, which is the worst
    failure this feature has.
    """
    known = _known(document_type)
    if known is None:
        return DraftResult(None, (f"no template for document type {document_type!r}",))

    # Refused before the model is called, not after. Asked for a notice the
    # conversation holds no law for, the drafter would omit every ground and
    # return an empty document -- having been paid for.
    if known not in available_types(retrieved):
        return DraftResult(
            None,
            (
                f"this conversation has not established the law a "
                f"{known.label.lower()} rests on",
            ),
        )

    try:
        raw = generate(
            known.prompt.format(matter=matter, conversation=conversation, law=law),
            max_output_tokens=DEFAULT_CONFIG.draft_model_max_tokens,
        )
    except Exception:
        return DraftResult(None, ("the model was unreachable",))

    parsed = _parse(raw)
    if parsed is None:
        return DraftResult(None, ("the model's reply could not be read as a draft",))

    structure = _structure(document_type, parsed, values or {})
    return DraftResult(
        structure,
        tuple(
            validate(
                structure,
                retrieved,
                needs_demand=known.makes_a_demand,
                needs_facts=known.rests_on_facts,
            )
        ),
    )


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


def _structure(document_type: str, parsed: dict, values: dict[str, str]) -> DraftStructure:
    demand = parsed.get("demand") or {}
    return DraftStructure(
        document_type=document_type,
        subject=_text(parsed.get("subject")),
        recipient=_party(parsed.get("recipient")),
        sender=_party(parsed.get("sender")),
        facts=tuple(_text(fact) for fact in parsed.get("facts") or [] if _text(fact)),
        grounds=tuple(
            Ground(text=_text(item.get("text")), authority=_text(item.get("authority")))
            for item in parsed.get("legal_grounds") or []
            if isinstance(item, dict) and _text(item.get("text"))
        ),
        demand=Demand(
            what=_text(demand.get("what")),
            within_days=_days(demand.get("within_days")),
            from_when=_text(demand.get("from")) or "receipt of this notice",
        ),
        consequence=_text(parsed.get("consequence")),
        conclusion=_text(parsed.get("conclusion")),
        annexures=tuple(_text(a) for a in parsed.get("annexures") or [] if _text(a)),
        needs_input=tuple(_text(n) for n in parsed.get("needs_input") or [] if _text(n)),
        warnings=tuple(_text(w) for w in parsed.get("warnings") or [] if _text(w)),
        values=dict(values),
    )


def _party(raw) -> Party:
    if not isinstance(raw, dict):
        return Party(name="")
    return Party(name=_text(raw.get("name")), address=_text(raw.get("address")))


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _days(value) -> int:
    """The statutory fifteen unless the model was given a reason to differ."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 15
