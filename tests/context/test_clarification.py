from datetime import date

import pytest

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


def test_answering_the_date_question_actually_satisfies_the_gate():
    """The end-to-end path a real second turn takes: the answer folded into
    a self-contained question by the rewriter, not a hand-built context.
    This is the exact case that looped forever before 2026-09-04 -- every
    phrasing of the date satisfied nothing, because build_thread_context
    never wrote relevant_date_from at all."""
    first = build_thread_context(
        "What is the limitation period for filing a suit for recovery of money?"
    )
    assert clarification_needed(first) == DATE_QUESTION

    rewritten = build_thread_context(
        "What is the limitation period for filing a suit for recovery of "
        "money? The debt was due on 1 January 2022 and has not been repaid."
    )
    assert clarification_needed(rewritten) is None


def test_a_date_supplied_a_second_way_also_satisfies_the_gate():
    rewritten = build_thread_context(
        "What is the limitation period for filing a suit for recovery of "
        "money? The cause of action arose on 1 January 2022."
    )
    assert clarification_needed(rewritten) is None


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


# --- the state gate must be answerable from any state -----------------------
#
# Reported from the live deploy: a user in Uttarakhand answered "my state is
# uttarakhand" and was asked the identical question again, without end. The
# table held eight states, and the gate re-asks while jurisdiction.state is
# unset. The earlier QA pass had cleared this gate after testing Maharashtra,
# which is one of the eight that worked.


@pytest.mark.parametrize(
    "state",
    [
        "Uttarakhand", "Uttar Pradesh", "Bihar", "Punjab", "Haryana",
        "Madhya Pradesh", "Odisha", "Telangana", "Assam", "Goa", "Jharkhand",
        "Chhattisgarh", "Himachal Pradesh", "Tripura", "Sikkim", "Manipur",
        "Meghalaya", "Nagaland", "Mizoram", "Arunachal Pradesh",
        "Andhra Pradesh", "Jammu and Kashmir", "Ladakh", "Puducherry",
        "Chandigarh", "Maharashtra", "Kerala", "Gujarat", "Karnataka",
        "Tamil Nadu", "West Bengal", "Rajasthan", "Delhi",
    ],
)
def test_naming_any_state_answers_the_state_question(state):
    from legal_ai.context.builder import build_thread_context

    context = build_thread_context(f"mutation of my land in {state}")

    assert context.jurisdiction.state is not None, state
    assert context.jurisdiction.court is not None, state
    assert clarification_needed(context) is None, state


def test_a_state_name_is_not_matched_inside_a_longer_word():
    """"goa" sits inside "Goalpara", which is in Assam."""
    from legal_ai.context.builder import build_thread_context

    context = build_thread_context("mutation of my land in Goalpara district")

    assert context.jurisdiction.state != "Goa"


def test_the_state_name_is_rendered_as_it_is_written():
    from legal_ai.context.builder import build_thread_context

    context = build_thread_context("rent dispute in Jammu and Kashmir")

    assert context.jurisdiction.state == "Jammu and Kashmir"

