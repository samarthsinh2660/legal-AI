"""Thread routes.

Identity comes from `request.state.user_id`, set by AuthMiddleware before
routing. No route here re-parses a header, and none can be reached without a
token -- see `api/middleware/auth.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.databases.postgres import connection
from api.schemas import ErrorResponse, Success
from api.threads.controller import send_message
from api.threads.repository import (
    create_thread,
    delete_thread,
    get_thread,
    list_messages,
    list_threads,
    rename_thread,
)
from api.threads.schemas import (
    MessageModel,
    MessageRequest,
    NewThreadRequest,
    RenameThreadRequest,
    ReplyModel,
    ThreadModel,
)
from api.utils.errors import Failure, not_found
from api.utils.pagination import PageParams, PageResponse
from api.utils.response import respond, success

router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", response_model=Success[ThreadModel])
async def new_thread(request: Request, body: NewThreadRequest):
    """Start a thread, optionally inside a case."""
    with connection() as conn:
        thread = create_thread(
            conn,
            request.state.user_id,
            title=body.title or "New conversation",
            case_id=body.case_id,
        )
    return success(ThreadModel(**thread.__dict__).model_dump(), status=201)


@router.get("", response_model=Success[PageResponse[ThreadModel]])
async def my_threads(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """This user's threads, most recently active first."""
    params = PageParams(limit=limit, offset=offset)
    with connection() as conn:
        page = list_threads(conn, request.state.user_id, params.limit, params.offset)
    page.items[:] = [ThreadModel(**t.__dict__).model_dump() for t in page.items]
    return success(PageResponse.of(page).model_dump())


@router.get(
    "/{thread_id}", response_model=Success[ThreadModel],
    responses={404: {"model": ErrorResponse}},
)
async def one_thread(request: Request, thread_id: str):
    with connection() as conn:
        thread = get_thread(conn, thread_id, request.state.user_id)
    if thread is None:
        return respond(not_found("thread"))
    return success(ThreadModel(**thread.__dict__).model_dump())


@router.patch(
    "/{thread_id}", response_model=Success[ThreadModel],
    responses={404: {"model": ErrorResponse}},
)
async def rename(request: Request, thread_id: str, body: RenameThreadRequest):
    """Rename a thread. The title is all a user may edit.

    Messages are not editable: a thread is a record of what was asked and
    what the system answered, and a rewritten question with the old answer
    under it is a false record.
    """
    with connection() as conn:
        thread = rename_thread(conn, thread_id, request.state.user_id, body.title)
    if thread is None:
        return respond(not_found("thread"))
    return success(ThreadModel(**thread.__dict__).model_dump())


@router.delete("/{thread_id}", responses={404: {"model": ErrorResponse}})
async def remove(request: Request, thread_id: str):
    """Delete a thread and its messages.

    A real delete, not a flag. A user deleting a legal question expects it
    gone, and a soft delete that keeps the text is the opposite of what they
    asked for.
    """
    with connection() as conn:
        deleted = delete_thread(conn, thread_id, request.state.user_id)
    if not deleted:
        return respond(not_found("thread"))
    return success({"deleted": thread_id})


@router.get(
    "/{thread_id}/messages", response_model=Success[list[MessageModel]],
    responses={404: {"model": ErrorResponse}},
)
async def thread_messages(request: Request, thread_id: str):
    """Every message in the thread, oldest first."""
    with connection() as conn:
        if get_thread(conn, thread_id, request.state.user_id) is None:
            return respond(not_found("thread"))
        messages = list_messages(conn, thread_id, request.state.user_id)
    return success([MessageModel(**m.__dict__).model_dump() for m in messages])


@router.post(
    "/{thread_id}/messages", response_model=Success[ReplyModel],
    responses={
        404: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def post_message(request: Request, thread_id: str, body: MessageRequest):
    """Send a message and get the reply.

    Counted against the per-user AI budget: a turn that routes to RESEARCH
    costs what a research call costs.
    """
    from api.middleware.rate_limit import check_ai_quota
    from api.utils.errors import rate_limited

    user_id = request.state.user_id
    if check_ai_quota(user_id) is not None:
        return respond(rate_limited())

    with connection() as conn:
        result = await send_message(
            conn, user_id, thread_id, body.message,
            document_ids=body.document_ids,
            verification_level=body.verification_level,
        )
    if isinstance(result, Failure):
        return respond(result)
    return success(ReplyModel(**result.value).model_dump())
