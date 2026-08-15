# src/legal_ai/ingestion/citations.py
"""Regex-based Indian legal citation extraction.

Formats confirmed real in docs/DATA_RECON_FINDINGS.md and the worked
examples in design/pramana-ui.html: SCC, INSC, AIR, and state-report
formats (GLR, etc). This is intentionally regex, not an LLM — see
docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.4.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"\(\d{4}\)\s+\d+\s+SCC\s+\d+"),           # (2019) 8 SCC 729
    re.compile(r"\d{4}\s+INSC\s+\d+"),                     # 2023 INSC 1043
    re.compile(r"AIR\s+\d{4}\s+SC\s+\d+"),                 # AIR 1968 SC 1165
    re.compile(r"\d{4}\s+GLR\s+\d+"),                      # 2023 GLR 1
]


def extract_citations(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _PATTERNS:
        for match in pattern.finditer(text):
            citation = match.group(0)
            if citation not in seen:
                seen.add(citation)
                found.append(citation)
    return found
