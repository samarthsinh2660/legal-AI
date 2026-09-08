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


def test_there_is_no_reason_to_stop_until_there_is():
    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
        assert job._stop_reason(claimed["run_id"]) is None
        conn.execute("DELETE FROM threads WHERE user_id = %s", (USER,))
        conn.commit()
        assert "deleted" in job._stop_reason(claimed["run_id"])


def test_a_cancelled_run_is_its_own_reason_to_stop():
    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
        runs.cancel(conn, claimed["run_id"], USER)
        assert "cancelled" in job._stop_reason(claimed["run_id"])


# --- stopping, and saying you are alive ------------------------------------
#
# The worker already pauses between nodes to check the run still exists.
# That one seam carries everything Phase 4 needs: a beat so the reaper can
# tell working from dead, and a cancel check so a reader who left stops
# being charged. Neither can live anywhere else -- a synchronous graph
# offers no other place to interrupt it.


def test_a_cancelled_run_stops_at_the_next_node(monkeypatch):
    _researches(monkeypatch)
    reached = []

    def three_nodes(inputs):
        yield "step", "context_builder"
        reached.append("context_builder")
        with connection() as conn:
            runs.cancel(conn, CANCELLED["run_id"], USER)
        yield "step", "research"
        reached.append("research")
        yield "done", {"answer": "should never be stored", "draft_answer": None}

    monkeypatch.setattr(job, "stream_graph", three_nodes)

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is section 138")
    CANCELLED.update(claimed)
    job.run(claimed)

    # It got as far as the node that cancelled it, and stopped before the
    # next one produced anything.
    assert reached == ["context_builder"]
    with connection() as conn:
        assert runs.get(conn, claimed["run_id"], USER)["status"] == "cancelled"
        assert [m.role for m in list_messages(conn, thread_id, USER)] == ["user"]


CANCELLED: dict = {}


def test_a_running_job_beats_between_nodes(monkeypatch):
    """The reaper tells a working run from an abandoned one by this and
    nothing else."""
    _researches(monkeypatch)
    beats = []

    def beat(_conn, run_id):
        beats.append(run_id)
        return "running"      # the status the worker carries on for

    monkeypatch.setattr(job.runs, "beat", beat)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(
        ("step", "context_builder"), ("step", "research"), ("step", "analyst"),
    ))

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    assert beats.count(claimed["run_id"]) >= 3


def test_a_cancelled_run_writes_no_answer_even_if_the_graph_finished(monkeypatch):
    """The graph returns whatever it returns; the decision not to store it
    is the worker's, and has to hold at the last moment too."""
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering("A lede."))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is section 138")
        runs.cancel(conn, claimed["run_id"], USER)
    job.run(claimed)

    with connection() as conn:
        assert [m.role for m in list_messages(conn, thread_id, USER)] == ["user"]


# --- a requeued run must not answer twice ----------------------------------
#
# The reaper can only guess. A worker deep in a model call and a worker that
# died look identical from the outside, so a run will occasionally be
# requeued while the first worker is still alive -- and then two workers
# finish the same question. Two assistant messages is the visible half; the
# real damage is _remember(), because duplicated case findings are wrong
# data that the next question is seeded with.


def test_only_the_first_worker_to_finish_stores_an_answer(monkeypatch):
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering("A lede."))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is section 138")

    job.run(claimed)                      # the worker that was thought dead
    job.run(dict(claimed))                # the one it was requeued to

    with connection() as conn:
        stored = list_messages(conn, thread_id, USER)

    assert [m.role for m in stored] == ["user", "assistant"]


def test_the_second_finisher_leaves_the_first_answer_alone(monkeypatch):
    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _answering("The first answer."))

    with connection() as conn:
        thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    monkeypatch.setattr(job, "stream_graph", _answering("A different answer."))
    job.run(dict(claimed))

    with connection() as conn:
        stored = list_messages(conn, thread_id, USER)

    assert "The first answer." in stored[1].content
    assert "A different answer." not in stored[1].content


# --- a retry does not buy the search twice ---------------------------------


def test_a_run_saves_what_it_found_so_a_retry_need_not_search_again(monkeypatch):
    from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
    from datetime import datetime, timezone

    found = [Evidence(
        document_id="act:2189:sec-138", document_type="act", title="s.138",
        content="Dishonour of cheque.",
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            licence="Government of India", attribution_required=False),
    )]

    _researches(monkeypatch)
    monkeypatch.setattr(job, "stream_graph", _graph_yielding(
        ("step", "research"),
        ("findings", found),
        ("done", {"answer": "text", "draft_answer": None}),
    ))

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    with connection() as conn:
        restored = runs.restore_findings(conn, claimed["run_id"])
    assert [e.document_id for e in restored] == ["act:2189:sec-138"]


def test_a_retried_run_hands_the_graph_what_the_last_attempt_found(monkeypatch):
    """The whole point: the second worker starts from the evidence rather
    than from the search."""
    from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
    from datetime import datetime, timezone

    found = [Evidence(
        document_id="act:2189:sec-138", document_type="act", title="s.138",
        content="Dishonour of cheque.",
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            licence="Government of India", attribution_required=False),
    )]

    _researches(monkeypatch)
    seen = {}

    def capture(inputs):
        seen["findings"] = inputs.get("findings")
        yield "done", {"answer": "text", "draft_answer": None}

    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
        runs.save_findings(conn, claimed["run_id"], found)

    monkeypatch.setattr(job, "stream_graph", capture)
    job.run(claimed)

    assert [e.document_id for e in (seen["findings"] or [])] == ["act:2189:sec-138"]


def test_a_first_attempt_hands_the_graph_nothing(monkeypatch):
    """A fresh run must search. Seeding it with an empty list would be the
    same shape as seeding it with results."""
    _researches(monkeypatch)
    seen = {}

    def capture(inputs):
        seen["findings"] = inputs.get("findings")
        yield "done", {"answer": "text", "draft_answer": None}

    monkeypatch.setattr(job, "stream_graph", capture)
    with connection() as conn:
        _thread_id, claimed = _ask(conn, "what is section 138")
    job.run(claimed)

    assert not seen["findings"]
