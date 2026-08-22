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
