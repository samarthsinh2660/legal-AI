"""Stage 3 -- does the quoted text actually appear in the cited document?

**No model.** A string comparison answers this with a certainty no model can
offer, and it catches the failure that reached the Delhi High Court in
September 2025: a petition quoting paragraphs 73 and 74 of a judgment that
contains 27 paragraphs. The case was real, the citation resolved, and the
words were invented. Every check we had before this one passes that.

Only quoted spans are checked. A claim that paraphrases has nothing to
string-match, and is left for the semantic stage -- saying nothing is the
correct outcome here, not a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this a "quotation" is a common phrase that will match by accident.
# "the court held" appears in thousands of judgments; matching it proves
# nothing and would turn a free decisive check into a free wrong one.
MIN_QUOTE_CHARS = 40

# Straight and curly quotation marks, and the double-angle marks that appear
# in some Indian PDFs.
_QUOTED = re.compile(r'"([^"]{10,600})"|“([^”]{10,600})”|«([^»]{10,600})»')

_WHITESPACE = re.compile(r"\s+")


def extract_quotations(text: str) -> list[str]:
    """Quoted spans long enough to be worth checking, in order."""
    found: list[str] = []
    for match in _QUOTED.finditer(text):
        quote = next(group for group in match.groups() if group is not None)
        if len(quote.strip()) >= MIN_QUOTE_CHARS:
            found.append(quote.strip())
    return found


def normalise(text: str) -> str:
    """Whitespace collapsed and case dropped, because a quotation copied
    out of a PDF carries that PDF's line breaks and a claim rarely
    reproduces them. Nothing else is normalised: dropping punctuation would
    let "shall not" match "shall", which inverts the meaning of a section.
    """
    return _WHITESPACE.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class QuoteCheck:
    quote: str
    found: bool
    document_id: str | None


def check_quotations(claim_text: str, sources: dict[str, str]) -> list[QuoteCheck]:
    """Each quotation in `claim_text`, and whether it appears in any of
    `sources` (document_id -> full text).

    A quote is satisfied by *any* cited document, not by all of them: a
    claim citing three sections and quoting one of them is correct.
    """
    haystacks = {doc_id: normalise(body) for doc_id, body in sources.items()}
    checks: list[QuoteCheck] = []
    for quote in extract_quotations(claim_text):
        needle = normalise(quote)
        where = next((doc_id for doc_id, body in haystacks.items() if needle in body), None)
        checks.append(QuoteCheck(quote=quote, found=where is not None, document_id=where))
    return checks
