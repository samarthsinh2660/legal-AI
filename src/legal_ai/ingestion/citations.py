# src/legal_ai/ingestion/citations.py
"""Regex-based Indian legal citation extraction.

Formats confirmed real in docs/DATA_RECON_FINDINGS.md and the worked
examples in design/pramana-ui.html: SCC, SCR, INSC, AIR, and state-report
formats (GLR, etc). This is intentionally regex, not an LLM — see
docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.4.

Used only for judgment-to-judgment CITES edges. Statute references are a
separate extractor (statute_citations.extract_section_references) and
nothing here touches them.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+"),           # (2019) 8 SCC 729
    # Supreme Court Reports. Added 2026-08-27: the Bharat Courts archive
    # reports every Supreme Court judgment by its SCR citation, and SCR is
    # also how those judgments cite each other -- 3,121 SCR references sat
    # in the corpus unextracted while CITES resolved 2 edges. Spacing and
    # stops vary in the source PDFs ("S.C.R.", "S C R", "SCR"), hence the
    # tolerant separators.
    # Horizontal whitespace only before the page number. Every page of an
    # SCR judgment is stamped "858 SUPREME COURT REPORTS [2023] 2 S.C.R.",
    # and with \s+ this read across the line break onto the next paragraph
    # number -- manufacturing "[2023] 2 S.C.R. 20", a citation the judgment
    # never made, whose key collided with a real and unrelated case. That
    # phantom edge was then classified OVERRULED from nearby prose about a
    # different overruling, reporting a live authority as doubted.
    # A citation wrapped across lines is lost; that costs one edge, where a
    # phantom one costs a false overruling.
    re.compile(r"\[\d{4}\][ \t]+\d+[ \t]+S\.?[ \t]?C\.?[ \t]?R\.?[ \t]+\d+"),  # [2018] 13 S.C.R. 1188
    re.compile(r"\d{4}\s+INSC\s+\d+"),                     # 2023 INSC 1043
    re.compile(r"AIR\s+\d{4}\s+SC\s+\d+"),                 # AIR 1968 SC 1165
    re.compile(r"\d{4}\s+GLR\s+\d+"),                      # 2023 GLR 1
]


def normalise_citation(citation: str) -> str:
    """Case, spacing and stops removed, so `[2018] 13 S.C.R. 1188` and
    `[2018] 13 SCR 1188` are one identifier.

    The same case is printed both ways across the corpus -- sometimes
    within a single PDF -- so matching raw strings silently loses real
    edges. Matching is done on this form; the original is kept for display.
    """
    return re.sub(r"[^A-Z0-9]", "", citation.upper())


def extract_citations(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            citation = match.group(0)
            key = normalise_citation(citation)
            if key not in seen:
                seen.add(key)
                found.append(citation)
    return found


# Characters carried either side of a citation. Wide enough to hold the
# sentence that states the treatment ("we respectfully overrule...") and the
# clause before it, narrow enough that several fit in one model window.
CONTEXT_CHARS = 500


def extract_citation_contexts(text: str) -> list[tuple[str, str]]:
    """(citation, surrounding text) for every occurrence in `text`.

    Whether a judgment followed, distinguished or overruled the case it
    cites is never in the citation -- "(2019) 8 SCC 729" reads the same in
    all three -- it is in the words around it. The graph records only that A
    cites B, so classifying the treatment needs this carried alongside.

    Every *occurrence*, not every distinct citation: a judgment often
    considers a case early and disposes of it late, and keeping only the
    first mention would systematically miss the treatment that matters.
    """
    if not text:
        return []

    found: list[tuple[int, str, str]] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            start = max(match.start() - CONTEXT_CHARS, 0)
            end = min(match.end() + CONTEXT_CHARS, len(text))
            found.append((match.start(), match.group(0), text[start:end]))

    # Source order, so a caller reading them sees the judgment's own
    # sequence of dealing with an authority.
    return [(citation, context) for _position, citation, context in sorted(found)]
