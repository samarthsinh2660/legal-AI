"""Treatment read from the reporter's own Case Law Reference table.

Supreme Court Reports close the headnote with an editorial table stating how
the judgment dealt with each authority:

    [2020] 3 SCR 1      followed        Para 7.5
    [2014] 1 SCR 783    referred to     Para 2

Measured 2026-08-29 over an 800-judgment sample: 36% of stored Supreme Court
judgments carry it, and it names 12 overrulings and 37 distinguishings in
that sample alone.

Where this table exists it beats a model outright. It is the reporter's own
classification rather than a reading of prose, it costs nothing, it cannot
hallucinate, and it is the same source a practitioner would check. The model
in `agents/treatment.py` is for the 64% without it, not a replacement for it.

The mapping is the delicate part, and it is deliberately conservative:

  relied on  -> FOLLOWED       applying an authority IS following it
  referred to -> CONSIDERED    the commonest label and the weakest: noted,
                               not adopted. Reading it as following would
                               invent agreement the court never expressed.
  held inapplicable -> DISTINGUISHED
                               it confines the case to its facts, it does
                               not retire it. Reading it as overruling would
                               kill an authority that still binds.

A label not in the map is skipped, never defaulted. Silence is not approval
-- the same rule as the model path.
"""

from __future__ import annotations

import re

from legal_ai.agents.treatment import Treatment

# Only inside the table. The same words appear in ordinary prose ("the High
# Court followed..."), where they describe something other than this
# judgment's treatment of a cited case.
_TABLE_HEADER = re.compile(r"Case\s+Law\s+Reference", re.IGNORECASE)

# The headnote's citation list. Every authority the judgment dealt with is
# named here, and the reporter attaches a label ("- followed.") when there
# is a treatment to report. An entry with no label was therefore cited and
# neither adopted nor doubted, which is what CONSIDERED means.
#
# Deliberately scoped to this block. Assuming CONSIDERED for every citation
# anywhere in a judgment would let good_law report "no negative treatment"
# from an assumption rather than a reading, and that is the one claim this
# system must never make cheaply.
_CITED_BLOCK = re.compile(
    r"(?:Case\s+Law\s+Cited|LIST\s+OF\s+CITATIONS(?:\s+AND\s+OTHER\s+REFERENCES)?)",
    re.IGNORECASE,
)


_LABELS: dict[str, Treatment] = {
    "followed": Treatment.FOLLOWED,
    "relied on": Treatment.FOLLOWED,
    "relied upon": Treatment.FOLLOWED,
    "approved": Treatment.FOLLOWED,
    "affirmed": Treatment.FOLLOWED,
    "applied": Treatment.FOLLOWED,
    "referred": Treatment.CONSIDERED,
    "referred to": Treatment.CONSIDERED,
    "explained": Treatment.CONSIDERED,
    "considered": Treatment.CONSIDERED,
    "cited": Treatment.CONSIDERED,
    "distinguished": Treatment.DISTINGUISHED,
    "held inapplicable": Treatment.DISTINGUISHED,
    "overruled": Treatment.OVERRULED,
    "over-ruled": Treatment.OVERRULED,
}

# Longest first, so "referred to" is not matched as "referred" and
# "held inapplicable" is not lost to a shorter alternative.
_LABEL_PATTERN = "|".join(
    re.escape(label) for label in sorted(_LABELS, key=len, reverse=True)
)

_ANY_SCR = re.compile(r"\[\d{4}\]\s*\d+\s*S\.?\s?C\.?\s?R\.?\s*\d+")

# A label attached to a citation in the block, e.g. "- followed." or
# "-- referred to." rather than the table's "... Para 7" form.
_INLINE_LABEL = re.compile(
    r"(\[\d{4}\]\s*\d+\s*S\.?\s?C\.?\s?R\.?\s*\d+)[^.\[\]]{0,120}?"
    r"[-\u2013\u2014]\s*(" + _LABEL_PATTERN + r")\b",
    re.IGNORECASE,
)

_ROW = re.compile(
    r"(\[\d{4}\]\s*\d+\s*S\.?\s?C\.?\s?R\.?\s*\d+)\s+(" + _LABEL_PATTERN + r")\s+Para",
    re.IGNORECASE,
)

# When a case appears twice in one table -- referred to in one paragraph and
# overruled in another -- the strongest treatment is the one that governs.
_STRENGTH = {
    Treatment.CONSIDERED: 0,
    Treatment.FOLLOWED: 1,
    Treatment.DISTINGUISHED: 2,
    Treatment.OVERRULED: 3,
}


def extract_treatment_table(text: str) -> list[tuple[str, Treatment]]:
    """(citation, treatment) pairs from `text`'s Case Law Reference table.

    Empty when the judgment has no such table, which is the majority case
    and not a failure -- those go to the model instead.
    """
    if not text:
        return []

    block = _CITED_BLOCK.search(text)
    if not _TABLE_HEADER.search(text) and not block:
        return []

    strongest: dict[str, tuple[str, Treatment]] = {}

    def record(citation: str, treatment: Treatment) -> None:
        key = re.sub(r"[^A-Z0-9]", "", citation.upper())
        current = strongest.get(key)
        if current is None or _STRENGTH[treatment] > _STRENGTH[current[1]]:
            strongest[key] = (citation, treatment)

    # Weakest first, so a label later overrides a bare listing.
    if block:
        # From the block heading to the end of the headnote. The whole tail
        # is used rather than a guessed span: an over-wide window can only
        # add citations the judgment genuinely dealt with.
        for match in _ANY_SCR.finditer(text[block.start():]):
            record(match.group(0), Treatment.CONSIDERED)
        for match in _INLINE_LABEL.finditer(text[block.start():]):
            treatment = _LABELS.get(" ".join(match.group(2).lower().split()))
            if treatment is not None:
                record(match.group(1), treatment)

    for match in _ROW.finditer(text):
        treatment = _LABELS.get(" ".join(match.group(2).lower().split()))
        if treatment is not None:
            record(match.group(1), treatment)

    return list(strongest.values())
