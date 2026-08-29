"""Who sat on a judgment, read out of the reporter's header.

Bench size is load-bearing for precedent, not metadata trivia: a larger
bench binds a smaller one, so "which of these two authorities wins" is
unanswerable without it. A five-judge Constitution Bench and a two-judge
bench saying opposite things is not a conflict -- it is a settled question,
and only the count tells them apart.

Read from the text rather than the archive index, because the index has no
bench column. The SCR reporter prints it in brackets under the parties:

    [N. V. RAMANA, CJI, HIMA KOHLI AND C.T. RAVIKUMAR, JJ.]

Deliberately regex and not a model call. The shape is fixed by the
reporter's house style, a model would cost one call per judgment across
thousands of documents, and a wrong bench size is worse than a missing one
-- it would silently reorder authority. What this cannot parse it declines
to guess about, and returns nothing.

High Court judgments use per-court formats that share no common shape and
are not handled here; see docs/phases/PHASE_7_ADVANCED_GRAPHRAG.md.
"""

from __future__ import annotations

import re

# The header only. A bracketed bench further down the page belongs to a
# judgment being quoted, not to this one.
_HEADER_CHARS = 6000

# The closing suffix is what separates a bench from every other bracket in
# the header -- `[2013] 9 S.C.R. 283` must not parse as a one-judge bench.
_BENCH = re.compile(
    r"\[([^\[\]]{6,250}?),?\s*(?:JJ|J|CJI)\s*\.?\s*\]",
    re.IGNORECASE,
)

# `CJI` appears inline exactly where a name would, with or without its
# comma. Left in, it becomes a fictitious extra judge.
_TITLES = {"CJI", "J", "JJ", "CJ"}

_SEPARATOR = re.compile(r",|\bAND\b", re.IGNORECASE)

# `S. A. BOBDE CJI` -- the title runs into the name when the reporter omits
# the comma, so stripping it only at the separator is not enough.
_TRAILING_TITLE = re.compile(r"\s+(?:CJI|CJ|JJ|J)\s*\.?\s*$", re.IGNORECASE)


def extract_bench(text: str) -> list[str]:
    """Judge names from `text`'s header, in the order printed.

    Empty when there is no parseable bench line. Callers must treat that as
    "unknown", never as "one judge" -- an absent bench and a small bench
    rank very differently.
    """
    if not text:
        return []

    match = _BENCH.search(text[:_HEADER_CHARS])
    if match is None:
        return []

    names = []
    for part in _SEPARATOR.split(match.group(1)):
        # `*` marks the judge who wrote the opinion; it is not part of the
        # name. Newlines are PDF line wrapping inside one field.
        name = " ".join(part.replace("*", "").split())
        name = _TRAILING_TITLE.sub("", name)
        if len(name) < 4 or name.upper().strip(". ") in _TITLES:
            continue
        names.append(name)
    return names


def bench_size(text: str) -> int | None:
    """Number of judges, or None when the bench could not be read."""
    names = extract_bench(text)
    return len(names) or None
