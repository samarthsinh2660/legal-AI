"""Case routes.

The container above a thread: a matter holding many conversations plus the
documents and findings they share. Both design flows live here -- create a
case then research it, or research first and attach the thread afterwards.

A case that is missing and a case that is not yours answer the same 404.
Telling a caller a matter exists confirms the id is real.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.cases.repository import (
    attach_thread,
    create,
    delete,
    get,
    listing,
    update,
)
from api.cases.schemas import (
    AttachThreadRequest,
    CaseModel,
    NewCaseRequest,
    UpdateCaseRequest,
)
from api.databases.postgres import connection
from api.schemas import ErrorResponse, Success
from api.utils.errors import not_found
from api.utils.pagination import PageParams, PageResponse
from api.utils.response import respond, success

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=Success[CaseModel])
async def new_case(request: Request, body: NewCaseRequest):
    """Create a matter. Design Flow B: create, upload, then research."""
    with connection() as conn:
        case = create(
            conn,
            request.state.user_id,
            title=body.title,
            court=body.court,
            state=body.state,
            case_number=body.case_number,
            parties=tuple(body.parties),
            matter_type=body.matter_type,
            status=body.status,
            description=body.description,
        )
    return success(CaseModel(**case).model_dump(), status=201)


@router.get("", response_model=Success[PageResponse[CaseModel]])
async def my_cases(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    params = PageParams(limit=limit, offset=offset)
    with connection() as conn:
        page = listing(conn, request.state.user_id, params.limit, params.offset)
    page.items[:] = [CaseModel(**c).model_dump() for c in page.items]
    return success(PageResponse.of(page).model_dump())


@router.get(
    "/{case_id}", response_model=Success[CaseModel],
    responses={404: {"model": ErrorResponse}},
)
async def one_case(request: Request, case_id: str):
    with connection() as conn:
        case = get(conn, case_id, request.state.user_id)
    if case is None:
        return respond(not_found("case"))
    return success(CaseModel(**case).model_dump())


@router.patch(
    "/{case_id}", response_model=Success[CaseModel],
    responses={404: {"model": ErrorResponse}},
)
async def edit_case(request: Request, case_id: str, body: UpdateCaseRequest):
    with connection() as conn:
        case = update(
            conn, case_id, request.state.user_id, **body.model_dump(exclude_unset=True)
        )
    if case is None:
        return respond(not_found("case"))
    return success(CaseModel(**case).model_dump())


@router.delete("/{case_id}", responses={404: {"model": ErrorResponse}})
async def remove_case(request: Request, case_id: str):
    """Delete a matter and its files, findings and sessions.

    Its threads survive, detached: closing a file is not a request to lose
    the questions that were asked in it.
    """
    with connection() as conn:
        if not delete(conn, case_id, request.state.user_id):
            return respond(not_found("case"))
    return success({"deleted": case_id})


@router.post("/{case_id}/threads", responses={404: {"model": ErrorResponse}})
async def attach(request: Request, case_id: str, body: AttachThreadRequest):
    """Design Flow A's "Save to case": attach an existing thread.

    From here on that thread's questions are seeded with this matter's
    parties, documents and established findings.
    """
    with connection() as conn:
        if not attach_thread(conn, case_id, body.thread_id, request.state.user_id):
            return respond(not_found("case or thread"))
    return success({"case_id": case_id, "thread_id": body.thread_id})
