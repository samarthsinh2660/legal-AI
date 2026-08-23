"""Document Agent -- turn an uploaded file into structure for the context.

Runs before the Context Builder, because ThreadContext is defined to hold
case facts and something has to produce them.

It exists as a separate agent for one reason: **context isolation**. A
petition may run to hundreds of pages. This agent spends its own window on
the raw text and returns only structure, so the researcher is never handed
the document body. That is the same pattern research fan-out uses -- one
agent per large input, compressed before it crosses a boundary.

Work is split by what each side is actually good at:

    cited sections   regex, via ingestion.statute_citations -- deterministic,
                     already tested, and a citation is a pattern not a
                     judgement call
    parties, dates,  the model -- these are genuinely ambiguous and cannot
    issues, type     be pattern-matched out of prose

The model's output is parsed and validated here; malformed fields are
dropped rather than trusted, so a bad generation degrades the extraction
instead of corrupting the context.
"""

from __future__ import annotations

import json

from legal_ai.context.models import DocumentFacts
from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate

# Characters of a document sent to the model in one pass. Large enough for a
# notice or agreement whole; longer files are read in windows and merged, so
# a long petition costs more calls rather than losing its tail.
WINDOW_CHARS = 12_000

# Windows read from a single document. Bounds the cost of someone uploading
# a thousand-page exhibit bundle.
MAX_WINDOWS = 6

_FIELDS = ("document_type", "parties", "dates", "issues")

PROMPT = """You are reading part of an Indian legal document.

Extract only what is explicitly present. Do not infer, and do not add
anything the text does not state. Return JSON with exactly these keys:

  "document_type": one of petition, notice, agreement, judgment, order, other
  "parties":  names of the parties
  "dates":    dates that matter, each as written in the document
  "issues":   the legal issues this document raises, one short phrase each

Any key with nothing to report must be an empty list (or null for
document_type). Return ONLY the JSON object.

Document text:
{text}"""


def _windows(text: str) -> list[str]:
    return [
        text[i : i + WINDOW_CHARS]
        for i in range(0, len(text), WINDOW_CHARS)
    ][:MAX_WINDOWS]


def _parse(raw: str) -> dict:
    """Parse the model's JSON, tolerating a fenced code block.

    Returns {} on anything unparseable -- a malformed generation must not
    take the whole extraction down with it.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned.strip())
    except (ValueError, IndexError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strings(value) -> list[str]:
    """Coerce a model field to a list of non-empty strings, dropping
    anything that is not one."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def extract_document_facts(document_id: str, text: str) -> DocumentFacts:
    """Structure of one document. Never returns the document body."""
    merged: dict[str, list[str]] = {field: [] for field in _FIELDS if field != "document_type"}
    document_type: str | None = None

    for window in _windows(text):
        try:
            parsed = _parse(generate(
                PROMPT.format(text=window),
                max_output_tokens=DEFAULT_CONFIG.extraction_model_max_tokens,
            ))
        except Exception:
            # One failed window degrades the extraction; it does not lose
            # the windows that succeeded.
            continue
        if document_type is None and isinstance(parsed.get("document_type"), str):
            document_type = parsed["document_type"].strip() or None
        for field in merged:
            for item in _strings(parsed.get(field)):
                if item not in merged[field]:
                    merged[field].append(item)

    # Citations are a pattern, not a judgement -- extracted deterministically
    # from the whole text rather than asked of the model. Rendered as the
    # phrase a reader would recognise, so the researcher can search it.
    cited = [
        f"Section {ref.section_number} of the {ref.act_name}"
        for ref in extract_section_references(text)
    ]

    return DocumentFacts(
        document_id=document_id,
        document_type=document_type,
        parties=tuple(merged["parties"]),
        dates=tuple(merged["dates"]),
        cited_sections=tuple(dict.fromkeys(cited)),
        issues=tuple(merged["issues"]),
    )
