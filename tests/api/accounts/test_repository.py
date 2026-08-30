"""The users table.

Small surface, and every method on it is one an attacker will reach for.
The tests below pin three things that are easy to get wrong and expensive to
get wrong late.

Email is stored case-folded and unique, because "Sam@x.com" and "sam@x.com"
are the same mailbox everywhere that matters; letting both register creates
two accounts one person cannot tell apart and a support path that leaks one
into the other.

`find_by_email` returns the row including its hash, and nothing else does.
Authentication is the only caller with a reason to see it.

Creating a duplicate raises rather than overwriting. An upsert here would
let anyone who knows an address take the account by registering again.
"""

import pytest

from api.accounts.repository import (
    DuplicateEmail,
    create_user,
    ensure_account_schema,
    find_by_email,
    find_by_id,
)
from legal_ai.knowledge.static.db import get_connection


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_account_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email LIKE 'test-%'")
    connection.commit()
    connection.close()


def test_a_created_user_can_be_found_by_email(conn):
    user = create_user(conn, "test-a@example.com", "hashed-value")
    found = find_by_email(conn, "test-a@example.com")
    assert found is not None
    assert found.user_id == user.user_id
    assert found.password_hash == "hashed-value"


def test_email_is_matched_case_insensitively(conn):
    create_user(conn, "test-Case@Example.com", "h")
    assert find_by_email(conn, "test-case@example.com") is not None


def test_email_is_stored_folded(conn):
    user = create_user(conn, "test-Fold@Example.COM", "h")
    assert user.email == "test-fold@example.com"


def test_a_duplicate_email_is_refused(conn):
    """Not an upsert. Re-registering an address must never take over the
    account that already owns it."""
    create_user(conn, "test-dup@example.com", "first")
    with pytest.raises(DuplicateEmail):
        create_user(conn, "test-dup@example.com", "second")


def test_a_duplicate_differing_only_in_case_is_refused(conn):
    create_user(conn, "test-dup2@example.com", "first")
    with pytest.raises(DuplicateEmail):
        create_user(conn, "TEST-DUP2@EXAMPLE.COM", "second")


def test_an_unknown_email_returns_none_rather_than_raising(conn):
    """A login for an address that does not exist is an ordinary event, not
    an error -- and it must be indistinguishable from a wrong password."""
    assert find_by_email(conn, "test-nobody@example.com") is None


def test_find_by_id_round_trips(conn):
    user = create_user(conn, "test-byid@example.com", "h")
    found = find_by_id(conn, user.user_id)
    assert found is not None and found.email == "test-byid@example.com"


def test_find_by_id_of_a_stranger_is_none(conn):
    assert find_by_id(conn, "00000000-0000-0000-0000-000000000000") is None


def test_ids_are_unguessable(conn):
    """Sequential ids would let a caller with one valid id enumerate the
    rest, which matters as soon as anything is scoped by user."""
    first = create_user(conn, "test-id1@example.com", "h").user_id
    second = create_user(conn, "test-id2@example.com", "h").user_id
    assert first != second
    assert len(first) >= 32


def test_the_schema_is_idempotent(conn):
    ensure_account_schema(conn)
    ensure_account_schema(conn)
    assert find_by_email(conn, "test-nobody@example.com") is None
