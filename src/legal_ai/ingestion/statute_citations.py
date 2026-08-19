"""Regex-based extraction of Act/Section references from judgment text.

Complements citations.py (judgment-to-judgment reporter citations, e.g.
"(2019) 8 SCC 729") with judgment-to-statute references, e.g. "Section 18
of the Real Estate (Regulation and Development) Act, 2016" or "Section
420 IPC". Intentionally regex, not an LLM, same reasoning as
citations.py — see docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md
§3.4.

This is necessarily best-effort: Act names are written in judgments with
huge variation (short titles, abbreviations, "the said Act", etc.). A
reference this module can't parse, or can't resolve to a stored Act, is
left unresolved rather than guessed — same non-fabrication discipline as
the rest of this project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# "Section 18 of the Real Estate (Regulation and Development) Act, 2016"
# "Sections 3 and 4 of the Indian Easements Act"
# "S. 138 of the Negotiable Instruments Act, 1881"
_SECTION_OF_ACT = re.compile(
    r"(?:Section|Sections|S\.)\s+(\d+[A-Za-z]?)(?:\(\d+\))?\s+of\s+(?:the\s+)?"
    r"([A-Z][A-Za-z,\.\(\)&'\-\s]{3,90}?Act)(?:,?\s*(\d{4}))?",
)

# "Section 420 IPC", "u/s 302 IPC", "S.138 NI Act"
_KNOWN_ABBREVIATIONS = ["IPC", "CrPC", "CPC", "NI Act", "Evidence Act"]
_SECTION_ABBREVIATION = re.compile(
    r"(?:Section|Sections|S\.|u/s\.?)\s*(\d+[A-Za-z]?)(?:\(\d+\))?\s+(" + "|".join(_KNOWN_ABBREVIATIONS) + r")\b",
)


@dataclass
class SectionReference:
    section_number: str
    act_name: str
    act_year: str | None
    raw: str


def extract_section_references(text: str) -> list[SectionReference]:
    found: list[SectionReference] = []
    seen: set[tuple[str, str]] = set()

    for match in _SECTION_OF_ACT.finditer(text):
        section_number, act_name, act_year = match.groups()
        act_name = re.sub(r"\s+", " ", act_name).strip().rstrip(",")
        key = (section_number.upper(), act_name.lower())
        if key in seen:
            continue
        seen.add(key)
        found.append(
            SectionReference(
                section_number=section_number.upper(),
                act_name=act_name,
                act_year=act_year,
                raw=match.group(0),
            )
        )

    for match in _SECTION_ABBREVIATION.finditer(text):
        section_number, abbreviation = match.groups()
        key = (section_number.upper(), abbreviation.lower())
        if key in seen:
            continue
        seen.add(key)
        found.append(
            SectionReference(
                section_number=section_number.upper(),
                act_name=abbreviation,
                act_year=None,
                raw=match.group(0),
            )
        )

    return found
