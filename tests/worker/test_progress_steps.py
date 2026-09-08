"""What the progress pane is allowed to claim.

The pane's whole justification is that it "shows real work, never fake
thinking" (design/UX_FLOWS.md). A step announcing work that did not happen
is the one thing it must not do.
"""

from __future__ import annotations

from worker import graph as graph_module


class _FakeGraph:
    """Emits one update per node, like LangGraph's `stream`."""

    def __init__(self, nodes):
        self._nodes = nodes

    def stream(self, inputs):
        for node in self._nodes:
            yield {node: {}}


def _steps(inputs, nodes, monkeypatch):
    monkeypatch.setattr(graph_module, "_compiled", lambda: _FakeGraph(nodes))
    return [
        node
        for kind, node in graph_module.stream_graph(inputs)
        if kind == "step"
    ]


def test_no_documents_means_no_reading_your_documents_step(monkeypatch):
    """The `document` node runs either way and returns immediately having
    read nothing. Announcing it claims work that did not happen."""
    seen = _steps(
        {"question": "what is section 138"},
        ["document", "context_builder", "clarification", "draft"],
        monkeypatch,
    )
    assert "document" not in seen
    assert seen == ["context_builder", "clarification", "draft"]


def test_an_attached_document_still_announces_the_step(monkeypatch):
    """The suppression is about work not done, not about hiding the step."""
    seen = _steps(
        {"question": "read this", "document_ids": ["doc-1"]},
        ["document", "context_builder", "draft"],
        monkeypatch,
    )
    assert seen == ["document", "context_builder", "draft"]


# --- a graph that finished must not be called a timeout --------------------


def test_a_graph_whose_last_node_ran_long_still_reports_its_answer(monkeypatch):
    """The check ran after the last update was consumed, so a run whose
    final node pushed it past the ceiling was called a timeout and its
    fully paid-for answer thrown away."""
    import time

    class _SlowLastNode:
        def stream(self, inputs):
            yield {"research": {}}
            time.sleep(0.15)          # the ceiling passes inside this node
            yield {"draft": {"answer": "the answer"}}

    monkeypatch.setattr(graph_module, "_compiled", lambda: _SlowLastNode())
    monkeypatch.setattr(graph_module, "read_timeout", lambda: 0.10)

    events = list(graph_module.stream_graph({"question": "q"}))
    kinds = [kind for kind, _payload in events]

    assert "timeout" not in kinds
    assert kinds[-1] == "done"
    assert events[-1][1]["answer"] == "the answer"


def test_a_graph_still_producing_past_its_deadline_is_stopped(monkeypatch):
    """The ceiling still has to bite on a graph that has more to do."""
    import itertools
    import time

    class _Endless:
        def stream(self, inputs):
            for n in itertools.count():
                time.sleep(0.05)
                yield {f"node{n}": {}}

    monkeypatch.setattr(graph_module, "_compiled", lambda: _Endless())
    monkeypatch.setattr(graph_module, "read_timeout", lambda: 0.10)

    kinds = [kind for kind, _payload in graph_module.stream_graph({"question": "q"})]

    assert kinds[-1] == "timeout"
