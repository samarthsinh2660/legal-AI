"""Regex-based extraction of Act/Section references from judgment text.

Complements citations.py (judgment-to-judgment reporter citations, e.g.
"(2019) 8 SCC 729") with judgment-to-statute references, e.g. "Section 18
of the Real Estate (Regulation and Development) Act, 2016" or "Section
420 IPC". Intentionally regex, not an LLM, for the same reason
citations.py is: a reference is a fixed printed form, so a regex either
matches it or does not, while a model can also produce one that was never
in the text.

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
# "Section 302 of the Indian Penal Code"
# "Section 154 of the Code of Criminal Procedure, 1973"
#
# Codes as well as Acts: the IPC, CrPC, CPC and IBC are 1,553 sectioned
# documents this could not name, and between them they are most of Indian
# criminal and procedural practice. A name may end in "Code" or open with
# it ("Code of Criminal Procedure"), so both shapes are matched.
#
# And the 2023 codes that replaced them, which end in neither: the
# Bharatiya Nyaya Sanhita and Nagarik Suraksha Sanhita, and the Sakshya
# Adhiniyam. Requiring "Act" or "Code" found none of the 90 judgments that
# name them in full.
_SECTION_OF_ACT = re.compile(
    r"(?:Section|Sections|S\.)\s+(\d+[A-Za-z]?)(?:\(\d+\))?\s+of\s+(?:the\s+)?"
    r"(Code\s+of\s+[A-Z][A-Za-z,\.\(\)&'\-\s]{3,60}?(?=,|\s+\d{4}|$|\s+[a-z])"
    r"|[A-Z][A-Za-z,\.\(\)&'\-\s]{3,90}?(?:Act|Code|Sanhita|Adhiniyam))(?:,?\s*(\d{4}))?",
)

# "Section 420 IPC", "u/s 302 IPC", "U/s 63 BSA", "S.138 NI Act"
_KNOWN_ABBREVIATIONS = ["IPC", "CrPC", "CPC", "NI Act", "Evidence Act", "BNSS", "BNS", "BSA"]
_SECTION_ABBREVIATION = re.compile(
    r"(?:Section|Sections|S\.|[Uu]/[Ss]\.?)\s*(\d+[A-Za-z]?)(?:\(\d+\))?\s+(" + "|".join(_KNOWN_ABBREVIATIONS) + r")\b",
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
    years: dict[str, set[str]] = {}

    def add(key: tuple[str, str], reference: SectionReference) -> None:
        if reference.act_year:
            years.setdefault(key[1], set()).add(reference.act_year)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = reference
            found.append(reference)
        else:
            existing.mentions += 1
            # The bare mention may come first; its year arrives with a later one.
            existing.act_year = existing.act_year or reference.act_year

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

    # A judgment names an Act in full once -- "the Arbitration Act, 1996" --
    # and shortens it after. The bare references are the same Act, so they
    # take the year it wrote. "Arbitration Act" alone is two laws, 1940 and
    # 1996, and 1,126 of its references in the corpus carry no year of their
    # own. A name written with two years is left alone: a judgment comparing
    # the Companies Acts of 1956 and 2013 does not say which a bare
    # "Companies Act" means.
    for reference in found:
        if reference.act_year is None:
            written = years.get(reference.act_name.lower(), set())
            if len(written) == 1:
                reference.act_year = next(iter(written))

    return found
