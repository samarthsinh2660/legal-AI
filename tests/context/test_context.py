from datetime import date

from legal_ai.context.builder import (
    attach_case,
    build_thread_context,
    promote_finding,
    revise,
    to_filters,
)
from legal_ai.context.models import EstablishedFinding, ThreadContext
from legal_ai.context.serialization import render


def _finding(claim="RERA s.18 allows refund", depends_on=("jurisdiction",)):
    return EstablishedFinding(
        claim=claim, evidence_ids=("act:2158:sec-18",), depends_on=depends_on
    )


def test_build_starts_at_revision_one_with_no_case():
    ctx = build_thread_context("what is the punishment for murder")
    assert ctx.revision == 1
    assert ctx.case_id is None
    assert ctx.established_findings == ()


def test_build_extracts_state_and_its_high_court():
    ctx = build_thread_context("builder in Gujarat has not given possession")
    assert ctx.jurisdiction.state == "Gujarat"
    assert ctx.jurisdiction.court == "Gujarat High Court"


def test_build_leaves_jurisdiction_unset_rather_than_guessing():
    ctx = build_thread_context("what is the punishment for murder")
    assert ctx.jurisdiction.court is None
    assert ctx.jurisdiction.state is None


def test_build_flags_questions_asking_for_the_current_position():
    assert build_thread_context("is section 66A still good law").needs_current_law


# --- relevant_date_from --------------------------------------------------
#
# Until 2026-09-04 this field had no writer anywhere: declared on
# ThreadContext, read by the clarification gate, never assigned. A
# limitation-period question therefore asked "when did this happen?" and,
# whatever the reader answered, asked it again -- forever, since the field
# that would have satisfied the gate never moved off None. Reproduced live
# on the deployed app, thread 56545ff6, three different phrasings of the
# same date, three identical repeats of the question.


def test_build_extracts_a_date_from_the_question():
    ctx = build_thread_context(
        "The debt was due on 1 January 2022 and has not been repaid."
    )
    assert ctx.relevant_date_from == date(2022, 1, 1)


def test_build_leaves_the_date_unset_when_the_question_names_none():
    ctx = build_thread_context("what is the punishment for murder")
    assert ctx.relevant_date_from is None


def test_a_rewritten_follow_up_carries_the_date_through():
    # rewrite_question folds a follow-up answer into a self-contained
    # question -- this is what the graph actually sees on a second turn,
    # not the bare "1 January 2022" the reader typed.
    ctx = build_thread_context(
        "What is the limitation period for filing a suit for recovery of "
        "money? The debt was due on 1 January 2022 and has not been repaid."
    )
    assert ctx.relevant_date_from == date(2022, 1, 1)
    assert build_thread_context("what is the current position on bail").needs_current_law
    assert not build_thread_context("what is the punishment for theft").needs_current_law


def test_jurisdiction_reaches_the_retrieval_filters():
    # Phase 2 shipped MetadataFilters.court and nothing populated it.
    ctx = build_thread_context("possession delay in Gujarat")
    assert to_filters(ctx).court == "Gujarat High Court"


def test_relevant_period_reaches_the_retrieval_filters():
    ctx = ThreadContext(
        question="q",
        relevant_date_from=date(2016, 1, 1),
        relevant_date_to=date(2020, 12, 31),
    )
    filters = to_filters(ctx)
    assert filters.decision_date_from == date(2016, 1, 1)
    assert filters.decision_date_to == date(2020, 12, 31)


def test_promoting_a_finding_bumps_the_revision():
    ctx = build_thread_context("q")
    promoted = promote_finding(ctx, _finding())
    assert promoted.revision == ctx.revision + 1
    assert len(promoted.established_findings) == 1


def test_context_is_immutable_so_history_stays_reconstructable():
    ctx = build_thread_context("q")
    promote_finding(ctx, _finding())
    assert ctx.established_findings == ()


