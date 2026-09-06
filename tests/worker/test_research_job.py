"""What a research job guarantees, whoever is or is not watching.

The properties here were all bought by a live failure. The question must
survive a disconnect, because refreshing mid-research once landed the reader
back on "Ask your first question below". The answer must survive one too,
because the write used to sit at the tail of the SSE generator and a closed
tab discarded an answer the model budget had already been spent on. And a
run that produced nothing must store no assistant row, because an empty one
reads to the next rewrite as an answer that was given.

None of them depend on a reader now: the job runs in the worker and the
reader watches `run_events`. These drive the job directly, which is what
that separation makes possible.
"""

from __future__ import annotations

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.controller import send_message
from api.threads.repository import (
    create_thread,
    ensure_thread_schema,
    get_thread,
    list_messages,
)
from legal_ai.conversation.router import Route
from legal_ai.schemas.answer import DraftAnswer
from worker import research as job

USER = "test-user-worker"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()


def _graph_yielding(*events):
    def fake(inputs):
        yield from events

    return fake


def _answering(lede: str):
    return _graph_yielding(
        ("step", "research"),
        ("done", {
            "answer": f"{lede}\n\n- claim [doc-1]",
            "draft_answer": DraftAnswer(question="q", lede=lede),
        }),
    )


def _researches(monkeypatch):
    """Force the RESEARCH route without a model call."""
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(job, "rewrite_question", lambda q, h, *a, **k: q)


def _ask(conn, message: str) -> tuple[str, dict]:
    """Send a message and claim the job it queued, as a worker would."""
    thread = create_thread(conn, USER)
    send_message(conn, USER, thread.thread_id, message)
    conn.commit()
    claimed = runs.claim(conn, ("research",))
    return thread.thread_id, claimed


# --- the question survives, whatever happens to the run --------------------


def test_the_question_is_stored_before_the_job_is_even_claimed(monkeypatch):
    with connection() as conn:
        thread = create_thread(conn, USER)
        send_message(conn, USER, thread.thread_id, "what is section 420")
        conn.commit()
        stored = list_messages(conn, thread.thread_id, USER)

    assert [message.role for message in stored] == ["user"]
    assert stored[0].content == "what is section 420"


def test_the_title_is_set_from_the_question_before_any_work_happens():
    """So History shows what was asked even for a turn that never finished."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        send_message(conn, USER, thread.thread_id, "what is the punishment for cheating")
        conn.commit()
        reloaded = get_thread(conn, thread.thread_id, USER)

    assert reloaded.title.startswith("what is the punishment for cheating")


def test_a_second_message_is_refused_while_the_first_is_running():
    """Two turns answering one thread would interleave their messages and
    each rewrite the other's follow-up against a history still moving."""
    from api.utils.errors import Failure

    with connection() as conn:
        thread = create_thread(conn, USER)
        send_message(conn, USER, thread.thread_id, "first")
        conn.commit()
        second = send_message(conn, USER, thread.thread_id, "second")

    assert isinstance(second, Failure)
    assert second.code == "run_in_progress"


# --- the answer survives, whoever is watching ------------------------------


def test_the_answer_is_stored_with_nobody_watching(monkeypatch):
    lede = "A complaint may be filed once the fifteen days expire."
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering(lede))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "can my client file a complaint")
    job.run(claimed)

    with connection() as conn:
        stored = list_messages(conn, thread_id, USER)
        run = runs.get(conn, claimed["run_id"], USER)

    assert [message.role for message in stored] == ["user", "assistant"]
    assert lede in stored[1].content
    assert run["status"] == "done"


def test_a_run_that_produced_nothing_stores_no_assistant_row(monkeypatch):
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(("step", "research")))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is section 420")
    job.run(claimed)

    with connection() as conn:
        stored = list_messages(conn, thread_id, USER)

    assert [message.role for message in stored] == ["user"]


def test_a_timed_out_run_leaves_the_question_and_no_answer(monkeypatch):
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(("timeout", None)))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is anticipatory bail")
    job.run(claimed)

    with connection() as conn:
        stored = list_messages(conn, thread_id, USER)
        run = runs.get(conn, claimed["run_id"], USER)

    assert [message.role for message in stored] == ["user"]
    assert run["status"] == "failed"


def test_a_failed_run_closes_its_row_rather_than_saying_running_forever(monkeypatch):
    _researches(monkeypatch)

    def explodes(inputs):
        raise RuntimeError("the graph fell over")
        yield  # pragma: no cover - a generator, never reached

    monkeypatch.setattr(job, "stream_graph", explodes)

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    with connection() as conn:
        run = runs.get(conn, claimed["run_id"], USER)

    assert run["status"] == "failed"


