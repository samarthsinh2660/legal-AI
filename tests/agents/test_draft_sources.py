"""Every citation reaches the reader with a way to open it.

A lawyer must be able to click through and read the provision before
relying on it. We store the source URL on every document and the answer
carried only the opaque id.

The archive case is the reason `openable` exists: Supreme Court and High
Court judgments came from bundled year tars, so their stored URL is a
several-hundred-megabyte download, not the judgment. Offering that as
"open this" would be worse than offering nothing.
"""

from datetime import datetime, timezone

from legal_ai.agents.draft import build_answer
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _evidence(document_id: str, url: str, **kw) -> Evidence:
    return Evidence(
        content="text",
        document_id=document_id,
        title=kw.get("title", "A title"),
        document_type=kw.get("document_type", "section"),
        court=kw.get("court"),
        citation=kw.get("citation"),
        provenance=Provenance(
            source=SourceRef(name="src", url=url, source_type="primary"),
            retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


def _analysis(*ids: str) -> AnalysisResult:
    return AnalysisResult(
        lede="x", claims=(Claim(text="a claim", evidence_ids=tuple(ids)),)
    )


def test_a_statute_carries_its_source_url():
    answer = build_answer(
        "q",
        _analysis("act:2189:sec-138"),
        [_evidence("act:2189:sec-138", "https://indiacode.gov.in/handle/123456789/535860")],
    )
    source = next(s for s in answer.sources if s.document_id == "act:2189:sec-138")
    assert source.openable
    assert "indiacode.gov.in" in source.url


def test_an_indian_kanoon_judgment_carries_its_own_page():
    answer = build_answer(
        "q",
        _analysis("judgment:ik-1843699"),
        [_evidence("judgment:ik-1843699", "https://indiankanoon.org/doc/1843699/",
                   document_type="judgment")],
    )
    assert answer.sources[0].openable


def test_a_bundled_archive_is_not_offered_as_a_link():
    """The stored URL is a year tar. Handing a reader a 484MB download and
    calling it the judgment is worse than admitting we have no link."""
    answer = build_answer(
        "q",
        _analysis("judgment:escr010000722020"),
        [_evidence(
            "judgment:escr010000722020",
            "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/tar/year=2020/english/english.tar",
            document_type="judgment",
            citation="[2020] 8 S.C.R. 1057",
        )],
    )
    source = answer.sources[0]
    assert not source.openable
    # The citation is what the reader uses instead, so it must be there.
    assert source.citation == "[2020] 8 S.C.R. 1057"


def test_sources_cover_every_cited_id_and_nothing_else():
    evidence = [
        _evidence("act:1:sec-1", "https://www.indiacode.nic.in/handle/1"),
        _evidence("act:2:sec-2", "https://www.indiacode.nic.in/handle/2"),
    ]
    answer = build_answer("q", _analysis("act:1:sec-1"), evidence)

    assert [s.document_id for s in answer.sources] == ["act:1:sec-1"]


def test_a_source_carries_what_the_panel_renders():
    answer = build_answer(
        "q",
        _analysis("judgment:x"),
        [_evidence("judgment:x", "https://indiankanoon.org/doc/1/",
                   document_type="judgment", title="A v. B",
                   court="Supreme Court of India", citation="[2020] 1 SCR 1")],
    )
    source = answer.sources[0]
    assert (source.title, source.court) == ("A v. B", "Supreme Court of India")


def test_a_url_on_the_migrated_india_code_host_is_not_offered():
    """India Code moved to indiacode.gov.in and renumbered every handle, so
    the stored nic.in URLs 404. A link to an error page is worse than none;
    the reader gets the title and citation instead."""
    answer = build_answer(
        "q",
        _analysis("act:2189:sec-138"),
        [_evidence(
            "act:2189:sec-138",
            "https://www.indiacode.nic.in/handle/123456789/2189?view_type=browse",
            title="Dishonour of cheque",
        )],
    )
    source = answer.sources[0]
    assert not source.openable
    assert source.title == "Dishonour of cheque"


def test_a_live_india_code_url_is_still_offered():
    answer = build_answer(
        "q",
        _analysis("act:1:sec-1"),
        [_evidence("act:1:sec-1", "https://indiacode.gov.in/handle/123456789/535860")],
    )
    assert answer.sources[0].openable
