"""
Tests for EntityReader — ensures the Cypher-pushdown path is wired through the
GraphStorage interface and that the resulting ``FilteredEntities`` shape stays
backwards-compatible for the API layer.
"""

from unittest.mock import MagicMock

import pytest

from app.services.entity_reader import (
    EntityReader,
    EntityNode,
    FilteredEntities,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fixture_entities():
    """Mirrors the dict shape returned by Neo4jStorage.get_filtered_entities_with_edges."""
    return [
        {
            "uuid": "u1",
            "name": "Alice",
            "labels": ["Entity", "Person"],
            "summary": "researcher",
            "attributes": {"age": 30},
            "created_at": None,
            "related_edges": [
                {
                    "direction": "outgoing",
                    "edge_name": "KNOWS",
                    "fact": "Alice knows Bob",
                    "target_node_uuid": "u2",
                },
            ],
            "related_nodes": [
                {
                    "uuid": "u2",
                    "name": "Bob",
                    "labels": ["Person"],
                    "summary": "colleague",
                },
            ],
        },
        {
            "uuid": "u3",
            "name": "Acme",
            "labels": ["Entity", "Organization"],
            "summary": "org",
            "attributes": {},
            "created_at": None,
            "related_edges": [],
            "related_nodes": [],
        },
    ]


@pytest.fixture
def storage():
    mock = MagicMock()
    mock.get_filtered_entities_with_edges.return_value = {
        "entities": _fixture_entities(),
        "total_count": 5,
    }
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_filter_defined_entities_uses_pushdown(storage):
    """EntityReader must delegate filtering to the GraphStorage method."""
    reader = EntityReader(storage)

    result = reader.filter_defined_entities("g1")

    storage.get_filtered_entities_with_edges.assert_called_once_with(
        graph_id="g1",
        defined_entity_types=None,
        enrich_with_edges=True,
    )
    assert isinstance(result, FilteredEntities)
    assert result.total_count == 5
    assert result.filtered_count == 2
    assert result.entity_types == {"Person", "Organization"}


def test_filter_defined_entities_builds_entity_nodes(storage):
    reader = EntityReader(storage)

    result = reader.filter_defined_entities("g1")

    by_uuid = {e.uuid: e for e in result.entities}
    assert set(by_uuid) == {"u1", "u3"}

    alice = by_uuid["u1"]
    assert isinstance(alice, EntityNode)
    assert alice.name == "Alice"
    assert alice.labels == ["Entity", "Person"]
    assert alice.summary == "researcher"
    assert alice.attributes == {"age": 30}
    assert len(alice.related_edges) == 1
    assert alice.related_edges[0]["edge_name"] == "KNOWS"
    assert alice.related_nodes == [
        {"uuid": "u2", "name": "Bob", "labels": ["Person"], "summary": "colleague"}
    ]


def test_filter_defined_entities_respects_type_filter(storage):
    reader = EntityReader(storage)

    reader.filter_defined_entities("g1", defined_entity_types=["Person"])

    storage.get_filtered_entities_with_edges.assert_called_once_with(
        graph_id="g1",
        defined_entity_types=["Person"],
        enrich_with_edges=True,
    )


def test_filter_defined_entities_skips_pure_entity_labels():
    """Defensive guard: if storage ever returns a node without a custom label,
    EntityReader must still drop it (matches original contract)."""
    storage = MagicMock()
    storage.get_filtered_entities_with_edges.return_value = {
        "entities": [
            {
                "uuid": "u4",
                "name": "Untyped",
                "labels": ["Entity"],  # no custom label
                "summary": "",
                "attributes": {},
                "related_edges": [],
                "related_nodes": [],
            }
        ],
        "total_count": 1,
    }
    reader = EntityReader(storage)

    result = reader.filter_defined_entities("g1")

    assert result.filtered_count == 0
    assert result.total_count == 1
    assert result.entity_types == set()


def test_filter_defined_entities_handles_missing_fields():
    """Neo4jStorage may emit partial dicts for sparsely-populated nodes."""
    storage = MagicMock()
    storage.get_filtered_entities_with_edges.return_value = {
        "entities": [
            {
                "uuid": "u5",
                "name": "",
                "labels": ["Entity", "Topic"],
                # summary / attributes / related_* missing
            }
        ],
        "total_count": 1,
    }
    reader = EntityReader(storage)

    result = reader.filter_defined_entities("g1", enrich_with_edges=False)

    assert result.filtered_count == 1
    node = result.entities[0]
    assert node.summary == ""
    assert node.attributes == {}
    assert node.related_edges == []
    assert node.related_nodes == []


def test_get_entities_by_type_delegates(storage):
    reader = EntityReader(storage)

    result = reader.get_entities_by_type("g1", "Person")

    # wraps filter_defined_entities with a one-element whitelist
    storage.get_filtered_entities_with_edges.assert_called_once_with(
        graph_id="g1",
        defined_entity_types=["Person"],
        enrich_with_edges=True,
    )
    assert all(isinstance(e, EntityNode) for e in result)
