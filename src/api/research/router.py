"""Research routes.

Identity comes from the bearer token, never from the request body. A
`user_id` field a client could set would let anyone read anyone else's case
by typing a different value, so `current_user_id` reads the header and the
route uses its result rather than anything in the payload.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.accounts.controller import current_user_id
from api.research.controller import research as run_research
from api.middleware.rate_limit import check_ai_quota
from api.utils.errors import Failure, Result, internal_error, rate_limited
from api.utils.response import respond, success
from api.schemas import (
    AnswerModel,
    ErrorResponse,
    ResearchRequest,
    ResearchResponse,
    Success,
)
from legal_ai.config import Configuration

log = logging.getLogger(__name__)

router = APIRouter(tags=["research"])

@router.post(
    "/research",
    response_model=Success[ResearchResponse],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def research(request: ResearchRequest, auth: Result = Depends(current_user_id)):
    """Answer one question through the research graph, as the signed-in user."""
    if isinstance(auth, Failure):
        return respond(auth)

    # Per-user, on top of the global address limit: one account behind a
    # shared office address should not spend everyone else's model budget.
    wait = check_ai_quota(auth.value)
    if wait is not None:
        return respond(rate_limited())

    # `from_env`, not the module-level DEFAULT_CONFIG: that one is built
    # from the field defaults and never reads the environment, so a
    # deployment setting LEGAL_AI_VERIFICATION_LEVEL would be ignored and
    # every answer would silently come back in the cheaper mode.
    level = request.verification_level or Configuration.from_env().verification_level
    inputs = {
        "question": request.question,
        "case_id": request.case_id,
        "document_ids": request.document_ids,
        "verification_level": level,
    }

    # The single catch for the unexpected. Everything an operator needs is
    # in the log with its traceback; the client gets a sentence.
    try:
        result = await run_research(inputs)
    except Exception:
        log.exception("research failed")
        return respond(internal_error("Research failed. See server logs."))

    if isinstance(result, Failure):
        return respond(result)

    state = result.value
    answer = state.get("draft_answer")
    return success(
        ResearchResponse(
            answer=AnswerModel.of(answer) if answer is not None else None,
            clarification_needed=state.get("clarification_needed"),
            text=state.get("answer"),
            verification_level=level,
        ).model_dump()
    )
