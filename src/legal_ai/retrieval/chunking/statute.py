"""Split statutory text on sub-section and proviso boundaries.

Never splits mid-clause: a fragment beginning half-way through a
sub-section reads as a different rule than the one actually enacted, which
is worse than a slightly oversized chunk.

Works in characters rather than tokens so it stays dependency-free and
fast to test; callers convert their token budget to characters.
"""

from __future__ import annotations

import re

from legal_ai.retrieval.chunking import Chunk

# Sub-section and clause markers as they appear in Indian statutes:
# "(1)", "(2A)", "(a)", "(iv)". Anchored to a boundary so mid-word
# parentheses in ordinary prose are not mistaken for markers.
_MARKER = re.compile(r"(?:(?<=^)|(?<=[\s;:.—-]))(\((?:\d+[A-Za-z]*|[a-z]{1,3}|[ivxl]{1,6})\))\s")

# A proviso qualifies the clause it follows, so it is kept with that clause
# whenever it fits rather than being treated as a split point.
_SENTENCE = re.compile(r"(?<=[.;])\s+")


def _split_on_markers(text: str) -> list[tuple[str | None, str]]:
    """Break text into (label, clause) pairs at sub-section markers."""
    matches = list(_MARKER.finditer(text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []

    pieces: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        pieces.append((None, preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        clause = text[match.start() : end].strip()
        if clause:
            pieces.append((match.group(1), clause))
    return pieces


def _split_on_words(text: str, max_chars: int) -> list[str]:
    """Last-resort split for text with no usable punctuation at all.

    Tables and unpunctuated lists occur in real statutes; without this they
    would stay oversized and be truncated by the embedder anyway.
    """
    parts: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip() if current else word
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _split_oversized(label: str | None, clause: str, max_chars: int) -> list[tuple[str | None, str]]:
    """Fall back to sentence boundaries for a clause too big to embed.

    Reached only when a single sub-section exceeds the budget on its own,
    so there is no structural boundary left to use.
    """
    parts: list[tuple[str | None, str]] = []
    current = ""
    for sentence in _SENTENCE.split(clause):
        if len(sentence) > max_chars:
            if current:
                parts.append((label, current))
                current = ""
            parts.extend((label, piece) for piece in _split_on_words(sentence, max_chars))
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            parts.append((label, current))
            current = sentence
        else:
            current = candidate
    if current:
        parts.append((label, current))
    return parts or [(label, clause)]


def chunk_statute(text: str, max_chars: int = 1600) -> list[Chunk]:
    """Split statutory text into chunks of at most roughly `max_chars`.

    Consecutive small clauses are packed together so a section does not
    fragment into dozens of one-line chunks; a chunk's label is that of the
    first clause it contains.
    """
    if not text or not text.strip():
        return []

    pieces: list[tuple[str | None, str]] = []
    for label, clause in _split_on_markers(text):
        if len(clause) > max_chars:
            pieces.extend(_split_oversized(label, clause, max_chars))
        else:
            pieces.append((label, clause))

    chunks: list[Chunk] = []
    current_text = ""
    current_label: str | None = None
    for label, clause in pieces:
        candidate = f"{current_text}\n{clause}" if current_text else clause
        if current_text and len(candidate) > max_chars:
            chunks.append(Chunk(text=current_text, ordinal=len(chunks), label=current_label))
            current_text, current_label = clause, label
        else:
            if not current_text:
                current_label = label
            current_text = candidate

    if current_text:
        chunks.append(Chunk(text=current_text, ordinal=len(chunks), label=current_label))
    return chunks
