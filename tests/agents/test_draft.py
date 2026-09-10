"""The draft renderer: where the verifier's result becomes visible."""

from datetime import datetime, timezone

from legal_ai.agents.draft import build_answer, render
from legal_ai.schemas.answer import AnalysisResult, DraftAnswer
from legal_ai.retrieval.evidence_builder import _location
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _evidence(doc_id, doc_type):
    return Evidence(
        content="text", document_id=doc_id, document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="x", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            licence="GoI", attribution_required=False,
        ),
    )


EVIDENCE = [
    _evidence("act:2158:sec-18", "section"),
    _evidence("judgment:ik-149094324", "judgment"),
]
GROUNDED = Claim("promoter must refund with interest", ("act:2158:sec-18",))
ALSO = Claim("the leading authority is Newtech", ("judgment:ik-149094324",))


def test_no_model_is_involved():
    # The inputs are already structured. Re-rendering them through a model
    # would only give it a chance to drop a citation.
    import inspect

    import legal_ai.agents.draft as draft

    assert "generate" not in inspect.getsource(draft)


def test_supported_claims_become_key_elements():
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE)
    assert answer.key_elements == (GROUNDED,)
    assert answer.needs_verification == ()
    assert answer.is_complete


def test_an_unsupported_claim_is_flagged_not_deleted():
    # A reader who cannot see that something was dropped cannot tell a
    # short answer from an incomplete one.
    answer = build_answer(
        "q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE,
        unsupported=(GROUNDED.text,),
    )
    assert answer.key_elements == ()
    assert answer.needs_verification == (GROUNDED.text,)
    assert not answer.is_complete


def test_a_claim_citing_nothing_is_unsupported_even_without_the_verifier():
    # There is nothing for the verifier to have checked, so it does not
    # need to have run for this to be unsupported.
    answer = build_answer("q", AnalysisResult(claims=(Claim("bare assertion"),)), EVIDENCE)
    assert answer.needs_verification == ("bare assertion",)


def test_law_and_judgments_are_separated():
    # A lawyer uses a provision and an authority differently, so the screen
    # must not blend them into one list.
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED, ALSO)), EVIDENCE)
    assert answer.applicable_law == ("act:2158:sec-18",)
    assert answer.key_judgments == ("judgment:ik-149094324",)


def test_citations_cover_every_supported_claim():
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED, ALSO)), EVIDENCE)
    assert set(answer.citations) == {"act:2158:sec-18", "judgment:ik-149094324"}


def test_an_unsupported_claim_contributes_no_citation():
    # Citing a source for a claim we could not ground would be the worst of
    # both: unverified content wearing a verified-looking reference.
    answer = build_answer(
        "q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE, unsupported=(GROUNDED.text,)
    )
    assert answer.citations == ()


def test_the_disclaimer_is_always_present():
    assert build_answer("q", AnalysisResult(), []).disclaimer
    assert "not legal advice" in build_answer("q", AnalysisResult(), []).disclaimer


def test_rendering_marks_the_unsupported_section():
    """The heading was "Could not be verified", which conflated two states.

    A claim the evidence contradicts and a claim nobody checked are
    different things, and the second is our normal condition against an
    Indian corpus in the crores. They now render under separate headings;
    this covers the finding-against one.
    """
    answer = build_answer(
        "q", AnalysisResult(lede="Short answer.", claims=(GROUNDED, Claim("shaky"))),
        EVIDENCE,
    )
    text = render(answer)
    assert "Short answer." in text
    assert "act:2158:sec-18" in text
    assert "NOT supported by the retrieved sources" in text
    assert "shaky" in text


def test_rendering_an_empty_analysis_still_carries_the_disclaimer():
    assert "not legal advice" in render(build_answer("q", AnalysisResult(), []))


