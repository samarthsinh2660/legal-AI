"""CRUD over document_chunks -- the embeddable pieces of long documents.

A document is represented in vector search exactly once: short documents by
their own embedding, long documents by their chunks. Chunking a document is
therefore paired with clearing its document-level embedding, which is a
truncated and misleading vector.
"""

from __future__ import annotations

import psycopg

from legal_ai.retrieval.chunking import Chunk

# Acts are excluded: an Act's text is its sections concatenated, and each
# section is embedded separately, so chunking Acts would duplicate those
# embeddings and have them compete in results.
CHUNKABLE_TYPES = ("section", "judgment")

# Characters per token on this corpus, against a budget below the model's
# token limit. Kept here so ingest-time and bulk chunking cannot drift
# apart and produce two differently-sized chunk populations.
DEFAULT_MAX_CHARS = int(330 * 4.6)


def upsert_chunks(
    conn: psycopg.Connection,
    document_id: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    """Replace this document's chunks with `chunks`.

    Replace rather than merge so a re-run after a chunker change cannot
    leave stale pieces behind alongside the new ones.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """
                INSERT INTO document_chunks (chunk_id, document_id, ordinal, label, text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    f"{document_id}#{chunk.ordinal}",
                    document_id,
                    chunk.ordinal,
                    chunk.label,
                    chunk.text,
                    embedding,
                ),
            )
    conn.commit()
    return len(chunks)


def chunk_and_store(
    conn: psycopg.Connection,
    document_id: str,
    text: str,
    document_type: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    title: str | None = None,
) -> int:
    """Chunk `text` if it is too long to embed whole, and store the pieces.

    Returns the number of chunks written, or 0 if the document is short
    enough to keep its own whole-document embedding.

    Used both by the bulk builder and at ingest time, so a newly stored
    document is never left in the truncated state chunking exists to fix.

    `title` is embedded with every chunk but not stored in it. A section's
    title is its semantic handle -- "Dishonour of cheque for insufficiency
    of funds" -- and none of it appears in the body, so without this the
    section could not be retrieved by its own name. Keeping it out of the
    stored text avoids repeating it in every passage shown to the model.
    """
    from legal_ai.knowledge.static.embeddings import embed_many
    from legal_ai.retrieval.chunking.judgment import chunk_judgment
    from legal_ai.retrieval.chunking.statute import chunk_statute

    if document_type not in CHUNKABLE_TYPES or len(text) <= max_chars:
        return 0

    splitter = chunk_judgment if document_type == "judgment" else chunk_statute
    chunks = splitter(text, max_chars=max_chars)
    if not chunks:
        return 0

    prefix = f"{title}\n" if title else ""
    upsert_chunks(
        conn, document_id, chunks, embed_many([prefix + c.text for c in chunks])
    )

    # The parent's own vector covers only the first max_chars, so drop it:
    # the document is now represented by its chunks, exactly once.
    with conn.cursor() as cur:
        cur.execute("UPDATE documents SET embedding = NULL WHERE document_id = %s", (document_id,))
    conn.commit()
    return len(chunks)


def get_chunks(conn: psycopg.Connection, document_id: str) -> list[Chunk]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT text, ordinal, label FROM document_chunks "
            "WHERE document_id = %s ORDER BY ordinal",
            (document_id,),
        )
        rows = cur.fetchall()
    return [Chunk(text=text, ordinal=ordinal, label=label) for text, ordinal, label in rows]


def delete_chunks(conn: psycopg.Connection, document_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
    conn.commit()


def documents_needing_chunks(
    conn: psycopg.Connection, min_chars: int, limit: int | None = None
) -> list[tuple[str, str, str, str]]:
    """Long documents with no chunks yet, as (id, text, type, title).

    Asking the database what is still missing is what makes the build
    resumable: an interrupted run is continued by running it again.
    """
    sql = """
        SELECT d.document_id, d.full_text, d.document_type, coalesce(d.title, '')
        FROM documents d
        WHERE d.document_type = ANY(%s)
          AND length(d.full_text) > %s
          AND NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.document_id)
        ORDER BY d.document_id
    """
    params: list = [list(CHUNKABLE_TYPES), min_chars]
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
