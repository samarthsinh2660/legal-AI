"""The queue tests need the queue to themselves.

Several tests here enqueue a job and then claim it, to drive
`worker.research.run` with exactly the row the API wrote. A worker process
against the same database claims it first -- and then answers it for real,
with real model calls, storing an answer where the test expected its own
fake. The failure that follows is a wrong assertion about content, which
reads like a bug in the code under test and is not one.

So this checks once, up front, and says what to do. Detected by racing a
probe rather than by looking for a process: a worker on another machine is
just as much of a problem and there is nothing local to look for.
"""

from __future__ import annotations

import time

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema

PROBE_USER = "test-queue-probe"

# Long enough for an idle worker woken by NOTIFY, which starts in
# milliseconds; short enough not to be felt at the start of every run.
PROBE_SECONDS = 3.0


@pytest.fixture(scope="session", autouse=True)
def _queue_is_ours():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id = %s", (PROBE_USER,))
        conn.commit()
        thread = create_thread(conn, PROBE_USER)
        run_id = runs.enqueue(conn, thread.thread_id, PROBE_USER, "research", {"probe": True})

    deadline = time.monotonic() + PROBE_SECONDS
    taken = False
    while time.monotonic() < deadline:
        with connection() as conn:
            if (runs.get(conn, run_id, PROBE_USER) or {}).get("status") != "queued":
                taken = True
                break
        time.sleep(0.2)

    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id = %s", (PROBE_USER,))
        conn.commit()

    if taken:
        pytest.exit(
            "A worker is already draining this database's queue, so these "
            "tests would race it for their own jobs -- and lose, "
            "intermittently. Stop it first:\n"
            "    docker compose stop worker\n",
            returncode=1,
        )
