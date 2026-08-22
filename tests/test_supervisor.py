"""Milestone 7.2 -- decompose, fan out, merge.

The claim under test: there is no split-versus-single mode. The supervisor
emits a list of angles, and a list of one IS the single-agent case.
"""

from datetime import datetime, timezone

from legal_ai.agents import supervisor as sup
from legal_ai.agents.research import ResearchResult
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef


def _evidence(doc_id):
    return Evidence(
        content="text",
        document_id=doc_id,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


def _finding(angle, ids):
    return ResearchResult(angle=angle, summary=f"summary of {angle}",
                          evidence=[_evidence(i) for i in ids], rounds=1)


# ------------------------------------------------------------- decompose

def test_decompose_returns_the_model_angles(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["RERA refund", "consumer forum"]')
    assert sup.decompose("builder is late", max_angles=3) == ["RERA refund", "consumer forum"]


def test_decompose_enforces_the_cap_even_if_the_model_ignores_it(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["a", "b", "c", "d", "e"]')
    assert len(sup.decompose("q", max_angles=2)) == 2


def test_decompose_falls_back_to_the_question_on_garbage(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: "I cannot help with that")
    assert sup.decompose("what is theft", max_angles=3) == ["what is theft"]


def test_decompose_falls_back_when_the_model_fails(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: (_ for _ in ()).throw(RuntimeError("429")))
    assert sup.decompose("what is theft", max_angles=3) == ["what is theft"]


def test_decompose_drops_non_string_entries(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["real angle", 42, null]'.replace("null", "null"))
    assert sup.decompose("q", max_angles=3) == ["real angle"]


def test_decompose_handles_a_fenced_block(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '```json\n["one angle"]\n```')
    assert sup.decompose("q", max_angles=3) == ["one angle"]


# ---------------------------------------------------------------- fan-out

def test_a_single_angle_question_spawns_exactly_one_agent(monkeypatch):
    # A lookup must not spawn three agents. This is the cost regression the
    # harness watches.
    monkeypatch.setattr(sup, "generate", lambda p: '["what is the punishment for murder"]')
    monkeypatch.setattr(sup, "research_angle",
                        lambda angle, **kw: _finding(angle, ["act:20062:sec-103"]))
    result = sup.supervise("what is the punishment for murder")
    assert result.agents_spawned == 1


def test_a_multi_angle_question_spawns_one_agent_per_angle(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["refund", "forum", "limitation"]')
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: _finding(angle, [f"act:1:sec-{angle}"]))
    result = sup.supervise("builder is late")
    assert result.agents_spawned == 3
    assert result.angles == ["refund", "forum", "limitation"]


def test_the_angle_cap_bounds_the_fan_out(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["a", "b", "c", "d", "e", "f"]')
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: _finding(angle, [f"x:{angle}"]))
    assert sup.supervise("q", max_angles=2).agents_spawned == 2


# ----------------------------------------------------------------- merge

def test_merge_interleaves_angles_so_no_angle_is_crowded_out(monkeypatch):
    # Each angle's list is ranked against ITS OWN angle. Concatenating would
    # bury the second angle's best result beneath the first angle's worst.
    monkeypatch.setattr(sup, "generate", lambda p: '["one", "two"]')
    findings = {
        "one": _finding("one", ["a1", "a2", "a3"]),
        "two": _finding("two", ["b1", "b2"]),
    }
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: findings[angle])
    ids = [e.document_id for e in sup.supervise("q").evidence]
    assert ids[:2] == ["a1", "b1"]


def test_merge_deduplicates_across_angles(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["one", "two"]')
    findings = {"one": _finding("one", ["same", "a2"]), "two": _finding("two", ["same", "b2"])}
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: findings[angle])
    ids = [e.document_id for e in sup.supervise("q").evidence]
    assert ids.count("same") == 1


def test_findings_keep_their_own_summaries(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["refund", "forum"]')
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: _finding(angle, [f"x:{angle}"]))
    result = sup.supervise("q")
    assert {f.summary for f in result.findings} == {"summary of refund", "summary of forum"}


def test_a_question_with_no_findings_still_returns_a_result(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p: '["only angle"]')
    monkeypatch.setattr(sup, "research_angle", lambda angle, **kw: _finding(angle, []))
    result = sup.supervise("q")
    assert result.evidence == []
    assert result.agents_spawned == 1
