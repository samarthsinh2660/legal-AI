"""CRUD + similarity search over the canonical documents table."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

import psycopg

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.schemas.evidence import Provenance

_WORD_RE = re.compile(r"[A-Za-z]{4,}")
_STOPWORDS = {"the", "act", "and", "for", "act,"}


def upsert_document(
    conn: psycopg.Connection,
    doc: CanonicalDocument,
    embedding: list[float] | None = None,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT content_hash, title, full_text, provenance, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (doc.document_id,),
        )
        row = cur.fetchone()
        if row is not None and row[0] == doc.content_hash:
            return False

        if row is not None:
            # The stored text is about to be overwritten by different
            # text -- an amendment, a correction, or a better scrape. Keep
            # the old version first: a citation to what the law said before
            # must stay checkable after the law changes.
            cur.execute(
                """
                INSERT INTO document_versions (
                    document_id, title, full_text, content_hash,
                    provenance, first_seen_at, superseded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc.document_id,
                    row[1],
                    row[2],
                    row[0],
                    json.dumps(row[3]),
                    row[4],
                    doc.ingested_at,
                ),
            )

        cur.execute(
            """
            INSERT INTO documents (
                document_id, document_type, title, court, citation,
                case_number, parties, decision_date, enactment_date,
                disposal_nature, act_id, full_text, content_hash,
                provenance, ingested_at, embedding
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_id) DO UPDATE SET
                document_type = EXCLUDED.document_type,
                title = EXCLUDED.title,
                court = EXCLUDED.court,
                citation = EXCLUDED.citation,
                case_number = EXCLUDED.case_number,
                parties = EXCLUDED.parties,
                decision_date = EXCLUDED.decision_date,
                enactment_date = EXCLUDED.enactment_date,
                disposal_nature = EXCLUDED.disposal_nature,
                act_id = EXCLUDED.act_id,
                full_text = EXCLUDED.full_text,
                content_hash = EXCLUDED.content_hash,
                provenance = EXCLUDED.provenance,
                ingested_at = EXCLUDED.ingested_at,
                embedding = EXCLUDED.embedding
            """,
            (
                doc.document_id,
                doc.document_type,
                doc.title,
                doc.court,
                doc.citation,
                doc.case_number,
                json.dumps(doc.parties) if doc.parties is not None else None,
                doc.decision_date,
                doc.enactment_date,
                doc.disposal_nature,
                doc.act_id,
                doc.full_text,
                doc.content_hash,
                doc.provenance.model_dump_json(),
                doc.ingested_at,
                embedding,
            ),
        )
    conn.commit()
    return True


def _row_to_document(row: tuple) -> CanonicalDocument:
    (
        document_id, document_type, title, court, citation, case_number,
        parties, decision_date, enactment_date, disposal_nature, act_id,
        full_text, content_hash_value, provenance_json, ingested_at,
    ) = row
    return CanonicalDocument(
        document_id=document_id,
        document_type=document_type,
        title=title,
        court=court,
        citation=citation,
        case_number=case_number,
        parties=parties,
        decision_date=decision_date,
        enactment_date=enactment_date,
        disposal_nature=disposal_nature,
        act_id=act_id,
        full_text=full_text,
        content_hash=content_hash_value,
        provenance=Provenance.model_validate(provenance_json),
        ingested_at=ingested_at,
    )


def get_document(conn: psycopg.Connection, document_id: str) -> CanonicalDocument | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    return _row_to_document(row) if row else None


def find_act_by_name(conn: psycopg.Connection, act_name: str) -> str | None:
    """Resolve a statute name (as written in a judgment) to a stored Act's document_id.

    Requires every significant (4+ letter) word from `act_name` to appear
    in a candidate Act's title, case-insensitively — deliberately strict:
    a wrong Act match would create a false CITES_SECTION edge, which is
    worse than leaving the reference unresolved. Returns the shortest
    matching title on the theory that it's the most specific match.
    """
    words = [w.lower() for w in _WORD_RE.findall(act_name) if w.lower() not in _STOPWORDS]
    if not words:
        return None

    conditions = " AND ".join(f"title ILIKE %s" for _ in words)
    params = [f"%{w}%" for w in words]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT document_id FROM documents
            WHERE document_type = 'act' AND {conditions}
            ORDER BY length(title) ASC
            LIMIT 1
            """,
            params,
        )
        row = cur.fetchone()
    return row[0] if row else None


def find_similar(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[CanonicalDocument, float]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at,
                   embedding <=> %s::vector AS distance
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT %s
            """,
            (query_embedding, limit),
        )
        rows = cur.fetchall()
    return [(_row_to_document(row[:-1]), row[-1]) for row in rows]


@dataclass(frozen=True)
class VersionedText:
    """Text of a document as it stood at a point in time, plus what we
    actually know about the bounds of that claim.

    `is_current` says the answer came from `documents` rather than
    history. `observed_from` / `observed_until` are the ingestion times
    that bracket the version -- not commencement and repeal dates. A
    caller quoting this to a lawyer must pass that distinction on: it
    says "this is the text we had on record then", not "this is the text
    Parliament had enacted then".
    """

    document_id: str
    title: str
    full_text: str
    content_hash: str
    is_current: bool
    observed_from: datetime
    observed_until: datetime | None


def get_text_as_on(
    conn: psycopg.Connection,
    document_id: str,
    as_on: datetime,
) -> VersionedText | None:
    """The stored text of `document_id` as it stood at `as_on`.

    Which text applies is decided by the date of the cause of action, not
    the date of the question, so the current text is frequently the wrong
    one to quote. Returns the oldest superseded version that was still
    current at `as_on`; falls back to the live row when history has
    nothing that late, which is the common case for text that has never
    changed since ingestion.

    Returns None for an unknown document_id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, full_text, content_hash, first_seen_at, superseded_at
            FROM document_versions
            WHERE document_id = %s AND superseded_at > %s
            ORDER BY superseded_at ASC
            LIMIT 1
            """,
            (document_id, as_on),
        )
        row = cur.fetchone()
        if row is not None:
            return VersionedText(
                document_id=document_id,
                title=row[0],
                full_text=row[1],
                content_hash=row[2],
                is_current=False,
                observed_from=row[3],
                observed_until=row[4],
            )

        cur.execute(
            """
            SELECT title, full_text, content_hash, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return VersionedText(
        document_id=document_id,
        title=row[0],
        full_text=row[1],
        content_hash=row[2],
        is_current=True,
        observed_from=row[3],
        observed_until=None,
    )


def list_versions(conn: psycopg.Connection, document_id: str) -> list[VersionedText]:
    """Every superseded version of `document_id`, oldest first.

    Excludes the current text, which lives in `documents` -- use
    get_document for that.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, full_text, content_hash, first_seen_at, superseded_at
            FROM document_versions
            WHERE document_id = %s
            ORDER BY superseded_at ASC
            """,
            (document_id,),
        )
        rows = cur.fetchall()
    return [
        VersionedText(
            document_id=document_id,
            title=title,
            full_text=full_text,
            content_hash=hash_value,
            is_current=False,
            observed_from=first_seen_at,
            observed_until=superseded_at,
        )
        for title, full_text, hash_value, first_seen_at, superseded_at in rows
    ]
