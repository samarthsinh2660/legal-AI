"""The front door: an uploaded file becomes case facts.

    file bytes
       |
    extract_text          pdf / docx / txt -- no OCR, no guessing
       |
    store_case_file       kept out of the public corpus, see case.files
       |
    extract_document_facts    the Document Agent, one window at a time
       |
    attach_document       the case now holds it
       |
    DocumentFacts         structure only -- what the researcher and the
                          Case Agent read, never the file

This is the step the rest of Phase 4 assumed existed. Everything
downstream consumes `DocumentFacts`, and until now nothing produced them
from a real file.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from legal_ai.agents.document import extract_document_facts
from legal_ai.case.files import (
    ensure_case_file_schema,
    extract_text,
    store_case_file,
    store_facts,
)
from legal_ai.case.store import attach_document
from legal_ai.context.models import DocumentFacts
from legal_ai.ingestion.schema import content_hash


def document_id_for(case_id: str, filename: str) -> str:
    """A stable id for one file in one case.

    Derived from the case and the name rather than random, so re-uploading
    a corrected scan of the same exhibit replaces it instead of adding a
    second copy the user has to notice and delete.
    """
    stem = Path(filename).name
    return f"casefile:{case_id}:{content_hash(stem)[:12]}"


def upload_document(
    conn: psycopg.Connection,
    case_id: str,
    filename: str,
    data: bytes,
    extract_facts: bool = True,
) -> DocumentFacts:
    """Take an uploaded file into a case and return what it says.

    `extract_facts=False` stores the file and skips the model, which is the
    path for a bulk upload where extraction runs later -- a user attaching
    forty exhibits should not wait on forty extractions to see them listed.

    An empty extraction is stored and returned with no facts rather than
    rejected: a scanned PDF with no text layer is still an exhibit in the
    case, and the user needs to see that we could not read it rather than
    have the upload silently fail.
    """
    ensure_case_file_schema(conn)

    text = extract_text(data, filename)
    document_id = document_id_for(case_id, filename)

    store_case_file(conn, case_id, document_id, filename, text)
    attach_document(conn, case_id, document_id)

    if not extract_facts or not text.strip():
        # Not a failure: nothing was attempted. A scan with no text layer
        # and a deferred bulk upload are both "no facts yet", and neither
        # should be reported as an extraction that broke.
        return DocumentFacts(document_id=document_id)

    facts = extract_document_facts(document_id, text)
    # Kept so opening the case later reads structure instead of paying for
    # extraction again. A failed extraction is not stored -- see store_facts.
    store_facts(conn, document_id, facts)
    return facts


def upload_path(
    conn: psycopg.Connection,
    case_id: str,
    path: str | Path,
    extract_facts: bool = True,
) -> DocumentFacts:
    """upload_document for a file on disk. For scripts and tests."""
    file_path = Path(path)
    return upload_document(
        conn,
        case_id,
        file_path.name,
        file_path.read_bytes(),
        extract_facts=extract_facts,
    )
