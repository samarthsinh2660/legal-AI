"""The service: assembly, and the one route with no domain.

A domain package has router (the only layer that speaks HTTP), controller
(returns `Ok`/`Failure`) and repository (the only layer with SQL):

    accounts/   register, login, identify the caller
    research/   the research graph, bounded and off the event loop

`/health` has no rules and no table, so it lives here rather than in three
files of its own. Anything with no storage and no business logic is a helper
and belongs in `utils/`.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.accounts.router import router as accounts_router
from api.databases.postgres import connection
from api.middleware.rate_limit import RateLimiter, RateLimitMiddleware
from api.research.router import router as research_router
from api.schemas import HealthResponse, Success
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
    application.add_middleware(RateLimitMiddleware, limiter=limiter)

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

    application.include_router(accounts_router)
    application.include_router(research_router)
    return application


app = create_app()