def test_an_out_of_scope_reply_carries_no_legal_disclaimer():
    """There is no legal information in it to disclaim, and the boilerplate
    on "I cannot help with that" reads as a non-sequitur."""
    from legal_ai.agents.analyst import OUT_OF_SCOPE
    from legal_ai.agents.draft import build_answer
    from legal_ai.schemas.answer import AnalysisResult

    answer = build_answer("write me a poem", AnalysisResult(lede=OUT_OF_SCOPE), [])

    assert answer.disclaimer == ""
    assert "not legal advice" not in render(answer).lower()


def test_an_answer_names_a_code_the_corpus_does_not_hold(monkeypatch):
    """A statement about our shelf, like support_not_checked -- not a claim
    about the law, and it must reach the reader.

    The register in retrieval.coverage is empty since the last repealed
    code was ingested, so the note is injected here; what is under test is
    the path from build_answer to render, not the register's contents.
    """
    import legal_ai.agents.draft as draft
    from legal_ai.schemas.answer import AnalysisResult

    monkeypatch.setattr(draft, "coverage_note", lambda q: "We do not hold the Foo Act.")
    answer = draft.build_answer("What does the Foo Act require?", AnalysisResult(lede="x"), [])

    assert "Foo Act" in answer.coverage_note
    assert "Foo Act" in render(answer)


def test_an_answer_about_a_held_act_carries_no_coverage_note():
    from legal_ai.agents.draft import build_answer
    from legal_ai.schemas.answer import AnalysisResult

    answer = build_answer(
        "What does Section 138 of the NI Act require?", AnalysisResult(lede="x"), []
    )
    assert answer.coverage_note == ""


# --- the pinpoint: where in the document the cited passage sits -----------


def _located(doc_id, doc_type, *labels):
    item = _evidence(doc_id, doc_type)
    return item.model_copy(update={"location": _location(*labels)})


def test_a_numbered_marker_is_cited_as_a_paragraph():
    evidence = [_located("judgment:ik-1", "judgment", "42")]
    answer = build_answer(
        "q", AnalysisResult(claims=(Claim("held", ("judgment:ik-1",)),)), evidence
    )
    assert answer.sources[0].pinpoint == "para 42"


def test_every_paragraph_the_extract_covers_is_cited():
    # The extract is up to three passages and they need not be adjacent.
    # Naming only the first sends a reader to paragraph 42 for a statement
    # the extract took from paragraph 58.
    evidence = [_located("judgment:ik-1", "judgment", "42", "58")]
    answer = build_answer(
        "q", AnalysisResult(claims=(Claim("held", ("judgment:ik-1",)),)), evidence
    )
    assert answer.sources[0].pinpoint == "paras 42, 58"


def test_a_statutory_marker_is_repeated_as_the_statute_writes_it():
    # "(1)" is a sub-section, not paragraph 1. Rendering it as a paragraph
    # would name a position the Act does not have.
    evidence = [_located("act:2158:sec-18", "section", "(1)")]
    answer = build_answer(
        "q", AnalysisResult(claims=(Claim("refund", ("act:2158:sec-18",)),)), evidence
    )
    assert answer.sources[0].pinpoint == "(1)"


def test_a_mixed_extract_keeps_both_markers_raw():
    evidence = [_located("act:2158:sec-18", "section", "(1)", "2")]
    answer = build_answer(
        "q", AnalysisResult(claims=(Claim("refund", ("act:2158:sec-18",)),)), evidence
    )
    assert answer.sources[0].pinpoint == "(1), 2"


def test_a_source_with_no_marker_has_no_pinpoint():
    # A short section is carried whole and given no location. The whole
    # section is in front of the reader, so no part of it is the citation --
    # and a pinpoint we do not have must never be invented.
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE)
    assert answer.sources[0].pinpoint is None


def test_the_plain_text_rendering_carries_the_pinpoint():
    evidence = [_located("judgment:ik-1", "judgment", "42")]
    answer = build_answer(
        "q", AnalysisResult(claims=(Claim("held", ("judgment:ik-1",)),)), evidence
    )
    assert "Sources: judgment:ik-1 para 42" in render(answer)


