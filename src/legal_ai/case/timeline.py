"""Build a case timeline from what the Document Agent extracted.

No model call. The Document Agent already decided which dates matter and
returned them as the document wrote them; turning "15.03.2021" into a date
is parsing, not judgement, and a model asked to do it can silently invent a
year. A wrong date in a limitation argument loses the case, so this stays
deterministic and refuses rather than guesses.

Indian legal documents write dates in several forms, and day-first is the
convention throughout -- 03/04/2021 is 3 April, never 4 March. That is why
no month-first format is accepted: allowing both would make every ambiguous
date a coin toss.
"""

from __future__ import annotations

import re
from datetime import date

from legal_ai.case.models import TimelineEntry
from legal_ai.context.models import DocumentFacts

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# 15.03.2021 | 15-03-2021 | 15/03/2021 -- day first, always.
_NUMERIC = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")

# 15 March 2021 | 15th March, 2021
_DAY_MONTH_YEAR = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"
)

# March 15, 2021 -- month name first is unambiguous, so it is safe to accept
# even though numeric month-first is not.
_MONTH_DAY_YEAR = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"
)


def parse_date(text: str) -> date | None:
    """The calendar date in `text`, or None if there isn't one we trust.

    None is a normal outcome, not a failure: "the following Monday" and
    "within 30 days" are real events with no resolvable date, and the entry
    survives without one.
    """
    match = _NUMERIC.search(text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        return _safe_date(year, month, day)

    match = _DAY_MONTH_YEAR.search(text)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return _safe_date(int(year), month, int(day))

    match = _MONTH_DAY_YEAR.search(text)
    if match:
        month_name, day, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return _safe_date(int(year), month, int(day))

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    """None on an impossible date rather than raising -- 31.02.2021 is a
    typo in someone's notice, not a reason to fail the whole case view."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def build_timeline(documents: tuple[DocumentFacts, ...]) -> tuple[TimelineEntry, ...]:
    """Every dated event across the case's documents, earliest first.

    Undated entries sort last rather than being dropped, so a reader sees
    the sequence that is known and, after it, what could not be placed. The
    alternative -- hiding them -- shows a confident timeline with holes in
    it.
    """
    entries: list[TimelineEntry] = []
    seen: set[tuple[str, str]] = set()
    for facts in documents:
        for raw in facts.dates:
            key = (facts.document_id, raw.strip())
            if not raw.strip() or key in seen:
                continue
            seen.add(key)
            entries.append(
                TimelineEntry(
                    raw=raw.strip(),
                    document_id=facts.document_id,
                    parsed=parse_date(raw),
                )
            )

    dated = sorted((e for e in entries if e.parsed is not None), key=lambda e: e.parsed)
    undated = [e for e in entries if e.parsed is None]
    return tuple(dated + undated)
