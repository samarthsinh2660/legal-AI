"""One LISTEN connection for the whole process, fanned out to the streams.

A stream that waited on its own `LISTEN` connection would cost one database
backend per viewer, which is the cost SSE was chosen to avoid: two people
watching the same run would open two connections to be told the same thing.
This holds one, and wakes whichever streams care.

What it delivers is a nudge, never data. A woken stream reads `run_events`
itself, which is what makes a dropped notification survivable -- see
`repository._notify`. The heartbeat in the router reads the same table on a
timer, so a stream that is never nudged still finishes; the notification
only decides whether that takes milliseconds or the heartbeat interval.
"""

from __future__ import annotations

import asyncio
import logging

import psycopg

from api.databases.postgres import dsn
from api.runs.repository import CHANGED_CHANNEL

log = logging.getLogger(__name__)

# How long to wait before rebuilding a listener that died. Long enough not
# to spin against a database that is down, short enough that a restart is
# not felt: the streams fall back to their heartbeat meanwhile.
RECONNECT_SECONDS = 2.0


class RunHub:
    """Subscriptions to run changes, backed by one Postgres listener."""

    def __init__(self) -> None:
        self._waiters: dict[str, set[asyncio.Queue]] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Begin listening. Idempotent, and safe to call before any viewer."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """A queue woken whenever `run_id` changes."""
        queue: asyncio.Queue = asyncio.Queue()
        self._waiters.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        waiting = self._waiters.get(run_id)
        if waiting is None:
            return
        waiting.discard(queue)
        if not waiting:
            del self._waiters[run_id]

    async def _listen(self) -> None:
        """Hold the listening connection, rebuilding it if it drops."""
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    dsn(), autocommit=True
                ) as conn:
                    await conn.execute(f"LISTEN {CHANGED_CHANNEL}")
                    async for notification in conn.notifies():
                        self._wake(notification.payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A listener that is down costs latency, not correctness:
                # every stream still reconciles on its heartbeat.
                log.warning("run listener dropped; reconnecting", exc_info=True)
                await asyncio.sleep(RECONNECT_SECONDS)

    def _wake(self, run_id: str) -> None:
        for queue in self._waiters.get(run_id, ()):
            queue.put_nowait(None)


hub = RunHub()
