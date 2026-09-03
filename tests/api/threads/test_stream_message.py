"""The lede streams ahead of `done`, in pieces -- but only once it is final.

Not raw model tokens: the lede is already past verification by the time
these events fire, because verification is what can still move a claim
between buckets. Streaming the analyst's own generation would show a
reader prose that verification might go on to contradict, which is the
exact false reassurance the three-state pattern exists to prevent.

Chunking the finished answer instead gets most of the same perceived-speed
win -- literature puts it at ~40% faster *felt* even at identical
wall-clock time, because the reader starts on the lede before the rest of
the pane (claims, sources) has rendered. See docs/SPEED_2026_09_03.md #1.
"""

from __future__ import annotations

import pytest

from api.threads import controller as thread_controller
from api.threads.repository import create_thread, ensure_thread_schema
from api.databases.postgres import connection
from legal_ai.conversation.router import Route
from legal_ai.schemas.answer import DraftAnswer

USER = "test-user-stream"


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


def test_chunk_words_concatenates_back_to_the_original():
    lede = "Anticipatory bail is granted by the High Court or the Court of Session."
    chunks = thread_controller._chunk_words(lede)
    assert len(chunks) > 1
    assert "".join(chunks).strip() == lede


def test_chunk_words_handles_a_single_word():
    assert thread_controller._chunk_words("Hello.") == ["Hello. "]


def _fake_research_with_progress(lede: str):
    async def fake(inputs):
        yield "step", "research"
        yield "done", {
            "answer": f"{lede}\n\n- claim [doc-1]",
            "draft_answer": DraftAnswer(question="q", lede=lede),
        }

    return fake


@pytest.mark.asyncio
async def test_answer_chunks_arrive_before_done_and_concatenate_to_the_lede(monkeypatch):
    lede = "Anticipatory bail may be granted after the court weighs several factors."
    import api.threads.graph as graph_module

    monkeypatch.setattr(graph_module, "research_with_progress", _fake_research_with_progress(lede))
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(thread_controller, "classify", lambda *a, **k: __import__(
        "legal_ai.conversation.intent", fromlist=["Intent"]
    ).Intent.LEGAL)

    with connection() as conn:
        thread = create_thread(conn, USER)
        events = [
            (kind, payload)
            async for kind, payload in thread_controller.stream_message(
                conn, USER, thread.thread_id, "when is anticipatory bail granted"
            )
        ]

    kinds = [kind for kind, _ in events]
    assert "answer_chunk" in kinds
    assert kinds.index("answer_chunk") < kinds.index("done")
    # Every answer_chunk precedes done -- none trail it.
    assert kinds[kinds.index("done") :] == ["done"]

    rebuilt = "".join(
        payload["text"] for kind, payload in events if kind == "answer_chunk"
    ).strip()
    assert rebuilt == lede


@pytest.mark.asyncio
async def test_no_lede_means_no_chunk_events(monkeypatch):
    """A clarification or an empty draft has nothing to stream -- the
    absence of chunks must not be mistaken for a stall."""
    import api.threads.graph as graph_module

    async def fake(inputs):
        yield "done", {"answer": None, "draft_answer": None, "clarification_needed": "Which state?"}

    monkeypatch.setattr(graph_module, "research_with_progress", fake)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)

    with connection() as conn:
        thread = create_thread(conn, USER)
        events = [
            (kind, payload)
            async for kind, payload in thread_controller.stream_message(
                conn, USER, thread.thread_id, "what about my case"
            )
        ]

    assert all(kind != "answer_chunk" for kind, _ in events)


# --- the question survives a disconnect ------------------------------------
#
# Reproduced live 2026-09-03: refreshing mid-research showed "Ask your
# first question below" -- the question itself was gone, not just its
# answer, because nothing was written to the thread until the whole run
# finished. A disconnect anywhere in a 30-130s run lost it outright.


@pytest.mark.asyncio
async def test_the_question_is_stored_even_if_the_stream_is_abandoned(monkeypatch):
    """Simulates a client disconnect: the generator is closed after the
    first step, before research ever reaches "done". The question must
    already be in the thread by then."""
    import api.threads.graph as graph_module
    from api.threads.repository import list_messages

    async def hangs_after_one_step(inputs):
        yield "step", "research"
        # A real disconnect would end the generator here via GeneratorExit,
        # well before "done". Emulated by simply never yielding it.

    monkeypatch.setattr(graph_module, "research_with_progress", hangs_after_one_step)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)

    with connection() as conn:
        thread = create_thread(conn, USER)
        gen = thread_controller.stream_message(
            conn, USER, thread.thread_id, "what is section 420"
        )
        await anext(gen)  # consumes the "step" event; nothing past it exists
        await gen.aclose()  # the disconnect

        stored = list_messages(conn, thread.thread_id, USER)

    assert len(stored) == 1
    assert stored[0].role == "user"
    assert stored[0].content == "what is section 420"


@pytest.mark.asyncio
async def test_a_timed_out_run_still_leaves_the_question_behind(monkeypatch):
    import api.threads.graph as graph_module
    from api.threads.repository import list_messages

    async def times_out(inputs):
        yield "timeout", TimeoutError()

    monkeypatch.setattr(graph_module, "research_with_progress", times_out)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)

    with connection() as conn:
        thread = create_thread(conn, USER)
        events = [
            (kind, payload)
            async for kind, payload in thread_controller.stream_message(
                conn, USER, thread.thread_id, "what is anticipatory bail"
            )
        ]
        stored = list_messages(conn, thread.thread_id, USER)

    assert events[-1][0] == "error"
    assert len(stored) == 1
    assert stored[0].role == "user"
    # No assistant row: nothing here for a later rewrite to mistake for an
    # answer that was never actually produced.
    assert all(m.role != "assistant" for m in stored)


@pytest.mark.asyncio
async def test_the_thread_title_is_set_from_the_question_even_if_research_never_finishes(monkeypatch):
    """So History shows what was asked, not the default title, even for a
    turn that never completed."""
    import api.threads.graph as graph_module
    from api.threads.repository import get_thread

    async def hangs(inputs):
        yield "step", "research"

    monkeypatch.setattr(graph_module, "research_with_progress", hangs)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)

    with connection() as conn:
        thread = create_thread(conn, USER)
        gen = thread_controller.stream_message(
            conn, USER, thread.thread_id, "what is the punishment for cheating"
        )
        await anext(gen)
        await gen.aclose()

        reloaded = get_thread(conn, thread.thread_id, USER)

    assert reloaded.title.startswith("what is the punishment for cheating")
