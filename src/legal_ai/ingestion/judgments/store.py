"""Store a verified judgment — upsert_document + embed + graph edges.

Deliberately separate from dynamic_search.py's fetch/verify step (see
that module's docstring) — call this only after search_judgment() returns
found=True, verified=True, source != "database" (a database hit is
already stored).
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_judgment
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.chunk_store import chunk_and_store
from legal_ai.knowledge.static.db import ensure_chunk_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document


def store_judgment(document: CanonicalDocument) -> bool:
    """Upserts into Postgres (with embedding) and writes graph edges
    (CITES, CITES_SECTION, DECIDED_BY) into Neo4j.

    Returns True if the document was newly inserted or changed, False if
    its content_hash already matched what's stored (a true no-op).
    """
    conn = get_connection()
    try:
        ensure_chunk_schema(conn)
        vector = embed(document.full_text)
        changed = upsert_document(conn, document, embedding=vector)

        # Judgments routinely run to tens of thousands of characters, far
        # past what the embedder reads. Without this the tail of every
        # newly fetched judgment would be unsearchable.
        chunk_and_store(conn, document.document_id, document.full_text, document.document_type)

        driver = get_driver()
        try:
            write_judgment(driver, document, pg_conn=conn)
        finally:
            driver.close()
    finally:
        conn.close()
    return changed
