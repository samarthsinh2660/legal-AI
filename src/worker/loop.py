"""Claim jobs and run them, until told to stop.

Two mechanisms, and only one of them is load-bearing. The sweep -- claim,
and if there is nothing, wait and claim again -- is what guarantees every
job runs. `LISTEN` in front of it is latency alone: a worker woken by a
notification starts in milliseconds, and a worker that missed one starts on
its next sweep. Nothing is lost either way, which is the only reason it is
safe to build on a signal Postgres does not store.

One job at a time per worker. A research turn is 30-130 seconds of model
calls and holds a model-sized process; running two in one worker would halve
neither. Concurrency is more workers, which the queue already supports --
`FOR UPDATE SKIP LOCKED` is what makes a second one free.
"""

from __future__ import annotations

import logging
import signal
import time

import psycopg

from api.databases.postgres import connection, dsn
from api.runs import repository as runs
from api.runs.repository import KINDS, QUEUED_CHANNEL, claim

log = logging.getLogger(__name__)

# How long an idle worker waits for a notification before sweeping anyway.
# The ceiling on how late a job can start when a notification is lost, and
# the reason a lost one is a latency bug rather than a stuck queue.
IDLE_SECONDS = 5.0

# How long to wait before rebuilding a listener that died. Long enough not
# to spin against a database that is down; the sweep still runs meanwhile.
RECONNECT_SECONDS = 2.0

# How long a run may go without a heartbeat before it is treated as
# abandoned. Comfortably past the graph's own ceiling: a worker deep in a
# model call must never be declared dead while it is working, or the answer
# it goes on to store lands on a run another worker has already been given.
STALE_AFTER_SECONDS = 600.0

_JOBS = {}


def _warm_models() -> None:
    """Make the first real question cheap, whichever way models are served.

    In-process, this loads the embedder and the cross-encoder. Both are
    `lru_cache`d, so it happens once -- but until it does, the first
    question pays for it: measured on a cold worker, 108s for the first
    turn against 18s and 40s for the next two.

    Behind a model server it is instead the first round-trip, which makes
    it a readiness check: a worker that cannot reach its server says so at
    startup rather than on somebody's question.

    Named so a test can replace it, and so the log line below says which
    part of a slow start is this.
    """
    from legal_ai.knowledge.static.embeddings import embed
    from legal_ai.retrieval.rerank import rerank

    embed("warm")
    rerank("warm", [("warm", "warm")])


def _dispatch(job: dict) -> None:
    """Run one job by its kind."""
    if not _JOBS:
        from worker import drafting, research

        _JOBS["research"] = research.run
        _JOBS["draft"] = drafting.run

    handler = _JOBS.get(job["kind"])
    if handler is None:
        # A kind this build does not know. Left running rather than failed:
        # a newer worker may serve it, and the reaper is what will decide.
        log.error("no handler for run kind %r", job["kind"])
        return
    handler(job)


class Worker:
    """The loop, as an object so a test and a signal can both stop it."""

    def __init__(self, kinds: tuple[str, ...] = KINDS) -> None:
        self.kinds = kinds
        self.stopping = False
        self._listener: psycopg.Connection | None = None

    def warm(self) -> None:
        """Ready the models before claiming anything.

        A failure here is logged and not raised. A model host that is down
        should cost the research path, which will fail on its own terms and
        say so, rather than stop a worker that can still draft documents and
        answer from a thread.
        """
        from legal_ai.inference import client

        served = bool(client.embed_url() or client.rerank_url())
        started = time.monotonic()
        try:
            _warm_models()
        except Exception:
            log.warning(
                "models not ready at startup (%s)",
                "model server unreachable" if served else "local load failed",
                exc_info=True,
            )
            return
        log.info(
            "models ready in %.1fs (%s)",
            time.monotonic() - started,
            "served over HTTP" if served else "loaded in-process",
        )

    def stop(self, *_signal) -> None:
        """Finish the job in hand, then exit.

        Not an interrupt: a run killed mid-model-call has already been paid
        for, and the row it would leave says "running" with nothing coming.
        """
        log.info("stopping after the current job")
        self.stopping = True

    def run_forever(self) -> None:
        try:
            while not self.stopping:
                if not self.run_once():
                    self._wait()
        finally:
            self._close_listener()

    def run_once(self) -> bool:
        """Claim and run one job. True if there was one."""
        with connection() as conn:
            job = claim(conn, self.kinds)
        if job is None:
            return False
        log.info("running %s job %s", job["kind"], job["run_id"])
        started = time.monotonic()
        _dispatch(job)
        log.info("finished %s in %.1fs", job["run_id"], time.monotonic() - started)
        return True

    def _wait(self) -> None:
        """Sleep until something is enqueued, or `IDLE_SECONDS` passes.

        Also when the reaper runs. A worker with nothing to do is exactly
        when a row nobody owns is worth looking for, and this saves a
        second process to deploy and watch for one indexed query.
        """
        self._reap()
        try:
            listener = self._listen()
            # `stop_after=1` returns on the first notification; the timeout
            # is what makes this a sweep rather than a wait.
            for _notification in listener.notifies(timeout=IDLE_SECONDS, stop_after=1):
                return
        except Exception:
            log.warning("queue listener dropped; sweeping instead", exc_info=True)
            self._close_listener()
            time.sleep(RECONNECT_SECONDS)

    def _reap(self) -> None:
        """Requeue or fail runs whose worker stopped breathing.

        Failures are swallowed. This is maintenance; a database hiccup in
        it must not stop the worker doing the thing it exists for.
        """
        try:
            with connection() as conn:
                abandoned = runs.reap(conn, stale_after=STALE_AFTER_SECONDS)
            if abandoned:
                log.warning("requeued or failed %d abandoned run(s): %s",
                            len(abandoned), ", ".join(abandoned))
        except Exception:
            log.warning("could not sweep for abandoned runs", exc_info=True)

    def _listen(self) -> psycopg.Connection:
        """The listening connection, opened on first use.

        Its own connection, outside the pool: it holds a session for as long
        as the worker lives, and a pooled one would be checked out forever.
        """
        if self._listener is None or self._listener.closed:
            self._listener = psycopg.connect(dsn(), autocommit=True)
            self._listener.execute(f"LISTEN {QUEUED_CHANNEL}")
        return self._listener

    def _close_listener(self) -> None:
        if self._listener is not None and not self._listener.closed:
            self._listener.close()
        self._listener = None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    with connection() as conn:
        from api.runs.repository import ensure_run_schema

        ensure_run_schema(conn)

    worker = Worker()
    # A container stop sends SIGTERM. Draining rather than dying is what
    # makes a deploy cost nothing: the job in hand finishes, and anything
    # queued is still queued for the next worker.
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)

    worker.warm()
    log.info("worker ready, serving %s", ", ".join(worker.kinds))
    worker.run_forever()
