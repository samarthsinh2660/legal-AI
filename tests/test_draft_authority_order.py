"""Judgments reach the reader strongest first.

`key_judgments` was sorted by document_id -- alphabetical order over opaque
ids, which is no order at all. On a heavily-litigated provision that puts a
single-judge order the profession ignores above the Constitution Bench that
settled the question, and the reader has no way to tell which is which.

Building the ranking (legal_ai.retrieval.authority) and not rendering it is
the same as not building it.
"""

from datetime import datetime, timezone

from legal_ai.agents.draft import build_answer
from legal_ai.retrieval.authority import Authority
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _evidence(doc_id: str, doc_type: str = "judgment") -> Evidence:
    return Evidence(
        content="x", document_id=doc_id, document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="x", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            licence="GoI", attribution_required=False,
        ),
    )


def _judgment(doc_id: str) -> Evidence:
    return _evidence(doc_id, "judgment")


def _analysis(*ids: str) -> AnalysisResult:
    return AnalysisResult(claims=(Claim("the court held so", tuple(ids)),), lede="Yes.")


def test_judgments_are_ordered_by_authority_not_by_id():
    evidence = [_judgment("judgment:zzz-leading"), _judgment("judgment:aaa-minor")]
    authority = {
        "judgment:zzz-leading": Authority("judgment:zzz-leading", citation_count=40),
        "judgment:aaa-minor": Authority("judgment:aaa-minor", citation_count=1),
    }
    answer = build_answer(
        "q", _analysis("judgment:zzz-leading", "judgment:aaa-minor"),
        evidence, authority=authority,
    )
    assert answer.key_judgments == ("judgment:zzz-leading", "judgment:aaa-minor")


def test_bench_breaks_a_tie_in_the_rendered_order():
    evidence = [_judgment("judgment:small"), _judgment("judgment:bench")]
    authority = {
        "judgment:small": Authority("judgment:small", citation_count=5, bench_size=2),
        "judgment:bench": Authority("judgment:bench", citation_count=5, bench_size=5),
    }
    answer = build_answer(
        "q", _analysis("judgment:small", "judgment:bench"), evidence, authority=authority
    )
    assert answer.key_judgments == ("judgment:bench", "judgment:small")


def test_without_authority_the_order_is_unchanged():
    """No authority data (no graph, or a caller that did not look it up)
    must not crash or reorder -- it falls back to the previous behaviour."""
    evidence = [_judgment("judgment:b"), _judgment("judgment:a")]
    answer = build_answer("q", _analysis("judgment:b", "judgment:a"), evidence)
    assert answer.key_judgments == ("judgment:a", "judgment:b")


def test_a_judgment_missing_from_the_lookup_is_kept():
    """Authority is looked up over the graph, which may not hold every
    retrieved judgment. A gap in the lookup must not silently drop a
    citation from the answer."""
    evidence = [_judgment("judgment:known"), _judgment("judgment:ungraphed")]
    authority = {"judgment:known": Authority("judgment:known", citation_count=9)}
    answer = build_answer(
        "q", _analysis("judgment:known", "judgment:ungraphed"), evidence,
        authority=authority,
    )
    assert set(answer.key_judgments) == {"judgment:known", "judgment:ungraphed"}
    assert answer.key_judgments[0] == "judgment:known"


def test_statutes_are_still_ordered_by_id():
    """Only judgments carry precedential weight; sections do not, and
    reordering them by a citation count would be meaningless."""
    evidence = [_evidence("act:2", "section"), _evidence("act:1", "section")]
    answer = build_answer("q", _analysis("act:2", "act:1"), evidence)
    assert answer.applicable_law == ("act:1", "act:2")
