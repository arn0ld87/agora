"""
GraphDiff-Contract v1 (Pydantic v2) — Single Source of Truth für Graph-Snapshot-Vergleiche.

Modelliert den Diff zwischen zwei Graph-Snapshots (Round-to-Round oder Branch-Diff).
Datenquellen:
- backend/app/services/temporal_graph.py  (get_snapshot, compute_diff)
- backend/app/services/network_analytics.py  (PolarizationMetrics, bridge_agents)
- docs/2026-05-03-task-22-graph-diff-spike.md § 3 (autoritatives Spec-Dokument)

Designentscheidungen (Abweichungen vom Spike-Pseudocode):
- source_id / target_id: str statt str|int — Neo4j-IDs werden als String serialisiert.
- properties: dict[str, str|int|float|bool] statt dict[str, Any] — Any ist mit
  extra="forbid" semantisch widersprüchlich; falls ein Producer reichere Typen
  braucht, soll er auf JSON-String serialisieren und hier hinterlegen.
- before/after in NodePropertyShift: str|int|float|bool|None (kein Any).
- edges_reinforced / edges_weakened: list[EdgeReinforcement] / list[EdgeWeakening]
  (typisiert, KEIN list[dict]).
- comparison_type: Literal["round-to-round", "branch-diff"] statt freiem str.

Aufruf zum Schema-Dump: cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Gemeinsame Konfiguration für alle Modelle dieses Moduls
_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=False)


class EdgeData(BaseModel):
    """Edge metadata with unique identifier.

    Note on properties: uses dict[str, str|int|float|bool] instead of
    dict[str, Any] to remain compatible with extra="forbid" semantics.
    Producers with richer value types should JSON-stringify those values.
    """

    model_config = _STRICT

    uuid: str = Field(..., description="Eindeutige Kanten-ID (Neo4j-UUID oder synthetisch)")
    source_id: str = Field(..., description="Quell-Knoten-ID (als String serialisiert)")
    target_id: str = Field(..., description="Ziel-Knoten-ID (als String serialisiert)")
    relation_type: str = Field(..., description='Kantentyp, z. B. "FOLLOWS", "OPPOSES"')
    weight: float | None = Field(default=None, description="Optionales Gewicht/Stärke")
    reinforced_count: int | None = Field(default=None, description="Anzahl Verstärkungen")
    properties: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Weitere Metadaten; komplexe Typen bitte JSON-stringifizieren",
    )


class NodePropertyShift(BaseModel):
    """Property change on a single graph node.

    before/after verwenden denselben engen Union-Typ wie EdgeData.properties,
    um dict[str, Any] mit extra='forbid' zu vermeiden.
    """

    model_config = _STRICT

    node_id: str = Field(..., description="Knoten-ID (als String serialisiert)")
    node_label: str = Field(..., description='Knotentyp-Label, z. B. "Agent", "Entity"')
    property_name: str = Field(..., description='Eigenschaftsname, z. B. "sentiment_score"')
    before: str | int | float | bool | None = Field(
        default=None, description="Wert vor dem Diff"
    )
    after: str | int | float | bool | None = Field(
        default=None, description="Wert nach dem Diff"
    )


class ClusterShift(BaseModel):
    """Agent migrating between two clusters across snapshots."""

    model_config = _STRICT

    agent_id: int
    cluster_a_id: int
    cluster_a_label: str
    cluster_b_id: int
    cluster_b_label: str
    cluster_a_size: int = Field(ge=0, description="Cluster-Größe in Snapshot A")
    cluster_b_size: int = Field(ge=0, description="Cluster-Größe in Snapshot B")


class BridgeAgentShift(BaseModel):
    """Change in betweenness-centrality top-k membership for one agent."""

    model_config = _STRICT

    agent_id: int
    action: Literal["joined_top_k", "left_top_k"]
    centrality_before: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Betweenness vor dem Diff"
    )
    centrality_after: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Betweenness nach dem Diff"
    )
    tier: str | None = Field(default=None, description='Optionales Tier-Label, z. B. "top-5"')


class ClusterSummary(BaseModel):
    """Summary representation of a single cluster."""

    model_config = _STRICT

    cluster_id: int
    size: int = Field(ge=0)
    label: str = Field(..., description="Deterministisches TF-Top-3-Label")
    member_count: int = Field(ge=0, description="Anzahl Agenten im Cluster")


class GraphSnapshot(BaseModel):
    """Graph state at a specific point in time (one snapshot)."""

    model_config = _STRICT

    graph_id: str
    round_num: int | None = Field(default=None, description="Runden-Nummer, falls rund-basiert")
    snapshot_id: str | None = Field(default=None, description="Eindeutiger Snapshot-Key oder UUID")
    created_at: datetime
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    edges: list[EdgeData] = Field(default_factory=list)
    density: float = Field(
        ge=0.0,
        le=1.0,
        description="Netzwerk-Dichte: edge_count / (node_count * (node_count - 1))",
    )
    cluster_count: int = Field(ge=0)
    dominant_clusters: list[ClusterSummary] = Field(
        default_factory=list, description="Top-k Cluster nach Louvain"
    )
    bridge_agents: list[int] = Field(
        default_factory=list, description="Top-k Agenten nach Betweenness-Centrality"
    )


class EdgeReinforcement(BaseModel):
    """Typed record for an edge that gained weight/reinforcement between snapshots.

    Validator stellt sicher: weight_after >= weight_before.
    Kanten mit sinkendem Gewicht gehören in EdgeWeakening.
    """

    model_config = _STRICT

    edge: EdgeData
    weight_before: float
    weight_after: float
    reinforced_count_before: int = Field(ge=0)
    reinforced_count_after: int = Field(ge=0)

    @model_validator(mode="after")
    def _weight_must_increase(self) -> "EdgeReinforcement":
        if self.weight_after < self.weight_before:
            raise ValueError(
                f"EdgeReinforcement: weight_after ({self.weight_after}) muss >= "
                f"weight_before ({self.weight_before}) sein. "
                "Kanten mit sinkendem Gewicht bitte in EdgeWeakening eintragen."
            )
        return self


class EdgeWeakening(BaseModel):
    """Typed record for an edge that lost weight/reinforcement between snapshots.

    Validator stellt sicher: weight_after < weight_before.
    Kanten mit steigendem Gewicht gehören in EdgeReinforcement.
    """

    model_config = _STRICT

    edge: EdgeData
    weight_before: float
    weight_after: float
    reinforced_count_before: int = Field(ge=0)
    reinforced_count_after: int = Field(ge=0)

    @model_validator(mode="after")
    def _weight_must_decrease(self) -> "EdgeWeakening":
        if self.weight_after >= self.weight_before:
            raise ValueError(
                f"EdgeWeakening: weight_after ({self.weight_after}) muss < "
                f"weight_before ({self.weight_before}) sein. "
                "Kanten mit steigendem oder gleichem Gewicht bitte in EdgeReinforcement eintragen."
            )
        return self


class GraphDiffMetrics(BaseModel):
    """Aggregated metrics summarising the diff between two graph snapshots."""

    model_config = _STRICT

    total_edges_added: int = Field(ge=0)
    total_edges_removed: int = Field(ge=0)
    total_edges_reinforced: int = Field(ge=0)
    total_edges_weakened: int = Field(ge=0)
    # delta-Felder sind signed — keine ge/le-Constraints
    avg_reinforcement_delta: float = Field(
        description="Durchschnittlicher Gewichts-Anstieg bei verstärkten Kanten"
    )
    avg_weakening_delta: float = Field(
        description="Durchschnittlicher Gewichts-Rückgang bei geschwächten Kanten"
    )
    density_delta: float = Field(description="Signed delta: B_density - A_density")
    node_properties_changed: int = Field(
        ge=0, description="Knoten mit mindestens einer Eigenschafts-Änderung"
    )
    agents_changed_clusters: int = Field(ge=0)
    clusters_new: int = Field(ge=0)
    clusters_removed: int = Field(ge=0)
    bridge_agents_joined: int = Field(ge=0)
    bridge_agents_left: int = Field(ge=0)


class GraphDiff(BaseModel):
    """Complete diff between two graph snapshots (top-level contract model).

    comparison_type unterscheidet rund-basierten Vergleich ("round-to-round")
    von Branch-Diff ("branch-diff"). Beide Snapshot-Objekte werden vollständig
    eingebettet, damit der Consumer keine zweite Anfrage stellen muss.
    """

    model_config = _STRICT

    # Metadaten
    graph_id: str
    snapshot_a_id: str
    snapshot_b_id: str
    created_at: datetime
    comparison_type: Literal["round-to-round", "branch-diff"]

    # Vollständige Snapshots
    snapshot_a: GraphSnapshot
    snapshot_b: GraphSnapshot

    # Kanten-Diffs
    edges_added: list[EdgeData] = Field(default_factory=list)
    edges_removed: list[EdgeData] = Field(default_factory=list)
    edges_reinforced: list[EdgeReinforcement] = Field(
        default_factory=list,
        description="Typisiert — KEIN list[dict]. Validator prüft weight_after >= weight_before.",
    )
    edges_weakened: list[EdgeWeakening] = Field(
        default_factory=list,
        description="Typisiert — KEIN list[dict]. Validator prüft weight_after < weight_before.",
    )

    # Knoten-Property-Diffs
    node_properties_changed: list[NodePropertyShift] = Field(default_factory=list)

    # Cluster-Diffs
    cluster_shifts: list[ClusterShift] = Field(
        default_factory=list, description="Agenten, die zwischen Clustern wechselten"
    )
    clusters_new: list[ClusterSummary] = Field(default_factory=list)
    clusters_removed: list[ClusterSummary] = Field(default_factory=list)

    # Bridge-Agent-Diffs
    bridge_agent_shifts: list[BridgeAgentShift] = Field(default_factory=list)

    # Aggregierte Metriken
    metrics: GraphDiffMetrics
