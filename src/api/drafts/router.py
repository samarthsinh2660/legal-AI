"""Drafting routes.

A document is drafted from a thread, so every route here is scoped by one.
A draft that is missing and a draft that is not yours answer the same 404;
telling a caller a document exists confirms the id is real.

The download returns the bytes rather than a link. The file is a row, so
there is no object store to sign a URL against, and a notice is small
enough that streaming it costs nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.databases.postgres import connection
from api.drafts.controller import download, get_draft, list_drafts, start_draft
from api.drafts.schemas import DraftModel, StartedDraftModel
from api.schemas import ErrorResponse, Success
from api.utils.errors import Failure
from api.utils.response import respond, success

router = APIRouter(tags=["drafts"])

# What a .docx is, to a browser deciding whether to download it.
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@router.post(
    "/threads/{thread_id}/drafts",
    response_model=Success[StartedDraftModel],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def new_draft(request: Request, thread_id: str):
    """Draft a document from this conversation.

    Nothing is chosen: the model reads what was asked and what was settled
    and produces the document that follows from it.

    Returns at once with an id. The document takes a model call and a
    render, so the reader polls `status` and the file appears -- the same
    shape a researched answer takes, and for the same reason.
    """
    with connection() as conn:
        result = await start_draft(conn, request.state.user_id, thread_id)
    if isinstance(result, Failure):
        return respond(result)
    return success(StartedDraftModel(**result.value))


@router.get(
    "/threads/{thread_id}/drafts",
    response_model=Success[list[DraftModel]],
    responses={404: {"model": ErrorResponse}},
)
async def thread_drafts(request: Request, thread_id: str):
    """Every document drafted from this thread, newest first."""
    with connection() as conn:
        result = list_drafts(conn, request.state.user_id, thread_id)
    if isinstance(result, Failure):
        return respond(result)
    return success([DraftModel.of(row) for row in result.value.items])


@router.get(
    "/drafts/{draft_id}",
    response_model=Success[DraftModel],
    responses={404: {"model": ErrorResponse}},
)
async def one_draft(request: Request, draft_id: str):
    """One draft's status, warnings and what it still needs."""
    with connection() as conn:
        result = get_draft(conn, request.state.user_id, draft_id)
    if isinstance(result, Failure):
        return respond(result)
    return success(DraftModel.of(result.value))


@router.get("/drafts/{draft_id}/download", responses={404: {"model": ErrorResponse}})
async def draft_file(request: Request, draft_id: str):
    """The .docx itself.

    Not enveloped: this one returns a file, and a browser saving it wants
    the bytes rather than JSON around them.
    """
    with connection() as conn:
        result = download(conn, request.state.user_id, draft_id)
    if isinstance(result, Failure):
        return respond(result)

    filename = result.value["filename"]
    return Response(
        content=result.value["content"],
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
