"""The connection pool.

Before this every request opened its own connection: tens of milliseconds of
TCP, TLS and backend fork per call, and nothing bounding how many backends
could exist at once. These tests pin the properties that make a pool a pool
-- one instance per process, connections handed back, a ceiling the database
actually sees -- and the one that keeps it out of the way of everything
else: it must not connect at import.
"""

import pytest

from api.databases import postgres


@pytest.fixture(autouse=True)
def _fresh_pool():
    postgres.close_pool()
    yield
    postgres.close_pool()


def test_the_pool_is_created_once():
    """Two requests arriving together must not each build a pool; the loser
    would be dropped with its connections still open."""
    assert postgres.get_pool() is postgres.get_pool()


def test_a_pooled_connection_answers():
    with postgres.connection() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_a_connection_is_returned_to_the_pool():
    """The whole point. If connections leaked, the pool would exhaust after
    max_size requests and the service would hang rather than fail."""
    pool = postgres.get_pool()
    for _ in range(pool.max_size + 3):
        with postgres.connection() as conn:
            conn.execute("SELECT 1")


def test_a_failed_block_does_not_poison_the_next_borrower():
    """A handler that raises mid-transaction must not hand the next request
    a connection with an open transaction on it."""
    with pytest.raises(Exception):
        with postgres.connection() as conn:
            conn.execute("SELECT * FROM a_table_that_does_not_exist")

    with postgres.connection() as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_the_dsn_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone@elsewhere:5432/other")
    assert postgres.dsn() == "postgresql://someone@elsewhere:5432/other"


def test_the_dsn_falls_back_to_the_local_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert postgres.dsn() == postgres.DEFAULT_DSN


def test_a_malformed_size_falls_back_rather_than_failing(monkeypatch):
    """A service that refuses to boot over a typo in a tuning parameter is
    less available than one that runs with the default."""
    monkeypatch.setenv("LEGAL_AI_DB_POOL_MAX", "not-a-number")
    assert postgres._sized("LEGAL_AI_DB_POOL_MAX", 10) == 10


def test_the_size_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_DB_POOL_MAX", "3")
    assert postgres._sized("LEGAL_AI_DB_POOL_MAX", 10) == 3


def test_closing_lets_a_new_pool_be_built():
    first = postgres.get_pool()
    postgres.close_pool()
    assert postgres.get_pool() is not first


def test_importing_the_module_opens_nothing():
    """A pool that connects at import makes `import api...` fail
    when Postgres is down -- so the process cannot start to report itself
    unhealthy, and every test that merely imports the app needs a database.
    """
    postgres.close_pool()
    assert postgres._pool is None
