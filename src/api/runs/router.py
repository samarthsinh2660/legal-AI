"""Run routes -- watching work that is already going.

The stream here is deliberately not the one that starts a run. Posting a
message opens a stream as a side effect of asking; this one attaches to a
run already in flight, which is what a reopened tab, a second device or a
recovered connection needs.

`Last-Event-ID` is SSE's own mechanism and the browser sends it without
being asked. Replaying from `run_events` and then continuing live is what
makes a reconnect cost nothing but the events actually missed.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from api.databases.postgres import connection
from api.runs import repository as runs
from api.runs.manager import hub
from api.schemas import ErrorResponse, Success
from api.utils.errors import not_found
from api.utils.response import respond, success

router = APIRouter(tags=["runs"])

# The longest a quiet stream waits before reconciling against the table.
#
# Two things settle this number. A proxy idles a silent connection out at
# about 60 seconds, so a heartbeat has to be well inside that. And Postgres
# NOTIFY is not durable -- a notification raised while a listener is
# reconnecting is gone, with no replay -- so something has to read the
# truth periodically or a dropped one strands the reader forever.
#
# It is a ceiling, not an interval: a notification from the worker wakes the
# stream in milliseconds, and this is only what happens when none arrives.
HEARTBEAT_SECONDS = 20

# A run that reaches this without finishing is reported rather than watched
# forever. Matches the graph's own ceiling.
MAX_WATCH_SECONDS = 600


@router.get(
    "/runs/{run_id}",
    response_model=Success[dict],
    responses={404: {"model": ErrorResponse}},
)
async def one_run(request: Request, run_id: str):
    """A run's status, without watching it."""
    with connection() as conn:
        run = runs.get(conn, run_id, request.state.user_id)
    if run is None:
        return respond(not_found("run"))
    return success(run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=Success[dict],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def cancel_run(request: Request, run_id: str):
    """Stop a run that has not finished.

    A queued run stops before it costs anything. A running one is marked and
    the worker stops at its next node -- Python cannot interrupt the call it
    is inside, but it can decline to start another.

    A run that already finished answers 409: its answer is stored and paid
    for, and a client should learn its cancel arrived too late rather than
    believe it worked.
    """
    from api.utils.errors import conflict

    with connection() as conn:
        run = runs.get(conn, run_id, request.state.user_id)
        if run is None:
            return respond(not_found("run"))
        if not runs.cancel(conn, run_id, request.state.user_id):
            return respond(conflict(
                "run_finished", "This run has already finished."
            ))
    return success({"run_id": run_id, "status": "cancelled"})


@router.get("/runs/{run_id}/stream", responses={404: {"model": ErrorResponse}})
async def watch_run(
    request: Request,
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    """Attach to a run in flight, replaying whatever was missed.

    Every event carries its `seq` as the SSE id, so a browser that drops
    and reconnects resumes exactly where it stopped without being told how.
    """
    user_id = request.state.user_id
    with connection() as conn:
        run = runs.get(conn, run_id, user_id)
    if run is None:
        return respond(not_found("run"))

    try:
        seen = int(last_event_id) if last_event_id else 0
    except ValueError:
        # A client that sent something unreadable gets the whole run rather
        # than an error: replaying too much is cheap, losing an event is not.
        seen = 0

    async def events():
        nonlocal seen
        # Subscribed before the first read, so an event raised while this
        # reads the backlog wakes the wait below instead of being missed.
        hub.start()
        woken = hub.subscribe(run_id)
        # Wall clock, not a count of quiet intervals: a chatty run must hit
        # the ceiling too.
        started = asyncio.get_running_loop().time()
        try:
            while True:
                with connection() as conn:
                    # Status first, then events. The worker commits the
                    # status change and the terminal event in one
                    # transaction, so reading events first left a window
                    # where the commit landed between the two: no terminal
                    # event in `pending`, `status` already done, and the
                    # stream closed having sent the reader nothing.
                    status = (runs.get(conn, run_id, user_id) or {}).get("status")
                    pending = runs.events_after(conn, run_id, seen)

                for event in pending:
                    seen = event["seq"]
                    yield (
                        f"id: {event['seq']}\n"
                        f"event: {event['kind']}\n"
                        f"data: {json.dumps(event['payload'])}\n\n"
                    )

                if status not in ("queued", "running"):
                    return
                if asyncio.get_running_loop().time() - started >= MAX_WATCH_SECONDS:
                    yield (
                        "event: error\n"
                        'data: {"code":"timeout",'
                        '"message":"Stopped watching; the run is still going."}\n\n'
                    )
                    return

                # A comment frame. Keeps proxies from idling the connection
                # out; the wait after it is what paces the loop.
                yield ": ping\n\n"
                try:
                    await asyncio.wait_for(woken.get(), HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    # No notification. Read the table anyway -- that is the
                    # whole reason the heartbeat exists.
                    pass
                # Anything else queued behind it is the same signal.
                while not woken.empty():
                    woken.get_nowait()
        finally:
            hub.unsubscribe(run_id, woken)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Proxies buffer by default, which would hold every event until the
        # run ended and defeat the point.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
