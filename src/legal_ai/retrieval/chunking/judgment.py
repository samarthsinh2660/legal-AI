"""Split judgment text on numbered paragraphs, preserving the numbers.

Paragraph numbers are load-bearing: judgments are cited as "paragraph 42",
and a chunk that has lost its number cannot support or be checked against
such a citation.

Falls back to sentence packing for judgments that carry no paragraph
numbering (short daily orders often do not).
"""

from __future__ import annotations

import re

from legal_ai.retrieval.chunking import Chunk

# A paragraph number at the start of a line: "1.", "42.", "12)".
_PARAGRAPH = re.compile(r"^[ \t]*(\d{1,4})[.)]\s+", re.MULTILINE)

_SENTENCE = re.compile(r"(?<=[.?!])\s+")


def _split_on_paragraphs(text: str) -> list[tuple[str | None, str]]:
    matches = list(_PARAGRAPH.finditer(text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []

    pieces: list[tuple[str | None, str]] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        pieces.append((None, preamble))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start() : end].strip()
        if body:
            pieces.append((match.group(1), body))
    return pieces


def _split_on_words(text: str, max_chars: int) -> list[str]:
    """Last-resort split for text with no usable punctuation."""
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


def _split_oversized(label: str | None, body: str, max_chars: int) -> list[tuple[str | None, str]]:
    parts: list[tuple[str | None, str]] = []
    current = ""
    for sentence in _SENTENCE.split(body):
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
    return parts or [(label, body)]


def chunk_judgment(text: str, max_chars: int = 1600) -> list[Chunk]:
    """Split a judgment into chunks of at most roughly `max_chars`.

    A chunk's label is the paragraph number it starts at, so a retrieved
    excerpt can still be cited precisely.
    """
    if not text or not text.strip():
        return []

    pieces: list[tuple[str | None, str]] = []
    for label, body in _split_on_paragraphs(text):
        if len(body) > max_chars:
            pieces.extend(_split_oversized(label, body, max_chars))
        else:
            pieces.append((label, body))

    chunks: list[Chunk] = []
    current_text = ""
    current_label: str | None = None
    for label, body in pieces:
        candidate = f"{current_text}\n{body}" if current_text else body
        if current_text and len(candidate) > max_chars:
            chunks.append(Chunk(text=current_text, ordinal=len(chunks), label=current_label))
            current_text, current_label = body, label
        else:
            if not current_text:
                current_label = label
            current_text = candidate

    if current_text:
        chunks.append(Chunk(text=current_text, ordinal=len(chunks), label=current_label))
    return chunks
