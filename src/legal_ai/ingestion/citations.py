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
    re.compile(r"\[\d{4}\]\s+\d+\s+S\.?\s?C\.?\s?R\.?\s+\d+"),  # [2018] 13 S.C.R. 1188
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
