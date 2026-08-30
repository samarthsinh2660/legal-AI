"""Two model calls per question, whatever the angle count.

An earlier version made five at one angle and thirteen at three: decompose,
then rewrite, plan, assess and compress per angle. Rewrite and plan both
produced a query and decompose produced it a third time.
"""

from datetime import datetime, timezone

from legal_ai.agents import supervisor as sup
from legal_ai.agents.research_plan import Angle, plan_research
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef


def _evidence(doc_id, content="Return of amount and compensation."):
    return Evidence(
        content=content,
        document_id=doc_id,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


# ------------------------------------------------------------- planning

def test_planning_returns_angles_with_statutory_queries(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"refund","query":"promoter fails to give possession return of amount"}]')
    angles = plan_research("builder did not hand over my flat")
    assert angles[0].query == "promoter fails to give possession return of amount"


def test_planning_caps_the_angle_count(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"a","query":"a"},{"angle":"b","query":"b"},{"angle":"c","query":"c"}]')
    assert len(plan_research("q", max_angles=2)) == 2


def test_planning_falls_back_to_the_question_on_garbage(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw: "I cannot help")
    angles = plan_research("what is theft")
    assert angles == [Angle(angle="what is theft", query="what is theft")]


def test_planning_falls_back_when_the_model_fails(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw: (_ for _ in ()).throw(RuntimeError("429")))
    assert plan_research("q")[0].query == "q"


def test_planning_drops_entries_missing_a_query(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"good","query":"real query"},{"angle":"bad"}]')
    assert len(plan_research("q")) == 1


def test_planning_handles_a_fenced_block(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '```json\n[{"angle":"a","query":"statutory phrasing"}]\n```')
    assert plan_research("q")[0].query == "statutory phrasing"


# ---------------------------------------------------------------- calls

def test_a_question_never_costs_more_than_two_model_calls(monkeypatch):
    calls = []
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw: calls.append("plan") or
        '[{"angle":"a","query":"q1"}]')
    monkeypatch.setattr(sup, "generate", lambda p, **kw: calls.append("summarise") or "summary")
    # Long enough to need summarising -- the upper bound of the cost.
    monkeypatch.setattr(sup, "_search",
        lambda q, limit=None, filters=None: [_evidence(f"act:1:sec-{i}", "x" * 600) for i in range(20)])
    monkeypatch.setattr(sup, "_merge", lambda per_angle, limit: [e for a in per_angle for e in a])

    sup.research("q")
    assert calls == ["plan", "summarise"]


def test_three_angles_cost_no_more_than_one_angle(monkeypatch):
    # Cost is per question, not per angle. Fan-out adds searches, not calls.
    calls = []
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw: calls.append("plan") or
        '[{"angle":"a","query":"q1"},{"angle":"b","query":"q2"},{"angle":"c","query":"q3"}]')
    monkeypatch.setattr(sup, "generate", lambda p, **kw: calls.append("summarise") or "s")
    monkeypatch.setattr(sup, "_search", lambda q, limit, filters=None: [_evidence(f"act:1:sec-{q}", "short")])
    monkeypatch.setattr(sup, "_merge", lambda per_angle, limit: [e for a in per_angle for e in a])

    result = sup.research("q")
    assert result.agents_spawned == 3
    assert calls == ["plan"]


# ------------------------------------------------------------- searching

def test_every_angle_is_searched(monkeypatch):
    searched = []
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"a","query":"first"},{"angle":"b","query":"second"}]')
    monkeypatch.setattr(sup, "generate", lambda p, **kw: "s")
    monkeypatch.setattr(sup, "_search", lambda q, limit, filters=None: searched.append(q) or [])
    sup.research("q")
    assert searched == ["first", "second"]


def test_results_are_deduplicated_across_angles(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"a","query":"x"},{"angle":"b","query":"y"}]')
    monkeypatch.setattr(sup, "generate", lambda p, **kw: "s")
    monkeypatch.setattr(sup, "_search", lambda q, limit, filters=None: [_evidence("act:1:sec-1")])
    # Real fusion here: de-duplication is its job, so stubbing it would test
    # nothing.
    assert len(sup.research("q").evidence) == 1


def test_a_failing_search_does_not_lose_the_others(monkeypatch):
    import legal_ai.agents.research_plan as rp

    monkeypatch.setattr(rp, "generate", lambda p, **kw:
        '[{"angle":"a","query":"bad"},{"angle":"b","query":"good"}]')
    monkeypatch.setattr(sup, "generate", lambda p, **kw: "s")
    monkeypatch.setattr(sup, "_search",
        lambda q, limit=None, filters=None: [] if q == "bad" else [_evidence("act:1:sec-2")])
    monkeypatch.setattr(sup, "_merge", lambda per_angle, limit: [e for a in per_angle for e in a])
    assert len(sup.research("q").evidence) == 1


# ------------------------------------------------------------ summarising

def test_the_summary_always_carries_the_evidence_ids(monkeypatch):
    # A summary that loses them makes every downstream claim ungroundable,
    # so they are appended structurally rather than asked for.
    monkeypatch.setattr(sup, "generate", lambda p, **kw: "prose with no identifiers")
    summary = sup.summarise("q", [_evidence("act:2158:sec-18")])
    assert "act:2158:sec-18" in summary


def test_the_summary_survives_the_model_failing(monkeypatch):
    monkeypatch.setattr(sup, "generate", lambda p, **kw: (_ for _ in ()).throw(RuntimeError("429")))
    assert "act:2158:sec-18" in sup.summarise("q", [_evidence("act:2158:sec-18")])


def test_summarising_nothing_says_so():
    assert "No supporting provisions" in sup.summarise("q", [])


# ---------------------------------------------------------------- ranking

def test_search_calls_hybrid_search_directly():
    # The same call the rewrite-only baseline makes, so a single-angle
    # question runs that exact path rather than something similar to it.
    import inspect

    source = inspect.getsource(sup._search)
    assert "hybrid_search(query" in source
    assert "get_tool(" not in source


def test_a_single_angle_keeps_the_order_search_gave_it():
    # That order came from the full Phase 2 pipeline, scored against the
    # statutory query. Passing it through unchanged is the current
    # behaviour; re-ranking it appeared worse, but inside benchmark noise.
    results = [_evidence("first"), _evidence("second"), _evidence("third")]
    assert [e.document_id for e in sup._merge([results], limit=10)] == [
        "first", "second", "third"]


def test_several_angles_are_interleaved_so_none_is_buried():
    a = [_evidence("a1"), _evidence("a2"), _evidence("a3")]
    b = [_evidence("b1"), _evidence("b2")]
    ids = [e.document_id for e in sup._merge([a, b], limit=10)]
    assert ids[:2] == ["a1", "b1"]


def test_merging_deduplicates_across_angles():
    a = [_evidence("same"), _evidence("x")]
    b = [_evidence("same"), _evidence("y")]
    ids = [e.document_id for e in sup._merge([a, b], limit=10)]
    assert ids.count("same") == 1


def test_merging_respects_the_limit():
    a = [_evidence(f"d{i}") for i in range(20)]
    assert len(sup._merge([a], limit=5)) == 5
