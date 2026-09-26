"""Graph chunk workers inherit the credential workspace of their run."""

from contextvars import ContextVar

from app.services.graph_builder import GraphBuilderService


def test_chunk_workers_receive_isolated_context():
    current_workspace = ContextVar("test_workspace", default=None)
    seen = []

    class Storage:
        def add_text(self, graph_id, chunk, **kwargs):
            seen.append((chunk, current_workspace.get()))
            return chunk

    token = current_workspace.set("tenant-a")
    try:
        result = GraphBuilderService(Storage()).add_text_batches(
            "graph-a", ["first", "second"]
        )
    finally:
        current_workspace.reset(token)

    assert result == ["first", "second"]
    assert sorted(seen) == [("first", "tenant-a"), ("second", "tenant-a")]
