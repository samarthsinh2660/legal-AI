"""Turn stored documents into Evidence for the caller.

Two shapes, and the difference matters:

`to_evidence` carries the whole document -- correct when a caller asked for
a specific document by id (get_section, get_judgment), where the whole thing
is the answer.

`build_evidence` carries the passages that matched. A search result should
return the paragraphs that matched, not the head of a 40,000-character
judgment that may be about something else. This is tier 1 of the
progressive disclosure in PHASE_3 §7: search returns small, get_* returns
whole, the source panel's Open returns the PDF.

Returning passages is also what keeps a research agent's compression honest.
Four search results are four passages, not four whole judgments.
"""

from __future__ import annotations

import psycopg

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence, Location

# Set in legal_ai.config.settings, which carries the reasoning.
PASSAGE_CHARS = DEFAULT_CONFIG.passage_chars

# A statute section is carried whole up to this length, rather than as the
# chunk that best matched. 19% of the sections we hold span more than one
# chunk, and a section's meaning is rarely in one of them: s.138 NI Act
# states the offence first and the provisos that decide whether a complaint
# is valid second, so a chunk-level answer described the offence and omitted
# the thirty-day notice. Covers the 95th percentile section (3,114 chars);
# longer ones still fall back to the passage.
SECTION_CHARS = 4000

# Document types whose text is a single provision, short and self-contained.
# Judgments are excluded deliberately -- they run to hundreds of thousands of
# characters, and one carried whole would spend the entire prompt.
_WHOLE_TEXT_TYPES = frozenset({"section"})

# A document too long to carry whole is carried as its nearest few chunks
# rather than its single nearest one. The median judgment we hold is 15,196
# chars across 18 chunks, so one chunk was ~5% of the judgment the analyst
# was citing; the holding and the reasoning it rests on are rarely in the
# same chunk. Three is what the budget buys: chunks run 1,303 chars at the
# median and 1,507 at the 95th percentile, so 4,000 fits three of almost any
# of them. The budget matches SECTION_CHARS, which caps the prompt at the
# same 48,000 chars (12 items) that sections could already reach.
MAX_PASSAGES = 3
EXTRACT_CHARS = 4000

# Marks where text was dropped between two passages that are not adjacent in
# the document. Without it the model reads two distant paragraphs as one.
ELLIPSIS = "[...]"


def to_evidence(doc: CanonicalDocument, content: str | None = None,
                location: Location | None = None) -> Evidence:
    """Evidence for `doc`. `content` overrides the full text with a passage."""
    return Evidence(
        content=content if content is not None else doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        court=doc.court,
        citation=doc.citation,
        provenance=doc.provenance,
        location=location,
    )


def _location(label: str | None) -> Location | None:
    """Location from a chunk's structural marker.

    `paragraph` is set only when the marker is a plain number -- judgments
    number paragraphs, statutes use "(1)" and "(a)", and coercing the latter
    into an integer would invent a paragraph that does not exist.
    """
    if not label:
        return None
    stripped = label.strip().strip("().")
    paragraph = int(stripped) if stripped.isdigit() else None
    return Location(paragraph=paragraph, label=label)


def _matched_passages(
    conn: psycopg.Connection, query: str, document_ids: list[str]
) -> dict[str, list[tuple[int, str, str | None]]]:
    """Nearest passages per document as {document_id: [(ordinal, text, label)]},
    nearest first."""
    if not document_ids:
        return {}

    query_embedding = embed(query)
    passages: dict[str, list[tuple[int, str, str | None]]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, ordinal, text, label FROM (
              SELECT document_id, ordinal, left(text, %s) AS text, label,
                     row_number() OVER (PARTITION BY document_id
                                        ORDER BY embedding <=> %s::vector) AS rn
              FROM document_chunks
              WHERE embedding IS NOT NULL AND document_id = ANY(%s)
            ) t WHERE rn <= %s ORDER BY document_id, rn
            """,
            (PASSAGE_CHARS, query_embedding, document_ids, MAX_PASSAGES),
        )
        for document_id, ordinal, text, label in cur.fetchall():
            passages.setdefault(document_id, []).append((ordinal, text, label))
    return passages


def _extract(passages: list[tuple[int, str, str | None]]) -> tuple[str, str | None]:
    """One extract from the nearest passages, as (text, label of its start).

    Passages are chosen nearest-first until the budget is spent, then laid out
    in document order: a judgment read in similarity order reverses cause and
    holding. `ELLIPSIS` separates passages that were not adjacent, so the
    reader is never shown a gap as continuous text.
    """
    kept = [passages[0]]
    used = len(passages[0][1])
    for passage in passages[1:]:
        cost = len(passage[1]) + len(ELLIPSIS) + 2
        if used + cost > EXTRACT_CHARS:
            break
        kept.append(passage)
        used += cost

    kept.sort(key=lambda p: p[0])
    parts = [kept[0][1]]
    for previous, current in zip(kept, kept[1:]):
        parts.append("" if current[0] == previous[0] + 1 else ELLIPSIS)
        parts.append(current[1])
    return "\n".join(part for part in parts if part)[:EXTRACT_CHARS], kept[0][2]


def build_evidence(
    conn: psycopg.Connection,
    document_ids: list[str],
    query: str | None = None,
) -> list[Evidence]:
    """Fetch documents for `document_ids`, preserving that order.

    With `query`, each result carries the passages that best match it.
    Without one, the whole document is carried -- callers that resolve a
    known id want the document itself.

    `location` marks where the extract *begins* -- the label of its first
    passage in document order. It does not describe the whole extract, which
    may skip forward past `ELLIPSIS`; there is no single marker that would.

    Ids with no stored document are skipped rather than raising: the graph
    can hold a node whose Postgres row was never stored.
    """
    passages = _matched_passages(conn, query, document_ids) if query else {}

    evidence: list[Evidence] = []
    for document_id in document_ids:
        doc = get_document(conn, document_id)
        if doc is None:
            continue
        # A short statute section goes in whole, provisos included. The
        # matched chunk is discarded, and with it its location: the location
        # of a passage is meaningless once the whole section is carried.
        if (
            (doc.document_type or "") in _WHOLE_TEXT_TYPES
            and len(doc.full_text) <= SECTION_CHARS
        ):
            evidence.append(to_evidence(doc, content=doc.full_text))
            continue

        matched = passages.get(document_id)
        if not matched:
            # No chunk: the document was short enough to embed whole, so its
            # own text is the passage. Truncated to the same budget.
            evidence.append(to_evidence(doc, content=doc.full_text[:PASSAGE_CHARS]))
        else:
            text, label = _extract(matched)
            evidence.append(to_evidence(doc, content=text, location=_location(label)))
    return evidence
