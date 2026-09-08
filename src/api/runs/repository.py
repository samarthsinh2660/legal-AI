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

import logging
import uuid

import psycopg
from psycopg.types.json import Json

log = logging.getLogger(__name__)

# What a run does. One column is the whole of multi-kind support: a worker
# claims only the kinds it can serve.
KINDS = ("research", "draft")

# Woken when a job is enqueued. Workers listen; a missed one costs latency.
QUEUED_CHANNEL = "run_queued"

# Woken when a run gains an event or changes status. The API's connection
# manager listens, once per process, and fans out to the streams it serves.
CHANGED_CHANNEL = "run_changed"

# How many times a run may be handed to a worker before it is treated as
# the problem rather than the worker. A job that kills whoever picks it up
# would otherwise kill every worker in turn, one at a time.
MAX_ATTEMPTS = 3


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
            attempts INT NOT NULL DEFAULT 0,
            heartbeat_at TIMESTAMPTZ,
            checkpoint JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
        """
    )
    # These arrived after the table existed: `payload` with the worker,
    # the rest with the reaper.
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS payload JSONB "
                 "NOT NULL DEFAULT '{}'::jsonb")
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS attempts INT "
                 "NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS checkpoint JSONB")
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
    # The reaper's sweep: only running rows can have stopped breathing.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS runs_heartbeat_idx ON runs (heartbeat_at) "
        "WHERE status = 'running'"
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
        UPDATE runs SET status = 'running', started_at = now(),
                        heartbeat_at = now(), attempts = attempts + 1
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


def restore_findings(conn: psycopg.Connection, run_id: str) -> list:
    """The evidence a previous attempt found, or an empty list.

    All of it or none of it. A half-restored list would put an answer's
    citations on evidence that was never properly rebuilt, which is worse
    than paying for the search again -- so anything unreadable is discarded
    whole and the run searches afresh.
    """
    from legal_ai.schemas.evidence import Evidence

    row = conn.execute(
        "SELECT checkpoint FROM runs WHERE run_id = %s", (run_id,)
    ).fetchone()
    stored = (row[0] or {}).get("findings") if row else None
    if not stored:
        return []
    try:
        return [Evidence.model_validate(item) for item in stored]
    except Exception:
        log.warning("run %s: unreadable checkpoint, searching again", run_id)
        return []


def save_findings(conn: psycopg.Connection, run_id: str, findings) -> None:
    """Keep the evidence this run found, so a retry need not buy it again.

    Only the findings. They are the expensive part -- about 7s of planning
    and 11s of retrieval -- and the only part of the graph channel that
    round-trips provably: Evidence is a pydantic model. The ThreadContext
    is a frozen dataclass and costs 1.3s to rebuild, so it is rebuilt.

    An empty list is not stored. A search that found nothing is not worth
    resuming, and a stored empty list would make the next attempt skip
    searching at all.
    """
    if not findings:
        return
    # Added to, not replaced. `stream_graph` accumulates node outputs, so a
    # resumed run whose verification loops back reports only round two's
    # new evidence -- replacing with that shrank the checkpoint, and the
    # next attempt would answer from a fraction of what had been found.
    kept = {e.document_id: e for e in restore_findings(conn, run_id)}
    kept.update({e.document_id: e for e in findings})
    conn.execute(
        "UPDATE runs SET checkpoint = %s WHERE run_id = %s",
        (Json({"findings": [e.model_dump(mode="json") for e in kept.values()]}), run_id),
    )
    conn.commit()


def cancel(conn: psycopg.Connection, run_id: str, user_id: str) -> bool:
    """Stop a run that has not finished. True if this call stopped it.

    A queued run is cancelled before it costs anything. A running one is
    marked, and the worker stops at its next node -- Python cannot
    interrupt the call it is inside, but it can decline to start another.

    A finished run is left alone: its answer is stored and paid for, and
    throwing it away would help nobody.
    """
    row = conn.execute(
        "UPDATE runs SET status = 'cancelled', finished_at = now() "
        "WHERE run_id = %s AND user_id = %s AND status IN ('queued','running') "
        "RETURNING run_id",
        (run_id, user_id),
    ).fetchone()
    if row is None:
        conn.commit()
        return False
    # A terminal event, or the reader's stream sits open on a run that has
    # stopped and says nothing.
    append(conn, run_id, "error",
           {"code": "cancelled", "message": "This run was cancelled."})
    return True


def beat(conn: psycopg.Connection, run_id: str) -> str | None:
    """Say the worker is still on it, and report what the run is now.

    Returns the status, or None if the run is gone -- which is everything
    the worker needs to decide whether to carry on: `running` means carry
    on, `cancelled` means a reader left, and None means the thread was
    deleted underneath it.

    One statement, because it is one row. Asking separately cost three
    round-trips at every node, twenty-one across a run, and the heartbeat
    only moves for a run that is still going: reviving a cancelled one
    would tell the reaper a worker still owns it.

    Called between graph nodes because that is the only place a synchronous
    graph can be interrupted at all.
    """
    row = conn.execute(
        """
        UPDATE runs
        SET heartbeat_at = CASE WHEN status = 'running' THEN now() ELSE heartbeat_at END
        WHERE run_id = %s
        RETURNING status
        """,
        (run_id,),
    ).fetchone()
    conn.commit()
    return row[0] if row else None


def reap(conn: psycopg.Connection, stale_after: float) -> list[str]:
    """Requeue or fail every run whose worker stopped breathing.

    Returns the ids it touched. A run past `MAX_ATTEMPTS` is failed rather
    than requeued: a job that kills whoever picks it up would otherwise
    kill every worker in turn.

    `stale_after` has to be comfortably longer than the slowest gap between
    two nodes, or a worker deep in a model call is declared dead while it
    is working -- and the answer it goes on to store lands on a run
    somebody else is already redoing.
    """
    # One statement, so the condition is evaluated against the row as it is
    # when it is written. Selecting first and updating row by row committed
    # inside the loop, which released the locks on everything not yet
    # handled -- and every idle worker sweeps, so a second reaper could
    # then requeue a run the first had already requeued and a worker had
    # since claimed. That hands a live job to a second worker: `complete`
    # keeps one answer, but the model budget is spent twice.
    requeued = conn.execute(
        """
        UPDATE runs SET status = 'queued', heartbeat_at = NULL, current_step = NULL
        WHERE status = 'running'
          AND heartbeat_at IS NOT NULL
          AND heartbeat_at < now() - make_interval(secs => %s)
          AND attempts < %s
        RETURNING run_id, kind
        """,
        (stale_after, MAX_ATTEMPTS),
    ).fetchall()
    for _run_id, kind in requeued:
        _notify(conn, QUEUED_CHANNEL, kind)
    conn.commit()

    # Past the attempt ceiling the run is the problem, not the worker. Done
    # separately because each needs its own terminal event, and `fail` is
    # itself guarded so a second reaper doing the same work writes nothing.
    exhausted = conn.execute(
        """
        SELECT run_id, attempts FROM runs
        WHERE status = 'running'
          AND heartbeat_at IS NOT NULL
          AND heartbeat_at < now() - make_interval(secs => %s)
          AND attempts >= %s
        """,
        (stale_after, MAX_ATTEMPTS),
    ).fetchall()
    for run_id, attempts in exhausted:
        fail(conn, run_id, "abandoned",
             f"No worker finished this after {attempts} attempts.")

    return [run_id for run_id, _kind in requeued] + [r for r, _a in exhausted]


def append(conn: psycopg.Connection, run_id: str, kind: str, payload: dict) -> int:
    """Add one event and return its seq.

    The seq is allocated from the run's own rows rather than a sequence, so
    it is dense and per-run -- `Last-Event-ID` is only meaningful against
    the run it came from.
    """
    # Serialised per run, because two writers really do append at once: the
    # worker emits steps and the lede's chunks while the API may be
    # appending the terminal event for a reader who pressed Stop. Reading
    # MAX(seq) without this let both see the same maximum under READ
    # COMMITTED, and the loser hit the (run_id, seq) primary key -- a 500
    # on cancel, or a worker recording its own run as internal_error.
    #
    # An advisory lock rather than a row lock on `runs`: it is held only
    # until this transaction commits, and it does not contend with the
    # status updates that `complete`, `cancel` and `fail` take on that row.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (run_id,))
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


def complete(conn: psycopg.Connection, run_id: str) -> bool:
    """Claim the right to finish this run. True if this caller won it.

    Does not commit, so the caller can write the answer in the same
    transaction. That is what makes a requeued run safe: the reaper can
    only guess, so a worker deep in a model call is sometimes declared dead
    and its run handed to somebody else. Both then finish the same
    question. The row lock this takes means exactly one of them gets past
    here, and the loser writes nothing -- two assistant messages would be
    the visible half, and duplicated case findings the real damage.
    """
    row = conn.execute(
        "UPDATE runs SET status = 'done', finished_at = now() "
        "WHERE run_id = %s AND status = 'running' RETURNING run_id",
        (run_id,),
    ).fetchone()
    return row is not None


def finish(conn: psycopg.Connection, run_id: str, payload: dict) -> bool:
    """Mark the run done and record its terminal event.

    False if somebody else finished it first, in which case nothing is
    written. Callers with an answer to store should use `complete` and
    write it in the same transaction before appending the event.
    """
    if not complete(conn, run_id):
        return False
    append(conn, run_id, "done", payload)
    return True


def fail(conn: psycopg.Connection, run_id: str, code: str, message: str) -> bool:
    """Mark the run failed, with a reason a reader can act on.

    False if the run had already finished, in which case nothing is
    written. Guarded for the same reason `complete` is: the reaper can
    requeue a live run, so a straggling worker sometimes raises long after
    another has stored a good answer. Unguarded, that straggler relabelled
    a `done` run as failed and appended a second terminal event -- the
    thread holding a correct answer while the run told the reader
    "Research failed." It would also overwrite a reader's own `cancelled`.

    A failed run keeps its row. A run that silently disappears is
    indistinguishable from one still going.
    """
    row = conn.execute(
        "UPDATE runs SET status = 'failed', error = %s, finished_at = now() "
        "WHERE run_id = %s AND status = 'running' RETURNING run_id",
        (message[:2000], run_id),
    ).fetchone()
    if row is None:
        return False
    append(conn, run_id, "error", {"code": code, "message": message})
    return True


def get(conn: psycopg.Connection, run_id: str, user_id: str) -> dict | None:
    """One run, or None if it is not this user's."""
    row = conn.execute(
        "SELECT run_id, thread_id, kind, status, current_step, error, "
        "created_at, finished_at, heartbeat_at, attempts "
        "FROM runs WHERE run_id = %s AND user_id = %s",
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


def live_for_thread(
    conn: psycopg.Connection,
    thread_id: str,
    user_id: str,
    kind: str | None = None,
) -> dict | None:
    """The run in flight on this thread, or None.

    What a reopened thread asks in order to decide whether to open a
    stream, so it is the one query on the thread-load path.

    `kind` narrows it. The one-run-per-thread gate wants research only: a
    draft reads the thread and does not write to it, so refusing a question
    while one is being prepared blocked something harmless -- and did it
    with "This thread is still working on the last message", which
    describes a different thing entirely.
    """
    row = conn.execute(
        "SELECT run_id, thread_id, kind, status, current_step, error, "
        "created_at, finished_at, heartbeat_at, attempts FROM runs "
        "WHERE thread_id = %s AND user_id = %s AND status IN ('queued','running') "
        "AND (%s::text IS NULL OR kind = %s) "
        "ORDER BY created_at DESC LIMIT 1",
        (thread_id, user_id, kind, kind),
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
        "heartbeat_at": row[8],
        "attempts": row[9],
    }
