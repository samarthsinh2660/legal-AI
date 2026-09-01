"""Uploading a document to a case, so the Document Agent can read it.

Text is extracted here, at upload, not at question time. Parsing a 300-page
PDF on every question would put seconds onto every answer, and a file whose
text cannot be read should fail while the user is looking at the upload
rather than silently produce a thinner answer an hour later.

Uploads go to `case_files`, never to `documents`. A client's pleading is
theirs, not corpus, and must never come back from a search someone else runs.
"""

from __future__ import annotations

from legal_ai.case.files import (
    MAX_TEXT_CHARS,
    SUPPORTED_SUFFIXES,
    extract_text,
    list_case_files,
    store_case_file,
)
from api.utils.errors import Ok, Result, invalid_request, not_found

# Uploads are held whole in memory to extract text, and the extracted text
# goes into a prompt. Both want a ceiling.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def owns_case(conn, case_id: str, user_id: str) -> bool:
    """Whether this user may touch this case.

    A case with no owner belongs to nobody: rows created before accounts
    existed are unreachable through the API rather than public.
    """
    row = conn.execute(
        "SELECT 1 FROM cases WHERE case_id = %s AND user_id = %s",
        (case_id, user_id),
    ).fetchone()
    return row is not None


def upload(conn, case_id: str, user_id: str, filename: str, data: bytes) -> Result:
    """Store a file's text against a case.

    A case that is missing and a case that is not yours answer the same 404:
    telling a caller a matter exists confirms the id is real.
    """
    if not owns_case(conn, case_id, user_id):
        return not_found("case")

    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in SUPPORTED_SUFFIXES:
        return invalid_request(
            f"Unsupported file type '{suffix or filename}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}."
        )
    if not data:
        return invalid_request("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        return invalid_request(
            f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB."
        )

    try:
        text = extract_text(data, filename)
    except Exception:
        # The library's own message names paths and offsets; the user needs
        # to know the file is unreadable, not where it broke.
        return invalid_request("Could not read text from that file.")

    if not text.strip():
        # A scan with no text layer. Storing it would give the Document
        # Agent an empty exhibit and the user a quieter answer for no
        # visible reason.
        return invalid_request(
            "No text could be extracted -- the file may be a scan without OCR."
        )

    document_id = f"case-file:{case_id}:{filename}"
    store_case_file(conn, case_id, document_id, filename, text[:MAX_TEXT_CHARS])
    return Ok({
        "document_id": document_id,
        "filename": filename,
        "characters": len(text),
    })


def files_for(conn, case_id: str, user_id: str) -> Result:
    if not owns_case(conn, case_id, user_id):
        return not_found("case")
    return Ok([
        {"document_id": document_id, "filename": filename}
        for document_id, filename in list_case_files(conn, case_id)
    ])
