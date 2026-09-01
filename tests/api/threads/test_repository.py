"""Threads and messages.

Every query is scoped to a user id. This is the first table in the system
with an owner, and the scoping is in the WHERE clause rather than checked
afterwards -- a filter applied after the read is one forgotten call away
from serving another firm's thread.
"""

import pytest

from api.threads.repository import (
    add_message,
    create_thread,
    ensure_thread_schema,
    get_thread,
    list_threads,
    list_messages,
)
from api.databases.postgres import connection

USER = "test-user-a"
OTHER = "test-user-b"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()


def test_a_thread_round_trips():
    with connection() as conn:
        created = create_thread(conn, USER, title="Refund question")
        found = get_thread(conn, created.thread_id, USER)
    assert found is not None and found.title == "Refund question"


def test_another_user_cannot_read_it():
    """The whole point of the owner column."""
    with connection() as conn:
        created = create_thread(conn, USER)
        assert get_thread(conn, created.thread_id, OTHER) is None


def test_another_user_cannot_see_it_listed():
    with connection() as conn:
        create_thread(conn, USER)
        assert list_threads(conn, OTHER, limit=10, offset=0).total == 0


def test_messages_come_back_in_order():
    with connection() as conn:
        c = create_thread(conn, USER)
        for n in range(5):
            add_message(conn, c.thread_id, "user" if n % 2 == 0 else "assistant", f"m{n}")
        messages = list_messages(conn, c.thread_id, USER)
    assert [m.content for m in messages] == ["m0", "m1", "m2", "m3", "m4"]


def test_another_user_cannot_read_the_messages():
    with connection() as conn:
        c = create_thread(conn, USER)
        add_message(conn, c.thread_id, "user", "private")
        assert list_messages(conn, c.thread_id, OTHER) == []


def test_an_assistant_message_keeps_its_structured_answer():
    """A later turn cites what was established rather than re-deriving it,
    which needs the claims, not the prose."""
    answer = {"lede": "Yes.", "citations": ["act:2158:sec-18"]}
    with connection() as conn:
        c = create_thread(conn, USER)
        add_message(conn, c.thread_id, "assistant", "Yes.", answer=answer)
        stored = list_messages(conn, c.thread_id, USER)[0]
    assert stored.answer["citations"] == ["act:2158:sec-18"]


def test_a_user_message_has_no_answer():
    with connection() as conn:
        c = create_thread(conn, USER)
        add_message(conn, c.thread_id, "user", "hello")
        assert list_messages(conn, c.thread_id, USER)[0].answer is None


def test_adding_a_message_touches_the_thread():
    """The thread list is ordered by activity, so a reply must move its
    thread to the top."""
    with connection() as conn:
        first = create_thread(conn, USER, title="older")
        second = create_thread(conn, USER, title="newer")
        add_message(conn, first.thread_id, "user", "bump")
        titles = [c.title for c in list_threads(conn, USER, limit=10, offset=0).items]
    assert titles[0] == "older"


def test_a_message_cannot_be_added_to_someone_elses_thread():
    with connection() as conn:
        c = create_thread(conn, USER)
        assert add_message(conn, c.thread_id, "user", "intrusion", user_id=OTHER) is None
        assert list_messages(conn, c.thread_id, USER) == []


def test_listing_is_paged():
    with connection() as conn:
        for n in range(7):
            create_thread(conn, USER, title=f"c{n}")
        page = list_threads(conn, USER, limit=3, offset=0)
    assert len(page.items) == 3 and page.total == 7 and page.has_more


def test_an_unknown_thread_is_none():
    with connection() as conn:
        assert get_thread(conn, "no-such-id", USER) is None
