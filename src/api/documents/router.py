"""Document routes -- upload to a case, list what is attached."""

from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from api.databases.postgres import connection
from api.documents.controller import MAX_UPLOAD_BYTES, files_for, upload
from api.schemas import ErrorResponse
from api.utils.errors import Failure, invalid_request
from api.utils.response import respond, success

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["documents"])


@router.post("", responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def upload_document(
    request: Request, case_id: str, file: UploadFile = File(...)
):
    """Attach a PDF, DOCX, TXT or MD to a case.

    Text is extracted now rather than at question time: a 300-page PDF
    parsed per question puts seconds on every answer, and an unreadable file
    should fail while the user is still looking at the upload.
    """
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        # Read one byte past the ceiling so an oversized file is refused
        # without holding all of it.
        return respond(
            invalid_request(f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")
        )

    with connection() as conn:
        result = upload(conn, case_id, request.state.user_id, file.filename or "upload", data)
    if isinstance(result, Failure):
        return respond(result)
    return success(result.value, status=201)


@router.get("", responses={404: {"model": ErrorResponse}})
async def list_documents(request: Request, case_id: str):
    """What is attached to this case."""
    with connection() as conn:
        result = files_for(conn, case_id, request.state.user_id)
    if isinstance(result, Failure):
        return respond(result)
    return success(result.value)
