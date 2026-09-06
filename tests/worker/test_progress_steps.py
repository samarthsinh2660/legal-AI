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