def test_revising_a_field_drops_findings_that_depended_on_it():
    ctx = promote_finding(build_thread_context("q"), _finding(depends_on=("jurisdiction",)))
    revised = revise(ctx, jurisdiction=type(ctx.jurisdiction)(court="Bombay High Court"))
    assert revised.established_findings == ()


def test_revising_a_field_keeps_findings_that_did_not_depend_on_it():
    ctx = promote_finding(build_thread_context("q"), _finding(depends_on=("case_id",)))
    revised = revise(ctx, jurisdiction=type(ctx.jurisdiction)(court="Bombay High Court"))
    assert len(revised.established_findings) == 1


def test_revising_with_no_actual_change_is_a_no_op():
    ctx = build_thread_context("q")
    assert revise(ctx, case_id=None) is ctx


def test_attaching_a_case_seeds_the_thread_with_its_findings():
    ctx = build_thread_context("what are my options")
    case_finding = _finding(claim="possession was due in March 2021")
    attached = attach_case(ctx, "case-patel-v-shah", (case_finding,))
    assert attached.case_id == "case-patel-v-shah"
    assert case_finding in attached.established_findings


def test_attaching_a_case_does_not_duplicate_a_finding_already_present():
    shared = _finding()
    ctx = promote_finding(build_thread_context("q"), shared)
    attached = attach_case(ctx, "case-1", (shared,))
    assert len(attached.established_findings) == 1


def test_a_thread_can_stay_unattached():
    # A student researching a doctrine never needs a case.
    ctx = build_thread_context("what is the doctrine of frustration")
    assert ctx.case_id is None


def test_render_omits_empty_fields():
    rendered = render(build_thread_context("what is the punishment for murder"))
    assert "Question:" in rendered
    assert "None" not in rendered
    assert "Court:" not in rendered


def test_render_includes_jurisdiction_and_findings():
    ctx = promote_finding(build_thread_context("possession delay in Gujarat"), _finding())
    rendered = render(ctx)
    assert "Gujarat High Court" in rendered
    assert "act:2158:sec-18" in rendered


def test_render_caps_findings_so_a_long_thread_cannot_grow_its_own_prompt():
    ctx = build_thread_context("q")
    for i in range(25):
        ctx = promote_finding(ctx, _finding(claim=f"finding {i}"))
    rendered = render(ctx)
    assert "finding 24" in rendered
    assert "finding 0" not in rendered
    assert "15 earlier omitted" in rendered


# --- document facts in the rendered context (Phase 4) ---

def test_document_facts_reach_the_rendered_context():
    # The researcher was being told the jurisdiction the documents implied
    # but never what the documents actually said, so a petition pleading
    # Section 18 and a possession date reached the search as nothing.
    from legal_ai.context.models import DocumentFacts
    from legal_ai.context.serialization import render

    facts = DocumentFacts(
        document_id="doc-1",
        document_type="petition",
        dates=("30 June 2021",),
        issues=("possession not handed over",),
        cited_sections=("Section 18 of the Real Estate (Regulation and Development) Act, 2016",),
    )
    rendered = render(build_thread_context("what are my options", "case-1", (facts,)))
    assert "possession not handed over" in rendered
    assert "30 June 2021" in rendered
    assert "Section 18" in rendered
    assert "doc-1" in rendered


def test_rendered_documents_are_capped():
    # This string is carried by every node's prompt and multiplied by the
    # fan-out width, so a hundred-exhibit bundle must not set its size.
    from legal_ai.context.models import DocumentFacts
    from legal_ai.context.serialization import MAX_RENDERED_DOCUMENTS, render

    facts = tuple(
        DocumentFacts(document_id=f"doc-{i}", issues=(f"issue {i}",)) for i in range(40)
    )
    rendered = render(build_thread_context("q", documents=facts))
    assert rendered.count("issue ") == MAX_RENDERED_DOCUMENTS
    assert "32 more not shown" in rendered


def test_a_context_with_no_documents_renders_no_document_section():
    from legal_ai.context.serialization import render

    assert "case documents" not in render(build_thread_context("plain question of law"))