# --- what the watcher sees -------------------------------------------------


def test_every_step_and_the_lede_reach_the_event_log(monkeypatch):
    """The table is the only wire between the worker and the reader now, so
    anything absent from it is invisible to every client."""
    lede = "Anticipatory bail may be granted after the court weighs several factors."
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering(lede))

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "when is anticipatory bail granted")
    job.run(claimed)

    with connection() as conn:
        events = runs.events_after(conn, claimed["run_id"], 0)

    kinds = [event["kind"] for event in events]
    assert kinds[0] == "step"
    assert "answer_chunk" in kinds
    # Every chunk precedes the terminal event -- none trail it.
    assert kinds[-1] == "done"

    rebuilt = "".join(
        event["payload"]["text"] for event in events if event["kind"] == "answer_chunk"
    ).strip()
    assert rebuilt == lede


def test_events_carry_a_dense_sequence_so_a_reconnect_can_resume(monkeypatch):
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering("A short lede."))

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "q")
    job.run(claimed)

    with connection() as conn:
        events = runs.events_after(conn, claimed["run_id"], 0)

    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))


def test_a_clarification_has_no_lede_to_stream(monkeypatch):
    """The absence of chunks must not be mistaken for a stall."""
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(
        ("done", {"answer": None, "draft_answer": None,
                  "clarification_needed": "Which state?"}),
    ))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what about my case")
    job.run(claimed)

    with connection() as conn:
        events = runs.events_after(conn, claimed["run_id"], 0)
        stored = list_messages(conn, thread_id, USER)

    assert all(event["kind"] != "answer_chunk" for event in events)
    # The question the graph halted on is what the reader is shown.
    assert stored[1].content == "Which state?"


# --- chunking ---------------------------------------------------------------


def test_chunk_words_concatenates_back_to_the_original():
    lede = "Anticipatory bail is granted by the High Court or the Court of Session."
    chunks = job._chunk_words(lede)
    assert len(chunks) > 1
    assert "".join(chunks).strip() == lede


def test_chunk_words_handles_a_single_word():
    assert job._chunk_words("Hello.") == ["Hello. "]


# --- history --------------------------------------------------------------


def test_the_worker_reads_the_history_without_the_question_it_is_answering(monkeypatch):
    """The API stores the question and then enqueues, so the rewriter would
    otherwise be handed the very message it is rewriting."""
    seen = {}
    _researches(monkeypatch)

    def capture(question, history, *args, **kwargs):
        seen["history"] = history
        return question

    monkeypatch.setattr(job, "rewrite_question", capture)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(("step", "research")))

    with connection() as conn:
        thread = create_thread(conn, USER)
        send_message(conn, USER, thread.thread_id, "first question")
        conn.commit()
        claimed = runs.claim(conn, ("research",))
    job.run(claimed)

    assert seen["history"] == []


# --- the reader deletes the thread while it is running ---------------------
#
# Deleting a thread cascades its runs and events away. The worker is still
# inside the graph at that point, so every write it makes afterwards is to
# rows that no longer exist. Before this was handled it surfaced as a
# ForeignKeyViolation traceback per step, and the run went on to completion
# at full price with nowhere to store an answer. Seen in QA 2026-09-06.


def test_a_run_whose_thread_was_deleted_stops_instead_of_finishing(monkeypatch):
    _researches(monkeypatch)

    deleted = {"done": False}

    def deletes_midway(inputs):
        yield "step", "context_builder"
        with connection() as conn:
            conn.execute("DELETE FROM threads WHERE user_id = %s", (USER,))
            conn.commit()
        deleted["done"] = True
        yield "step", "research"
        yield "done", {"answer": "should never be stored", "draft_answer": None}

    monkeypatch.setattr(job, "stream_graph", deletes_midway)

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    assert deleted["done"]
    with connection() as conn:
        assert runs.get(conn, claimed["run_id"], USER) is None


def test_a_deleted_run_is_not_reported_as_an_error(monkeypatch):
    """It is the reader's own decision, not a failure to log."""
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(("step", "research")))

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
        conn.execute("DELETE FROM threads WHERE user_id = %s", (USER,))
        conn.commit()

    # The whole assertion: it returns rather than raising.
    job.run(claimed)


def test_abandoned_is_true_only_once_the_run_is_gone():
    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
        assert job._abandoned(claimed["run_id"]) is False
        conn.execute("DELETE FROM threads WHERE user_id = %s", (USER,))
        conn.commit()
        assert job._abandoned(claimed["run_id"]) is True