def test_the_plain_text_rendering_omits_a_pinpoint_it_does_not_have():
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE)
    assert "Sources: act:2158:sec-18" in render(answer)


def test_sources_are_separated_so_a_multi_paragraph_pinpoint_stays_one_source():
    # "a, b para 42, 43" reads as four sources. The separator has to be
    # something a pinpoint cannot contain.
    evidence = [_located("judgment:ik-1", "judgment", "42", "43"),
                _located("judgment:ik-2", "judgment", "9")]
    answer = build_answer("q", AnalysisResult(claims=(
        Claim("first", ("judgment:ik-1",)), Claim("second", ("judgment:ik-2",)),
    )), evidence)
    assert "Sources: judgment:ik-1 paras 42, 43; judgment:ik-2 para 9" in render(answer)


# --- good law: whether a cited judgment still stands -----------------------


def _standing(status, overruled_by=(), checked=()):
    from legal_ai.retrieval.good_law import GoodLawResult
    return GoodLawResult(status, overruled_by=tuple(overruled_by),
                         checked=tuple(checked))


def test_an_overruled_judgment_is_reported_as_doubted():
    from legal_ai.retrieval.good_law import GoodLaw
    answer = build_answer(
        "q", AnalysisResult(claims=(ALSO,)), EVIDENCE,
        good_law={"judgment:ik-149094324": _standing(GoodLaw.DOUBTED, ("judgment:later",))},
    )
    assert [(n.document_id, n.status, n.overruled_by) for n in answer.good_law] == [
        ("judgment:ik-149094324", "DOUBTED", ("judgment:later",))
    ]
    assert answer.good_law[0].is_a_warning


def test_a_clean_judgment_carries_its_denominator():
    # "No negative treatment" without the count reads as a clearance. The
    # number is what makes it a statement about our shelf.
    from legal_ai.retrieval.good_law import GoodLaw
    answer = build_answer(
        "q", AnalysisResult(claims=(ALSO,)), EVIDENCE,
        good_law={"judgment:ik-149094324": _standing(
            GoodLaw.NO_NEGATIVE_TREATMENT, checked=("a", "b", "c", "d"))},
    )
    assert answer.good_law[0].status == "NO_NEGATIVE_TREATMENT"
    assert answer.good_law[0].checked == 4
    assert not answer.good_law[0].is_a_warning


def test_a_judgment_nothing_cites_produces_no_note():
    # NOT_CHECKED is the ordinary state of most of the corpus. A note on
    # every answer is one a reader learns to skip, which would cost the
    # DOUBTED note the only job it has.
    from legal_ai.retrieval.good_law import GoodLaw
    answer = build_answer(
        "q", AnalysisResult(claims=(ALSO,)), EVIDENCE,
        good_law={"judgment:ik-149094324": _standing(GoodLaw.NOT_CHECKED)},
    )
    assert answer.good_law == ()


def test_a_graph_that_is_down_costs_no_note_and_no_answer():
    answer = build_answer("q", AnalysisResult(claims=(ALSO,)), EVIDENCE, good_law={})
    assert answer.good_law == ()
    assert answer.key_elements == (ALSO,)


def test_a_statute_gets_no_standing_note():
    from legal_ai.retrieval.good_law import GoodLaw
    answer = build_answer(
        "q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE,
        good_law={"act:2158:sec-18": _standing(GoodLaw.DOUBTED, ("x",))},
    )
    assert answer.good_law == ()


def test_the_plain_text_rendering_warns_before_the_sources():
    from legal_ai.retrieval.good_law import GoodLaw
    answer = build_answer(
        "q", AnalysisResult(claims=(ALSO,)), EVIDENCE,
        good_law={"judgment:ik-149094324": _standing(GoodLaw.DOUBTED, ("judgment:later",))},
    )
    text = render(answer)
    assert "DOUBTED" in text
    assert text.index("DOUBTED") < text.index("Sources:")
