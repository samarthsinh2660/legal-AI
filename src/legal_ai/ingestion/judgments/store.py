"""Store a verified judgment — upsert_document + embed + graph edges.

Deliberately separate from dynamic_search.py's fetch/verify step (see
that module's docstring) — call this only after search_judgment() returns
found=True, verified=True, source != "database" (a database hit is
already stored).
"""

from __future__ import annotations

import json

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.ingest import write_judgment
from legal_ai.ingestion.bench import extract_bench
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.chunk_store import chunk_and_store
from legal_ai.knowledge.static.db import (
    ensure_bench_schema,
    ensure_chunk_schema,
    get_connection,
)
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
        chunk_and_store(
            conn, document.document_id, document.full_text,
            document.document_type, title=document.title,
        )

        # Derived from the text, so it is set here rather than in the
        # canonical upsert that statutes also pass through.
        ensure_bench_schema(conn)
        judges = extract_bench(document.full_text)
        conn.execute(
            "UPDATE documents SET judges = %s, bench_size = %s WHERE document_id = %s",
            (json.dumps(judges) if judges else None, len(judges) or None,
             document.document_id),
        )
        conn.commit()

        driver = get_driver()
        try:
            write_judgment(driver, document, pg_conn=conn)
        finally:
            driver.close()
    finally:
        conn.close()
    return changed
