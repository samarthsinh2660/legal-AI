"""Drafting a document from a thread.

The run is detached from the request, like a researched turn, so the
reader who closes the tab still gets the document. Ownership is enforced
through the thread: a draft carries no user_id of its own.
"""

from __future__ import annotations

import pytest

from api.databases.postgres import connection
from api.drafts import controller, repository
from api.threads.repository import add_message, create_thread, ensure_thread_schema
from api.utils.errors import Failure, Ok

class _NotRun:
    """Stands in for the detached task. The drafting run itself is covered
    in tests/drafting; here the question is only what the request returns."""

    def add_done_callback(self, _callback):
        pass


def _detach(monkeypatch):
    monkeypatch.setattr(
        controller.asyncio, "create_task", lambda coro: coro.close() or _NotRun()
    )


USER = "test-user-draft"
OTHER = "test-user-draft-other"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        repository.ensure_draft_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-draft%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-draft%'")
        conn.commit()


def _thread(conn, user=USER):
    thread = create_thread(conn, user, title="Verma v. Malhotra cheque bounce")
    add_message(conn, thread.thread_id, "user", "the cheque bounced")
    add_message(
        conn, thread.thread_id, "assistant", "Section 138 applies.",
        answer={"key_elements": [
            {"text": "Dishonour is an offence.", "evidence_ids": ["act:2189:sec-138"]}
        ]},
    )
    return thread


@pytest.mark.asyncio
async def test_a_draft_starts_and_returns_an_id(monkeypatch):
    _detach(monkeypatch)

    with connection() as conn:
        thread = _thread(conn)
        result = await controller.start_draft(
            conn, USER, thread.thread_id)

    assert isinstance(result, Ok)
    assert result.value["status"] == "running"


@pytest.mark.asyncio
async def test_a_thread_that_is_not_yours_is_a_404(monkeypatch):
    _detach(monkeypatch)

    with connection() as conn:
        thread = _thread(conn)
        result = await controller.start_draft(
            conn, OTHER, thread.thread_id)

    assert isinstance(result, Failure)
    assert result.status == 404


@pytest.mark.asyncio
async def test_two_drafts_of_one_thread_cannot_race(monkeypatch):
    """Two would leave the reader two cards and no way to tell which is
    the document they asked for."""
    _detach(monkeypatch)

    with connection() as conn:
        thread = _thread(conn)
        await controller.start_draft(conn, USER, thread.thread_id)
        again = await controller.start_draft(
            conn, USER, thread.thread_id)

    assert isinstance(again, Failure)
    assert again.status == 409


def test_a_finished_draft_carries_its_file_and_a_failed_one_its_reason():
    with connection() as conn:
        thread = _thread(conn)
        done = repository.start(conn, thread.thread_id)
        repository.finish(conn, done, "notice.docx", {"warnings": ["check limitation"]}, b"PK\x03\x04")
        broken = repository.start(conn, thread.thread_id)
        repository.fail(conn, broken, "cites act:9999:sec-1, which was not retrieved")

        finished = repository.get(conn, done, USER)
        failed = repository.get(conn, broken, USER)
        filename, data = repository.content(conn, done, USER)

    assert finished["status"] == "done" and finished["has_file"] is True
    assert finished["structure"]["warnings"] == ["check limitation"]
    # The reader gets what they can act on, not the validator's wording.
    assert failed["status"] == "failed"
    assert "never established" in failed["error"]
    assert "act:9999" not in failed["error"]
    assert failed["has_file"] is False
    assert (filename, data) == ("notice.docx", b"PK\x03\x04")


def test_another_users_draft_is_invisible():
    with connection() as conn:
        thread = _thread(conn)
        draft_id = repository.start(conn, thread.thread_id)
        repository.finish(conn, draft_id, "notice.docx", {}, b"PK")

        assert repository.get(conn, draft_id, OTHER) is None
        assert repository.content(conn, draft_id, OTHER) is None


def test_a_thread_with_no_established_law_cannot_be_drafted_from():
    """Nothing to cite means the drafter would have to invent law."""
    from legal_ai.drafting.source import thread_authorities
    from api.threads.repository import list_messages

    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "hello")
        messages = list_messages(conn, thread.thread_id, USER)

    assert thread_authorities(messages) == set()


def test_the_filename_comes_from_what_the_reader_asked():
    assert controller._filename(
        "NOTICE UNDER SECTION 138", "Verma v. Malhotra"
    ) == "notice_under_section_138.docx"


def test_an_untitled_thread_still_names_its_file():
    assert controller._filename("", "Verma v. Malhotra").startswith("verma")
    assert controller._filename("", "").endswith(".docx")
