"""Runs and the progress they emit.

A run is a row, not a variable. Before this, a research turn was an
`asyncio.Task` in one process's memory: nothing outside that process knew
it existed, so nothing could watch it, resume it or notice it died. A
reopened tab could only infer "probably still going" from a question with
no answer under it and a five-minute clock.

`run_events` is what makes a reconnect cheap. Each event carries a
monotonic `seq`, which is exactly what SSE's own `Last-Event-ID` is for:
a browser that reconnects sends the last id it saw and gets the rest
replayed, then continues live. Shared storage rather than an in-process
registry, because a registry finds nothing when the reconnect lands on
another worker.

Every event is stored, the lede's word-by-word chunks included. They were
left out while the producer and the reader shared a process and an
`asyncio.Queue`; now the producer is a worker on possibly another machine,
and the table is the only wire between them. Roughly twenty rows per run,
deleted with the thread.

The table is also the queue. `claim` takes a row with `FOR UPDATE SKIP
LOCKED`, which is Postgres's own answer to "hand one job to exactly one
worker" and needs no broker. `NOTIFY` sits in front of it purely for
latency: a worker that misses a notification finds the row on its next
sweep, so a lost notification costs seconds and never a job.
"""

from __future__ import annotations

import uuid

import psycopg
from psycopg.types.json import Json

# What a run can be. `cancelled` has no writer yet -- it arrives with the
# worker, which can decline to start the next step. Listed here because the
# constraint is the schema and adding a value later is a migration.
STATUSES = ("queued", "running", "done", "failed", "cancelled")

# What a run does. One column is the whole of multi-kind support: a worker
# claims only the kinds it can serve.
KINDS = ("research", "draft")

# Woken when a job is enqueued. Workers listen; a missed one costs latency.
QUEUED_CHANNEL = "run_queued"

# Woken when a run gains an event or changes status. The API's connection
# manager listens, once per process, and fans out to the streams it serves.
CHANGED_CHANNEL = "run_changed"


