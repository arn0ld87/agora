"""Wire-Identity-Tests für die Graph-DTOs (Issue #52).

Sicherstellt, dass ``GraphDataDTO.from_storage_dict(d).to_dict()`` für
realistische ``Neo4jStorage.get_graph_data``-Outputs bit-identisch ist —
kein Frontend-Diff durch das DTO-Refactor.
"""

from __future__ import annotations

from app.models.graph import GraphDataDTO, GraphEdgeDTO, GraphNodeDTO


def _sample_storage_dict() -> dict:
    """Baut ein realistisches Storage-Output-Dict, deckt die meisten Felder ab."""
    return {
        "graph_id": "graph_abc123",
        "nodes": [
            {
                "uuid": "uuid-node-1",
                "name": "Alice",
                "labels": ["Person"],
                "summary": "A protagonist.",
                "attributes": {"age": 30, "role": "lead"},
                "created_at": "2026-05-01T10:00:00",
            },
            {
                "uuid": "uuid-node-2",
                "name": "Bob",
                "labels": [],
                "summary": "",
                "attributes": {},
                "created_at": None,
            },
        ],
        "edges": [
            {
                "uuid": "uuid-edge-1",
                "name": "knows",
                "fact": "Alice knows Bob from school.",
                "source_node_uuid": "uuid-node-1",
                "target_node_uuid": "uuid-node-2",
                "attributes": {"since": 2010},
                "created_at": "2026-05-01T10:01:00",
                "valid_at": "2026-05-01T10:01:00",
                "invalid_at": None,
                "expired_at": None,
                "valid_from_round": 0,
                "valid_to_round": 5,
                "reinforced_count": 3,
                "episode_ids": ["ep-1", "ep-2"],
                # Enriched fields from JOIN in get_graph_data
                "fact_type": "knows",
                "source_node_name": "Alice",
                "target_node_name": "Bob",
                "episodes": ["ep-1", "ep-2"],
            }
        ],
        "node_count": 2,
        "edge_count": 1,
    }


def test_graph_data_dto_roundtrip_preserves_storage_dict() -> None:
    """``from_storage_dict(d).to_dict()`` muss ``d`` bit-identisch reproduzieren."""
    storage_dict = _sample_storage_dict()
    dto = GraphDataDTO.from_storage_dict(storage_dict)
    assert dto.to_dict() == storage_dict


def test_graph_node_dto_handles_optional_fields() -> None:
    """Knoten ohne ``created_at`` / leere Listen kommen sauber durch."""
    node = GraphNodeDTO.from_dict({
        "uuid": "u1",
        "name": "n1",
        "labels": None,
        "summary": "",
        "attributes": None,
        "created_at": None,
    })
    out = node.to_dict()
    assert out["uuid"] == "u1"
    assert out["labels"] == []
    assert out["attributes"] == {}
    assert out["created_at"] is None


def test_graph_edge_dto_falls_back_episodes_to_episode_ids() -> None:
    """Wenn der Storage ``episodes`` nicht setzt, fallback auf ``episode_ids``."""
    edge = GraphEdgeDTO.from_dict({
        "uuid": "e1",
        "name": "rel",
        "fact": "f",
        "source_node_uuid": "s",
        "target_node_uuid": "t",
        "episode_ids": ["ep-x"],
        # episodes fehlt
    })
    assert edge.episodes == ["ep-x"]
    assert edge.episode_ids == ["ep-x"]


def test_graph_edge_dto_fact_type_falls_back_to_name() -> None:
    """``fact_type`` ist Alias für ``name`` — fallback wenn nicht gesetzt."""
    edge = GraphEdgeDTO.from_dict({
        "uuid": "e1",
        "name": "knows",
        "fact": "f",
        "source_node_uuid": "s",
        "target_node_uuid": "t",
        # fact_type fehlt
    })
    assert edge.fact_type == "knows"


def test_graph_data_dto_empty_graph() -> None:
    """Leerer Graph (keine Nodes/Edges) ist gültig."""
    dto = GraphDataDTO.from_storage_dict({
        "graph_id": "empty",
        "nodes": [],
        "edges": [],
        "node_count": 0,
        "edge_count": 0,
    })
    assert dto.node_count == 0
    assert dto.edge_count == 0
    out = dto.to_dict()
    assert out["nodes"] == []
    assert out["edges"] == []


def test_graph_data_dto_count_fallback_to_list_length() -> None:
    """Fehlt ``node_count``/``edge_count``, wird die Listen-Länge benutzt."""
    dto = GraphDataDTO.from_storage_dict({
        "graph_id": "g",
        "nodes": [{"uuid": "u", "name": "n"}],
        "edges": [],
        # counts fehlen
    })
    assert dto.node_count == 1
    assert dto.edge_count == 0
