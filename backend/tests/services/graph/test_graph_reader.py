"""Smoke-tests for app.services.graph.graph_reader (M11 Phase 5b PR 2).

Each test exercises one module-level reader function in isolation.
GraphStorage is replaced by a MagicMock with spec so that only real
interface methods can be called.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.graph.graph_dtos import NodeInfo
from app.services.graph.graph_reader import (
    get_all_nodes,
    get_graph_statistics,
    get_node_detail,
)
from app.storage.graph_storage import GraphStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage() -> MagicMock:
    """Return a MagicMock bound to the real GraphStorage interface."""
    return MagicMock(spec=GraphStorage)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetAllNodes:
    def test_delegates_to_storage_and_returns_node_info_list(self) -> None:
        storage = _make_storage()
        storage.get_all_nodes.return_value = [
            {
                "uuid": "uuid-1",
                "name": "Alice",
                "labels": ["Person", "Entity"],
                "summary": "A test person",
                "attributes": {},
            },
            {
                "uuid": "uuid-2",
                "name": "Berlin",
                "labels": ["Location", "Entity"],
                "summary": "Capital of Germany",
                "attributes": {"population": 3700000},
            },
        ]

        result = get_all_nodes("graph-42", storage=storage)

        storage.get_all_nodes.assert_called_once_with("graph-42")
        assert len(result) == 2
        assert isinstance(result[0], NodeInfo)
        assert result[0].uuid == "uuid-1"
        assert result[0].name == "Alice"
        assert isinstance(result[1], NodeInfo)
        assert result[1].labels == ["Location", "Entity"]


class TestGetNodeDetail:
    def test_returns_none_when_storage_returns_none(self) -> None:
        storage = _make_storage()
        storage.get_node.return_value = None

        result = get_node_detail("missing-uuid", storage=storage)

        storage.get_node.assert_called_once_with("missing-uuid")
        assert result is None

    def test_returns_node_info_when_node_found(self) -> None:
        storage = _make_storage()
        storage.get_node.return_value = {
            "uuid": "abc-123",
            "name": "Dietmar",
            "labels": ["Person"],
            "summary": "A senior engineer",
            "attributes": {"age": 54},
        }

        result = get_node_detail("abc-123", storage=storage)

        assert isinstance(result, NodeInfo)
        assert result.uuid == "abc-123"
        assert result.name == "Dietmar"
        assert result.summary == "A senior engineer"


class TestGetGraphStatistics:
    def test_returns_aggregated_dict(self) -> None:
        storage = _make_storage()
        storage.get_all_nodes.return_value = [
            {
                "uuid": "n1",
                "name": "Alice",
                "labels": ["Person", "Entity"],
                "summary": "",
                "attributes": {},
            },
            {
                "uuid": "n2",
                "name": "Berlin",
                "labels": ["Location", "Entity"],
                "summary": "",
                "attributes": {},
            },
        ]
        storage.get_all_edges.return_value = [
            {
                "uuid": "e1",
                "name": "LIVES_IN",
                "fact": "Alice lives in Berlin",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
            },
            {
                "uuid": "e2",
                "name": "LIVES_IN",
                "fact": "Bob lives in Berlin",
                "source_node_uuid": "n3",
                "target_node_uuid": "n2",
            },
        ]

        result = get_graph_statistics("graph-42", storage=storage)

        assert result["graph_id"] == "graph-42"
        assert result["total_nodes"] == 2
        assert result["total_edges"] == 2
        assert result["entity_types"] == {"Person": 1, "Location": 1}
        assert result["relation_types"] == {"LIVES_IN": 2}

    def test_empty_graph_returns_zero_counts(self) -> None:
        storage = _make_storage()
        storage.get_all_nodes.return_value = []
        storage.get_all_edges.return_value = []

        result = get_graph_statistics("empty-graph", storage=storage)

        assert result["total_nodes"] == 0
        assert result["total_edges"] == 0
        assert result["entity_types"] == {}
        assert result["relation_types"] == {}
