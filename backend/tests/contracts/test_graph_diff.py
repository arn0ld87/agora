"""
Contract-Tests für graph_diff.py — gegen den echten Vertrag,
nicht gegen die Implementierung.

Datenquelle für Fixtures: docs/2026-05-03-task-22-graph-diff-spike.md § 4
(JSON-Response-Beispiel, leicht vereinfacht für Unit-Tests).
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.contracts.graph_diff import (
    BridgeAgentShift,
    ClusterShift,
    ClusterSummary,
    EdgeData,
    EdgeReinforcement,
    EdgeWeakening,
    GraphDiff,
    GraphDiffMetrics,
    GraphSnapshot,
    NodePropertyShift,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen / Fixtures
# ---------------------------------------------------------------------------

def _make_edge(
    uuid: str = "e-aabbccdd",
    source_id: str = "3",
    target_id: str = "7",
    relation_type: str = "FOLLOWS",
    weight: float | None = 1.0,
    reinforced_count: int | None = 1,
) -> EdgeData:
    return EdgeData(
        uuid=uuid,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        weight=weight,
        reinforced_count=reinforced_count,
    )


def _make_cluster_summary(
    cluster_id: int = 0, size: int = 10, label: str = "energie, politik", member_count: int = 10
) -> ClusterSummary:
    return ClusterSummary(
        cluster_id=cluster_id, size=size, label=label, member_count=member_count
    )


def _make_snapshot(
    graph_id: str = "sim-abc123-graph",
    snapshot_id: str = "branch-001",
    node_count: int = 38,
    edge_count: int = 127,
    density: float = 0.0878,
    cluster_count: int = 3,
) -> GraphSnapshot:
    return GraphSnapshot(
        graph_id=graph_id,
        snapshot_id=snapshot_id,
        created_at="2026-05-03T14:10:00Z",
        node_count=node_count,
        edge_count=edge_count,
        density=density,
        cluster_count=cluster_count,
        dominant_clusters=[
            _make_cluster_summary(0, 18, "energiepolitik, diskurs, europa", 18),
            _make_cluster_summary(1, 12, "finanzmarkt, handel, europa", 12),
        ],
        bridge_agents=[5, 12, 18],
    )


def _make_metrics(**overrides) -> GraphDiffMetrics:
    defaults = dict(
        total_edges_added=8,
        total_edges_removed=2,
        total_edges_reinforced=12,
        total_edges_weakened=0,
        avg_reinforcement_delta=0.22,
        avg_weakening_delta=0.0,
        density_delta=-0.0032,
        node_properties_changed=5,
        agents_changed_clusters=1,
        clusters_new=1,
        clusters_removed=0,
        bridge_agents_joined=1,
        bridge_agents_left=1,
    )
    defaults.update(overrides)
    return GraphDiffMetrics(**defaults)


def _make_full_graph_diff() -> GraphDiff:
    """Vollständiges GraphDiff-Objekt analog zum Spike-§-4-JSON-Response."""
    snapshot_a = _make_snapshot(snapshot_id="branch-001")
    snapshot_b = _make_snapshot(
        snapshot_id="branch-002",
        node_count=41,
        edge_count=142,
        density=0.0846,
        cluster_count=4,
    )

    edge_added = _make_edge(uuid="e-9c3d2f15", source_id="3", target_id="7")
    edge_removed = _make_edge(
        uuid="e-5f2a1b3c",
        source_id="18",
        target_id="12",
        relation_type="OPPOSES",
        weight=0.6,
        reinforced_count=2,
    )
    reinforced_edge = _make_edge(
        uuid="e-2c4f1a9d",
        source_id="5",
        target_id="12",
        weight=1.0,
        reinforced_count=4,
    )
    edge_reinforcement = EdgeReinforcement(
        edge=reinforced_edge,
        weight_before=0.8,
        weight_after=1.0,
        reinforced_count_before=2,
        reinforced_count_after=4,
    )

    node_shift_1 = NodePropertyShift(
        node_id="5",
        node_label="Agent",
        property_name="sentiment_score",
        before=0.62,
        after=0.55,
    )
    node_shift_2 = NodePropertyShift(
        node_id="12",
        node_label="Agent",
        property_name="interaction_count",
        before=28,
        after=35,
    )

    cluster_shift = ClusterShift(
        agent_id=18,
        cluster_a_id=0,
        cluster_a_label="energiepolitik, diskurs, europa",
        cluster_b_id=2,
        cluster_b_label="digital, blockchain, web3",
        cluster_a_size=18,
        cluster_b_size=6,
    )

    bridge_joined = BridgeAgentShift(
        agent_id=22,
        action="joined_top_k",
        centrality_before=None,
        centrality_after=0.42,
        tier="top-5",
    )
    bridge_left = BridgeAgentShift(
        agent_id=18,
        action="left_top_k",
        centrality_before=0.38,
        centrality_after=0.15,
        tier="top-5",
    )

    return GraphDiff(
        graph_id="sim-abc123-graph",
        snapshot_a_id="branch-001",
        snapshot_b_id="branch-002",
        created_at="2026-05-03T14:45:20Z",
        comparison_type="branch-diff",
        snapshot_a=snapshot_a,
        snapshot_b=snapshot_b,
        edges_added=[edge_added],
        edges_removed=[edge_removed],
        edges_reinforced=[edge_reinforcement],
        edges_weakened=[],
        node_properties_changed=[node_shift_1, node_shift_2],
        cluster_shifts=[cluster_shift],
        clusters_new=[_make_cluster_summary(3, 5, "klima, migration, sozialpolitik", 5)],
        clusters_removed=[],
        bridge_agent_shifts=[bridge_joined, bridge_left],
        metrics=_make_metrics(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_graph_diff_round_trip():
    """Vollständiges Round-Trip: model_validate → model_dump → erneutes model_validate."""
    original = _make_full_graph_diff()
    dumped = original.model_dump()
    restored = GraphDiff.model_validate(dumped)
    assert original == restored


def test_extra_key_rejected_top_level():
    """Unbekannte Felder auf Top-Level-GraphDiff müssen ValidationError auslösen."""
    diff = _make_full_graph_diff()
    data = diff.model_dump()
    data["unknown_field"] = "verboten"
    with pytest.raises(ValidationError, match="unknown_field"):
        GraphDiff.model_validate(data)


def test_extra_key_rejected_nested():
    """Unbekannte Felder in EdgeData und GraphSnapshot müssen abgelehnt werden."""
    # EdgeData
    with pytest.raises(ValidationError):
        EdgeData(
            uuid="x",
            source_id="1",
            target_id="2",
            relation_type="FOLLOWS",
            extra_key_not_in_model="boom",
        )
    # GraphSnapshot
    snap = _make_snapshot()
    snap_data = snap.model_dump()
    snap_data["surprise_field"] = 999
    with pytest.raises(ValidationError):
        GraphSnapshot.model_validate(snap_data)


def test_density_out_of_bounds():
    """density > 1.0 muss ValidationError auslösen (Field(le=1.0))."""
    with pytest.raises(ValidationError):
        GraphSnapshot(
            graph_id="g1",
            created_at="2026-05-03T14:00:00Z",
            node_count=10,
            edge_count=5,
            density=1.5,  # ungültig
            cluster_count=2,
        )


def test_negative_counts_rejected():
    """Negative Zähler müssen abgelehnt werden (Field(ge=0))."""
    # node_count negativ
    with pytest.raises(ValidationError):
        GraphSnapshot(
            graph_id="g1",
            created_at="2026-05-03T14:00:00Z",
            node_count=-1,
            edge_count=5,
            density=0.1,
            cluster_count=1,
        )
    # cluster_b_size negativ in ClusterShift
    with pytest.raises(ValidationError):
        ClusterShift(
            agent_id=1,
            cluster_a_id=0,
            cluster_a_label="label-a",
            cluster_b_id=1,
            cluster_b_label="label-b",
            cluster_a_size=10,
            cluster_b_size=-3,  # ungültig
        )


def test_edge_reinforcement_validator():
    """EdgeReinforcement mit weight_after < weight_before muss ValidationError auslösen."""
    edge = _make_edge()
    with pytest.raises(ValidationError, match="weight_after"):
        EdgeReinforcement(
            edge=edge,
            weight_before=0.5,
            weight_after=0.3,  # kleiner als before — ungültig
            reinforced_count_before=2,
            reinforced_count_after=3,
        )


def test_edge_weakening_validator():
    """EdgeWeakening mit weight_after >= weight_before muss ValidationError auslösen."""
    edge = _make_edge()
    with pytest.raises(ValidationError, match="weight_after"):
        EdgeWeakening(
            edge=edge,
            weight_before=0.3,
            weight_after=0.7,  # größer als before — ungültig
            reinforced_count_before=3,
            reinforced_count_after=2,
        )
    # Gleiches Gewicht ist ebenfalls ungültig für Weakening
    with pytest.raises(ValidationError, match="weight_after"):
        EdgeWeakening(
            edge=edge,
            weight_before=0.5,
            weight_after=0.5,  # gleich — ungültig
            reinforced_count_before=2,
            reinforced_count_after=2,
        )


def test_bridge_action_literal():
    """Unbekannte action-Werte müssen abgelehnt werden; gültige Literale akzeptiert."""
    with pytest.raises(ValidationError):
        BridgeAgentShift(agent_id=1, action="invalid_action")

    # Beide gültigen Literale müssen funktionieren
    joined = BridgeAgentShift(agent_id=1, action="joined_top_k")
    assert joined.action == "joined_top_k"

    left = BridgeAgentShift(agent_id=2, action="left_top_k")
    assert left.action == "left_top_k"


def test_comparison_type_literal():
    """Unbekannte comparison_type-Werte müssen abgelehnt werden."""
    diff = _make_full_graph_diff()
    data = diff.model_dump()
    data["comparison_type"] = "invalid-type"
    with pytest.raises(ValidationError):
        GraphDiff.model_validate(data)

    # Beide gültigen Werte müssen akzeptiert werden
    for valid_type in ("round-to-round", "branch-diff"):
        data["comparison_type"] = valid_type
        result = GraphDiff.model_validate(data)
        assert result.comparison_type == valid_type


def test_empty_diff():
    """Minimaler GraphDiff ohne Diff-Einträge (alle Listen leer, Metriken 0) muss valide sein."""
    empty = GraphDiff(
        graph_id="g1",
        snapshot_a_id="snap-a",
        snapshot_b_id="snap-b",
        created_at="2026-05-03T12:00:00Z",
        comparison_type="round-to-round",
        snapshot_a=_make_snapshot(snapshot_id="snap-a"),
        snapshot_b=_make_snapshot(snapshot_id="snap-b"),
        metrics=_make_metrics(
            total_edges_added=0,
            total_edges_removed=0,
            total_edges_reinforced=0,
            total_edges_weakened=0,
            avg_reinforcement_delta=0.0,
            avg_weakening_delta=0.0,
            density_delta=0.0,
            node_properties_changed=0,
            agents_changed_clusters=0,
            clusters_new=0,
            clusters_removed=0,
            bridge_agents_joined=0,
            bridge_agents_left=0,
        ),
    )
    assert empty.edges_added == []
    assert empty.edges_reinforced == []
    assert empty.metrics.total_edges_added == 0


def test_schema_dump_idempotent():
    """model_json_schema() zweimal aufrufen muss identisches Dict liefern."""
    schema_1 = GraphDiff.model_json_schema()
    schema_2 = GraphDiff.model_json_schema()
    assert json.dumps(schema_1, sort_keys=True) == json.dumps(schema_2, sort_keys=True)
