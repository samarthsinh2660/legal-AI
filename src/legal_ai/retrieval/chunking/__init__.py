"""Split long documents into embeddable pieces.

The embedding model has a hard token limit, so any document longer than it
is silently truncated -- the tail is simply never searchable. Chunking
splits those documents on their own structural boundaries so the whole
text becomes retrievable.

Splitting follows legal structure rather than a fixed window: statutes on
sub-section and proviso boundaries, judgments on numbered paragraphs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """One embeddable piece of a document.

    `label` carries the piece's own identity in the source -- a statute's
    sub-section marker ("(2)") or a judgment's paragraph number ("42").
    Paragraph numbers must survive chunking: a citation to "paragraph 42"
    cannot be verified if the number was discarded during splitting.
    """

    text: str
    ordinal: int
    label: str | None = None
