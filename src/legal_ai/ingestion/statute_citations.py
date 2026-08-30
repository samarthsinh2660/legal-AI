"""Regex-based extraction of Act/Section references from judgment text.

Complements citations.py (judgment-to-judgment reporter citations, e.g.
"(2019) 8 SCC 729") with judgment-to-statute references, e.g. "Section 18
of the Real Estate (Regulation and Development) Act, 2016" or "Section
420 IPC". Intentionally regex, not an LLM, same reasoning as
citations.py — see docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md
§3.4.

Best-effort by nature: Act names vary widely in judgments (short titles,
abbreviations, "the said Act"). Anything unparseable or unresolvable is
left unresolved rather than guessed.
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

    # How many times the judgment invokes this section. One mention is a
    # passing reference; a judgment that turns on a provision returns to it.
    # Kept because it is the cheapest signal separating "mentions" from
    # "is about", and de-duplication was throwing it away.
    mentions: int = 1


def extract_section_references(text: str) -> list[SectionReference]:
    """Each distinct section referenced, once, carrying how often it appears.

    De-duplicated by (section, act) as before -- one section is one edge --
    but repeats now increment `mentions` rather than being discarded.
    """
    found: list[SectionReference] = []
    by_key: dict[tuple[str, str], SectionReference] = {}

    def add(key: tuple[str, str], reference: SectionReference) -> None:
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = reference
            found.append(reference)
        else:
            existing.mentions += 1

    for match in _SECTION_OF_ACT.finditer(text):
        section_number, act_name, act_year = match.groups()
        act_name = re.sub(r"\s+", " ", act_name).strip().rstrip(",")
        add(
            (section_number.upper(), act_name.lower()),
            SectionReference(
                section_number=section_number.upper(),
                act_name=act_name,
                act_year=act_year,
                raw=match.group(0),
            ),
        )

    for match in _SECTION_ABBREVIATION.finditer(text):
        section_number, abbreviation = match.groups()
        add(
            (section_number.upper(), abbreviation.lower()),
            SectionReference(
                section_number=section_number.upper(),
                act_name=abbreviation,
                act_year=None,
                raw=match.group(0),
            ),
        )

    return found