def ensure_run_schema(conn: psycopg.Connection) -> None:
    """Create the run tables if absent. Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL
                REFERENCES threads(thread_id) ON DELETE CASCADE,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'research',
            status TEXT NOT NULL
                CHECK (status IN ('queued','running','done','failed','cancelled')),
            current_step TEXT,
            error TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """
    )
    # The column arrived with the worker, after the table existed.
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS payload JSONB "
                 "NOT NULL DEFAULT '{}'::jsonb")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_events (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            seq INT NOT NULL,
            kind TEXT NOT NULL,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, seq)
        )
        """
    )
    # "Is anything running on this thread" is asked on every thread load.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS runs_thread_live_idx ON runs (thread_id) "
        "WHERE status IN ('queued','running')"
    )
    # The claim query, which every idle worker runs on every sweep.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS runs_queued_idx ON runs (kind, created_at) "
        "WHERE status = 'queued'"
    )
    conn.commit()


def _notify(conn: psycopg.Connection, channel: str, payload: str) -> None:
    """Raise a notification on `channel`.

    `pg_notify` rather than the NOTIFY statement because the channel and the
    payload are values here, and NOTIFY takes literals only.

    Delivered on commit, and only to sessions listening at that moment --
    there is no store and no replay. Everything that depends on one arriving
    also reads the table, so a dropped notification costs latency alone.
    """
    conn.execute("SELECT pg_notify(%s, %s)", (channel, payload))


def enqueue(
    conn: psycopg.Connection,
    thread_id: str,
    user_id: str,
    kind: str,
    payload: dict,
) -> str:
    """Put a job on the queue and return its run id.

    The whole of what the API does for a turn. The row is written before the
    request returns, so a reader who reloads a second later sees a run in
    flight rather than a thread that looks abandoned, and the work itself
    belongs to whichever worker claims it.

    `payload` is the job's entire input. A worker reads it and nothing from
    the request, which is what lets the worker live in another process on
    another machine.
    """
    run_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO runs (run_id, thread_id, user_id, kind, status, payload) "
        "VALUES (%s, %s, %s, %s, 'queued', %s)",
        (run_id, thread_id, user_id, kind, Json(payload)),
    )
    _notify(conn, QUEUED_CHANNEL, kind)
    conn.commit()
    return run_id


def claim(conn: psycopg.Connection, kinds: tuple[str, ...]) -> dict | None:
    """Take the oldest queued job of one of `kinds`, or None.

    `FOR UPDATE SKIP LOCKED` is what makes this safe with any number of
    workers and no broker: a row another worker has locked is stepped over
    rather than waited for, so two workers never claim the same job and
    neither blocks.

    The claim commits before the work starts. Holding the transaction for
    the length of a run would keep the row locked for two minutes and hold a
    pooled connection across every model call in it.
    """
    row = conn.execute(
        """
        UPDATE runs SET status = 'running', started_at = now()
        WHERE run_id = (
            SELECT run_id FROM runs
            WHERE status = 'queued' AND kind = ANY(%s)
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING run_id, thread_id, user_id, kind, payload
        """,
        (list(kinds),),
    ).fetchone()
    conn.commit()
    if row is None:
        return None
    return {
        "run_id": row[0],
        "thread_id": row[1],
        "user_id": row[2],
        "kind": row[3],
        "payload": row[4] or {},
    }


def append(conn: psycopg.Connection, run_id: str, kind: str, payload: dict) -> int:
    """Add one event and return its seq.

    The seq is allocated from the run's own rows rather than a sequence, so
    it is dense and per-run -- `Last-Event-ID` is only meaningful against
    the run it came from.
    """
    row = conn.execute(
        """
        INSERT INTO run_events (run_id, seq, kind, payload)
        SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s FROM run_events WHERE run_id = %s
        RETURNING seq
        """,
        (run_id, kind, Json(payload), run_id),
    ).fetchone()
    _notify(conn, CHANGED_CHANNEL, run_id)
    conn.commit()
    return row[0]


def step(conn: psycopg.Connection, run_id: str, node: str, label: str) -> int:
    """Record which stage the run reached. Both a row and an event.

    `current_step` is what a reopened thread reads without walking the
    events; the event is what a reconnecting stream replays.
    """
    conn.execute("UPDATE runs SET current_step = %s WHERE run_id = %s", (node, run_id))
    return append(conn, run_id, "step", {"node": node, "label": label})


def finish(conn: psycopg.Connection, run_id: str, payload: dict) -> None:
    """Mark the run done and record its terminal event."""
    conn.execute(
        "UPDATE runs SET status = 'done', finished_at = now() WHERE run_id = %s",
        (run_id,),
    )
    append(conn, run_id, "done", payload)


def fail(conn: psycopg.Connection, run_id: str, code: str, message: str) -> None:
    """Mark the run failed, with a reason a reader can act on.

    A failed run keeps its row. A run that silently disappears is
    indistinguishable from one still going.
    """
    conn.execute(
        "UPDATE runs SET status = 'failed', error = %s, finished_at = now() "
        "WHERE run_id = %s",
        (message[:2000], run_id),
    )
    append(conn, run_id, "error", {"code": code, "message": message})


def get(conn: psycopg.Connection, run_id: str, user_id: str) -> dict | None:
    """One run, or None if it is not this user's."""
    row = conn.execute(
        "SELECT run_id, thread_id, kind, status, current_step, error, "
        "created_at, finished_at FROM runs WHERE run_id = %s AND user_id = %s",
        (run_id, user_id),
    ).fetchone()
    return _as_dict(row) if row else None


def exists(conn: psycopg.Connection, run_id: str) -> bool:
    """Whether the run is still there.

    A thread's deletion cascades its runs away, so a worker mid-graph can
    find that the job it is doing no longer has anywhere to put an answer.
    Asked between steps, where the cost is one indexed lookup per node.
    """
    return conn.execute(
        "SELECT 1 FROM runs WHERE run_id = %s", (run_id,)
    ).fetchone() is not None


def live_for_thread(conn: psycopg.Connection, thread_id: str, user_id: str) -> dict | None:
    """The run in flight on this thread, or None.

    What a reopened thread asks in order to decide whether to open a
    stream, so it is the one query on the thread-load path.
    """
    row = conn.execute(
        "SELECT run_id, thread_id, kind, status, current_step, error, "
        "created_at, finished_at FROM runs "
        "WHERE thread_id = %s AND user_id = %s AND status IN ('queued','running') "
        "ORDER BY created_at DESC LIMIT 1",
        (thread_id, user_id),
    ).fetchone()
    return _as_dict(row) if row else None


def events_after(conn: psycopg.Connection, run_id: str, after: int) -> list[dict]:
    """Every event past `after`, oldest first. The replay on reconnect."""
    rows = conn.execute(
        "SELECT seq, kind, payload FROM run_events "
        "WHERE run_id = %s AND seq > %s ORDER BY seq",
        (run_id, after),
    ).fetchall()
    return [{"seq": r[0], "kind": r[1], "payload": r[2] or {}} for r in rows]


def _as_dict(row) -> dict:
    return {
        "run_id": row[0],
        "thread_id": row[1],
        "kind": row[2],
        "status": row[3],
        "current_step": row[4],
        "error": row[5],
        "created_at": row[6],
        "finished_at": row[7],
    }
