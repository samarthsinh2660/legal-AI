"""Fill a template with a drafted structure and return a .docx.

A .docx rather than a PDF because what we produce is a draft, not a
finished instrument: the advocate puts it on their letterhead, adds their
enrolment number, settles the facts and signs. Word is the format of the
drafting stage precisely because it can be edited; handing a lawyer a PDF
hands them something to retype.

docxtpl rather than building the document call by call, so the layout lives
in a .docx a person can open in Word and change with no deployment. See
scripts/build_draft_template.py.

The amount is substituted here, not by the model. `Kaveri Plastics v
Mahdoom Bawa` (SC, 2025) holds the sum demanded must equal the cheque
exactly -- a rupee's difference invalidates the notice -- so the figure
comes from the record and the drafter only ever writes a token.
"""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from legal_ai.drafting.models import DraftStructure

TEMPLATES = Path(__file__).parent / "templates"

# What the advocate has to fill when we do not hold a value. Left visible in
# the document on purpose: a blank reads as nothing missing.
UNFILLED = "__________"

_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(
    draft: DraftStructure, *, today: date | None = None, citations: dict[str, str] | None = None
) -> bytes:
    """The draft as a .docx, ready to download.

    `citations` maps each authority id to how it should be cited. Without
    it the body prints `act:2189:sec-138`, which is how this system
    addresses a provision and not how a notice cites one -- see
    drafting.citation, and prefer `render_with_citations`.

    Raises FileNotFoundError when the document type has no template, which
    is a programming error rather than a user's: the type is chosen from a
    fixed list.
    """
    from docxtpl import DocxTemplate

    path = TEMPLATES / f"{draft.document_type}.docx"
    if not path.exists():
        raise FileNotFoundError(f"no template for document type {draft.document_type!r}")

    template = DocxTemplate(str(path))
    template.render(_context(draft, today or date.today(), citations or {}))

    buffer = io.BytesIO()
    template.save(buffer)
    return buffer.getvalue()


def render_with_citations(conn, draft: DraftStructure, *, today: date | None = None) -> bytes:
    """`render`, with every authority resolved against the corpus first."""
    from legal_ai.drafting.citation import format_citation

    citations = {}
    for ground in draft.grounds:
        cited = format_citation(conn, ground.authority)
        if cited is not None:
            citations[ground.authority] = cited
    return render(draft, today=today, citations=citations)


def _context(draft: DraftStructure, today: date, citations: dict[str, str]) -> dict:
    demand = draft.demand
    return {
        "date": today.strftime("%d %B %Y"),
        "subject": _fill(draft.subject, draft.values),
        "recipient": {
            "name": draft.recipient.name,
            "address": _address(draft.recipient.address),
        },
        "sender": {
            "name": draft.sender.name,
            "address": _address(draft.sender.address),
        },
        "facts": [_fill(fact, draft.values) for fact in draft.facts],
        # An id the corpus cannot place is dropped rather than printed. A
        # raw identifier in the body reads as a bug to opposing counsel;
        # the claim still stands on the text around it.
        "grounds": [
            {
                "text": _fill(ground.text, draft.values),
                "authority": citations.get(ground.authority, ""),
            }
            for ground in draft.grounds
        ],
        "demand": {
            "what": _fill(demand.what, draft.values) if demand else "",
            "within_days": demand.within_days if demand else 15,
            "from_when": demand.from_when if demand else "receipt of this notice",
        },
        "consequence": _fill(draft.consequence, draft.values),
        "conclusion": _fill(draft.conclusion, draft.values),
        "annexures": list(draft.annexures),
        "needs_input": list(draft.needs_input),
        "warnings": list(draft.warnings),
    }


def _fill(text: str, values: dict[str, str]) -> str:
    """`text` with its tokens replaced from the record.

    A token with no value becomes a visible blank rather than staying a
    token: `{{amount}}` printed in a notice looks like a bug, while a ruled
    blank looks like a field somebody has to complete -- which it is.
    """
    return _TOKEN.sub(lambda m: values.get(m.group(1)) or UNFILLED, text or "")


def _address(address: str) -> str:
    """An address, or a blank the advocate must fill.

    The drafter writes a placeholder when we hold no address; rendering that
    placeholder into the notice would put "[Address not on file]" on a
    document going to a court.
    """
    text = (address or "").strip()
    if not text or text.startswith(("[", "{{")) or text.lower().startswith("address"):
        return UNFILLED
    return text
