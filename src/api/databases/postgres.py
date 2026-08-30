"""Postgres connection pool, and the config for it.

A connection per request costs a TCP connect, TLS and a backend fork every
call, with nothing bounding how many backends exist at once. `max_size` is
the ceiling the database sees.

Opened on first use, not at import: a pool that connects at import makes the
app unimportable when Postgres is down, so the process cannot start to
report itself unhealthy.

The corpus layer keeps its own per-call connections on purpose -- its
callers are ingest jobs that hold one for minutes, which would starve the
pool.
"""

from __future__ import annotations

import os
import threading

from psycopg_pool import ConnectionPool

DEFAULT_DSN = "postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai"

# Every worker gets its own pool, so the database sees this times the number
# of workers times replicas.
DEFAULT_MIN_SIZE = 1
DEFAULT_MAX_SIZE = 10

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


def _sized(name: str, fallback: int) -> int:
    """A size knob from the environment, falling back on a bad value.

    Refusing to boot over a typo in a tuning parameter is worse than running
    with the default.
    """
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return fallback


def get_pool() -> ConnectionPool:
    """The process-wide pool, created on first use.

    Double-checked under a lock: two requests arriving together must not
    each build one, or the loser leaks its connections.
    """
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=dsn(),
                    min_size=_sized("LEGAL_AI_DB_POOL_MIN", DEFAULT_MIN_SIZE),
                    max_size=_sized("LEGAL_AI_DB_POOL_MAX", DEFAULT_MAX_SIZE),
                    # Do not block import-time or first-request latency on a
                    # database that is down; let the borrow fail instead, so
                    # the failure is reported by the route that needed it.
                    open=True,
                    timeout=10.0,
                )
    return _pool


def connection():
    """A pooled connection, as a context manager.

    Returned on exit and rolled back if the block raised, so a failed
    handler cannot leave an open transaction for the next request.
    """
    return get_pool().connection()


def close_pool() -> None:
    """Close every pooled connection. For shutdown and for tests."""
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None
