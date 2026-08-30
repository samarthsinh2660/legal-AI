from datetime import date

from legal_ai.context.builder import build_thread_context
from legal_ai.context.clarification import (
    DATE_QUESTION,
    STATE_QUESTION,
    clarification_needed,
)
from legal_ai.context.models import DocumentFacts
from legal_ai.graph.build import build_research_graph


def test_a_state_wise_question_without_a_state_asks():
    ctx = build_thread_context("the builder has not given possession of my flat")
    assert clarification_needed(ctx) == STATE_QUESTION


def test_the_same_question_with_a_state_does_not_ask():
    ctx = build_thread_context("the builder in Gujarat has not given possession")
    assert clarification_needed(ctx) is None


def test_a_state_supplied_by_an_uploaded_document_satisfies_the_gate():
    # The question rarely names the state; the petition does.
    facts = DocumentFacts(document_id="d1", issues=("possession dispute in Gujarat",))
    ctx = build_thread_context("the builder has not given possession", documents=(facts,))
    assert clarification_needed(ctx) is None


def test_a_question_that_is_not_state_wise_does_not_ask():
    # Criminal law is central. Asking here is the nagging that trains users
    # to ignore the prompt.
    assert clarification_needed(build_thread_context("what is the punishment for murder")) is None
    assert clarification_needed(build_thread_context("what is criminal breach of trust")) is None


def test_a_limitation_question_without_a_date_asks():
    ctx = build_thread_context("how long do i have to file this claim")
    assert clarification_needed(ctx) == DATE_QUESTION


def test_a_limitation_question_with_a_date_does_not_ask():
    ctx = build_thread_context("how long do i have to file this claim")
    ctx = type(ctx)(**{**ctx.__dict__, "relevant_date_from": date(2021, 6, 30)})
    assert clarification_needed(ctx) is None


def test_only_one_question_is_asked_even_when_two_gaps_exist():
    # A gate that asks everything at once is a form, and forms get abandoned.
    ctx = build_thread_context("how long do i have to sue the builder over possession")
    assert clarification_needed(ctx) == STATE_QUESTION


def test_the_graph_halts_before_research_when_clarification_is_needed():
    result = build_research_graph().invoke(
        {"question": "the builder has not given possession of my flat"}
    )
    assert result["clarification_needed"] == STATE_QUESTION
    assert result.get("answer") is None
    assert "research_rounds" not in result


def test_the_graph_proceeds_to_an_answer_when_nothing_is_blocking():
    result = build_research_graph().invoke({"question": "what is the punishment for murder"})
    assert result["clarification_needed"] is None
    assert result["answer"]
