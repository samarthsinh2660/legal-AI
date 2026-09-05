"""The service: assembly, and the one route with no domain.

A domain package has router (the only layer that speaks HTTP), controller
(returns `Ok`/`Failure`) and repository (the only layer with SQL):

    accounts/   register, login, identify the caller
    research/   the research graph, bounded and off the event loop
    chat/       multi-turn threads over the same graph

`/health` has no rules and no table, so it lives here rather than in three
files of its own. Anything with no storage and no business logic is a helper
and belongs in `utils/`.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.accounts.router import router as accounts_router
from api.cases.router import router as cases_router
from legal_ai.case.files import ensure_case_file_schema
from legal_ai.case.store import ensure_case_schema
from api.databases.postgres import connection
from api.graph.router import router as graph_router
from api.search.router import router as search_router
from api.documents.router import router as documents_router
from api.drafts.router import router as drafts_router
from api.audit.repository import ensure_audit_schema
from api.audit.router import router as audit_router
from api.middleware.audit import AuditMiddleware
from api.middleware.auth import AuthMiddleware
from api.middleware.rate_limit import RateLimiter, RateLimitMiddleware
from api.schemas import HealthResponse, Success
from api.drafts.repository import ensure_draft_schema
from api.threads.repository import ensure_thread_schema
from api.threads.router import router as threads_router
from api.utils.errors import Ok, Result, invalid_request, service_unavailable
from api.utils.response import respond, success

log = logging.getLogger(__name__)


def postgres_status() -> Result:
    """Whether Postgres answers. Blocking, called in a thread.

    The exception is logged and goes no further: a psycopg error carries the
    DSN, and the DSN carries the password.
    """
    try:
        with connection() as conn:
            conn.execute("SELECT 1")
        return Ok()
    except Exception:
        log.warning("health: postgres unreachable", exc_info=True)
        return service_unavailable("postgres_unreachable", "Postgres did not answer.")


def neo4j_status() -> Result:
    """Whether Neo4j answers. Blocking, called in a thread."""
    try:
        from legal_ai.graphdb.client import get_driver

        driver = get_driver()
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
        return Ok()
    except Exception:
        log.warning("health: neo4j unreachable", exc_info=True)
        return service_unavailable("neo4j_unreachable", "Neo4j did not answer.")


def create_app(limiter: RateLimiter | None = None) -> FastAPI:
    """Build the application.

    Takes a limiter so a test can supply its own instead of reaching into a
    global.
    """
    application = FastAPI(
        title="Pramana AI",
        description="Indian legal research over primary sources.",
        version="0.1.0",
    )
    # Added first, so it runs innermost -- by then AuthMiddleware has set
    # request.state.user_id and there is someone to attribute the event to.
    application.add_middleware(AuditMiddleware)

    # An unauthenticated flood should be turned away by the cheap check,
    # not after a token verification and a database read.
    application.add_middleware(AuthMiddleware)
    application.add_middleware(RateLimitMiddleware, limiter=limiter)

    # Outermost, so a preflight OPTIONS is answered before the rate limiter
    # or the auth check sees it -- a browser sends preflights without
    # credentials, and a 401 there breaks every cross-origin request.
    #
    # Origins come from the environment with no default. A wildcard would
    # let any site a user visits make authenticated calls with their token.
    origins = [
        origin.strip()
        for origin in os.environ.get("LEGAL_AI_CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        """400 rather than FastAPI's 422 for a malformed body.

        A handler because the raise is FastAPI's own, before any of our code
        runs. The detail names the offending field and is built only from
        what the client sent.
        """
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:]) or 'body'}: {error['msg']}"
            for error in exc.errors()
        )
        return respond(invalid_request(problems))

    @application.get(
        "/health", response_model=Success[HealthResponse], tags=["health"]
    )
    async def health() -> HealthResponse:
        """Liveness, plus whether Postgres and Neo4j answer.

        Unauthenticated and unlimited: the probe runs outside any secret the
        app holds, and throttling it turns load into a restart loop.

        Always 200 while the process is up; the status field carries the
        degradation. A 503 would make an orchestrator restart a process that
        cannot fix a database by dying.
        """
        postgres, neo4j = await asyncio.gather(
            asyncio.to_thread(postgres_status),
            asyncio.to_thread(neo4j_status),
        )
        ok = isinstance(postgres, Ok) and isinstance(neo4j, Ok)
        return success(
            HealthResponse(
                status="ok" if ok else "degraded",
                postgres=isinstance(postgres, Ok),
                neo4j=isinstance(neo4j, Ok),
            ).model_dump()
        )

    @application.on_event("startup")
    def _schema() -> None:
        """Create the chat tables once, not per request.

        `CREATE TABLE IF NOT EXISTS` still takes a lock even when it does
        nothing, and calling it on every request is how a bulk job once
        queued an ALTER behind a read and froze every reader for half an
        hour. 001_init.sql covers a fresh deployment; this covers a database
        that predates it.
        """
        try:
            with connection() as conn:
                # Cases first: `threads.case_id` is a foreign key to it, so
                # creating threads on a database without `cases` raises,
                # the except below swallows it, and nothing after this line
                # gets created -- leaving every /cases route to 500 on a
                # column that was never added.
                ensure_case_schema(conn)
                ensure_case_file_schema(conn)
                ensure_thread_schema(conn)
                ensure_draft_schema(conn)
                ensure_audit_schema(conn)
        except Exception:
            # A database that is down must not stop the process starting --
            # it has to come up to report itself unhealthy.
            log.warning("startup: could not ensure chat schema", exc_info=True)

    application.include_router(audit_router)
    application.include_router(accounts_router)
    application.include_router(threads_router)
    application.include_router(cases_router)
    application.include_router(documents_router)
    application.include_router(drafts_router)
    application.include_router(search_router)
    application.include_router(graph_router)
    return application


app = create_app()
