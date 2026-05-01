"""Graph-Domain-DTOs.

Issue #52 (EPIC-08-ST-03): Stabile, dokumentierte Backend-DTOs für Graph-
Knoten, -Kanten und Graph-Snapshots. Wire-Format-Spiegel zu den
Frontend-ViewModels in ``frontend/src/components/graph/graphPanelData.js``
(Issue #36).

Die DTOs reproduzieren das Schema, das ``Neo4jStorage.get_graph_data``
liefert — inklusive der Enriched-Fields, die der Storage-Layer beim JOIN
ergänzt (``fact_type``, ``source_node_name``, ``target_node_name``,
``episodes``-Legacy-Alias). Frontend-Mapper (``normalizeEdgeAliases``) kann
sich auf diese Felder verlassen, ohne Backend-interne Property-Namen kennen
zu müssen.

Wire-Identity-Garantie: ``GraphDataDTO.from_storage_dict(d).to_dict()`` muss
genau das gleiche Dict liefern wie der Storage-Output (key-/value-equiv).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GraphNodeDTO:
    """Knoten im Wissensgraphen.

    Felder folgen dem Format aus ``Neo4jStorage._node_to_dict`` (UUID, Name,
    Labels, Summary, Attribute-Dict). ``created_at`` ist optional, weil
    historische Knoten dieses Feld nicht haben.
    """

    uuid: str
    name: str
    labels: List[str] = field(default_factory=list)
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": list(self.labels),
            "summary": self.summary,
            "attributes": dict(self.attributes),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNodeDTO":
        return cls(
            uuid=data.get("uuid", ""),
            name=data.get("name", ""),
            labels=list(data.get("labels", []) or []),
            summary=data.get("summary", ""),
            attributes=dict(data.get("attributes", {}) or {}),
            created_at=data.get("created_at"),
        )


@dataclass
class GraphEdgeDTO:
    """RELATION-Kante mit zeitlicher Gültigkeit und Reinforcement-Count.

    Pflichtfelder kommen aus den Neo4j-Properties (``_edge_to_dict``).
    Enriched-Fields (``fact_type``, ``source_node_name``,
    ``target_node_name``, ``episodes``) werden beim Storage-JOIN gefüllt
    und sind die Frontend-Adresse — ohne sie wäre die Kante nicht
    darstellbar.
    """

    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[Any] = None
    valid_at: Optional[Any] = None
    invalid_at: Optional[Any] = None
    expired_at: Optional[Any] = None
    valid_from_round: Optional[int] = None
    valid_to_round: Optional[int] = None
    reinforced_count: int = 1
    episode_ids: List[Any] = field(default_factory=list)

    # Enriched fields (vom Storage-JOIN ergänzt)
    fact_type: str = ""
    source_node_name: str = ""
    target_node_name: str = ""
    episodes: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "attributes": dict(self.attributes),
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at,
            "valid_from_round": self.valid_from_round,
            "valid_to_round": self.valid_to_round,
            "reinforced_count": self.reinforced_count,
            "episode_ids": list(self.episode_ids),
            "fact_type": self.fact_type,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "episodes": list(self.episodes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdgeDTO":
        episode_ids = data.get("episode_ids", []) or []
        # Falls der Storage einen Default für episodes nicht setzt, fallback
        # auf episode_ids (so machen es Storage und Frontend bisher).
        episodes = data.get("episodes")
        if episodes is None:
            episodes = list(episode_ids)
        return cls(
            uuid=data.get("uuid", ""),
            name=data.get("name", ""),
            fact=data.get("fact", ""),
            source_node_uuid=data.get("source_node_uuid", ""),
            target_node_uuid=data.get("target_node_uuid", ""),
            attributes=dict(data.get("attributes", {}) or {}),
            created_at=data.get("created_at"),
            valid_at=data.get("valid_at"),
            invalid_at=data.get("invalid_at"),
            expired_at=data.get("expired_at"),
            valid_from_round=data.get("valid_from_round"),
            valid_to_round=data.get("valid_to_round"),
            reinforced_count=data.get("reinforced_count", 1),
            episode_ids=list(episode_ids),
            fact_type=data.get("fact_type", "") or data.get("name", ""),
            source_node_name=data.get("source_node_name", "") or "",
            target_node_name=data.get("target_node_name", "") or "",
            episodes=list(episodes),
        )


@dataclass
class GraphDataDTO:
    """Voller Graph-Dump für eine ``graph_id``: Knoten, Kanten, Counts."""

    graph_id: str
    nodes: List[GraphNodeDTO] = field(default_factory=list)
    edges: List[GraphEdgeDTO] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "node_count": self.node_count,
            "edge_count": self.edge_count,
        }

    @classmethod
    def from_storage_dict(cls, data: Dict[str, Any]) -> "GraphDataDTO":
        """Re-Hydration aus dem ``Neo4jStorage.get_graph_data``-Output.

        Garantiert Wire-Identity: ``from_storage_dict(d).to_dict() == d``
        (für gültige Storage-Outputs).
        """
        nodes_raw = data.get("nodes", []) or []
        edges_raw = data.get("edges", []) or []
        return cls(
            graph_id=data.get("graph_id", ""),
            nodes=[GraphNodeDTO.from_dict(n) for n in nodes_raw],
            edges=[GraphEdgeDTO.from_dict(e) for e in edges_raw],
            node_count=data.get("node_count", len(nodes_raw)),
            edge_count=data.get("edge_count", len(edges_raw)),
        )


__all__ = [
    "GraphNodeDTO",
    "GraphEdgeDTO",
    "GraphDataDTO",
]
