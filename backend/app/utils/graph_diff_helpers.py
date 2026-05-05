"""Hilfsfunktionen für die Konvertierung von TemporalGraphService-Dataclasses
in Pydantic-Layer-0-Contracts (Sub-Slice 22, Closes #74).

Alle Funktionen sind zustandslos und importieren ausschließlich aus
``app.contracts`` — niemals direkt aus Submodulen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..contracts import (
    EdgeData,
    EdgeReinforcement,
    GraphDiff,
    GraphDiffMetrics,
    GraphSnapshot,
)


def _edge_to_contract(edge: dict[str, Any]) -> EdgeData:
    """Konvertiert ein Edge-Dict aus TemporalGraphService in EdgeData."""
    uuid_val = str(
        edge.get("uuid") or edge.get("id")
        or f"{edge.get('source_id', '?')}-{edge.get('target_id', '?')}"
    )
    source_id = str(edge.get("source_id") or edge.get("source") or "")
    target_id = str(edge.get("target_id") or edge.get("target") or "")
    relation_type = str(edge.get("relation_type") or edge.get("type") or "UNKNOWN")

    weight_raw = edge.get("weight")
    weight = float(weight_raw) if weight_raw is not None else None

    rc_raw = edge.get("reinforced_count")
    reinforced_count = int(rc_raw) if rc_raw is not None else None

    _skip = frozenset((
        "uuid", "id",
        "source_id", "source",
        "target_id", "target",
        "relation_type", "type",
        "weight",
        "reinforced_count",
        "valid_from_round", "valid_to_round",
        "graph_id",
        "reinforced_before", "reinforced_after",
    ))
    properties: dict[str, str | int | float | bool] = {
        k: v
        for k, v in edge.items()
        if k not in _skip and isinstance(v, (str, int, float, bool))
    }

    return EdgeData(
        uuid=uuid_val,
        source_id=source_id,
        target_id=target_id,
        relation_type=relation_type,
        weight=weight,
        reinforced_count=reinforced_count,
        properties=properties,
    )


def _reinforced_to_contract(r: dict[str, Any]) -> EdgeReinforcement:
    """Konvertiert ein Reinforcement-Dict aus TemporalGraphService in EdgeReinforcement."""
    rc_before = int(r.get("reinforced_before") or 1)
    rc_after = int(r.get("reinforced_after") or rc_before)

    w_before = float(r.get("weight") or rc_before)
    w_after = float(r.get("weight") or rc_after)

    # EdgeReinforcement-Validator erfordert weight_after >= weight_before.
    # Wenn reinforced_count gestiegen ist, spiegeln wir das im Gewicht wider.
    if rc_after > rc_before and w_after <= w_before:
        w_after = w_before + float(rc_after - rc_before)

    # Sicherheitsnetz: weight_after darf nie kleiner als weight_before sein.
    if w_after < w_before:
        w_after = w_before

    return EdgeReinforcement(
        edge=_edge_to_contract(r),
        weight_before=w_before,
        weight_after=w_after,
        reinforced_count_before=rc_before,
        reinforced_count_after=rc_after,
    )


def _snapshot_to_contract(
    snap: Any,
    graph_id: str,
    round_num: int,
) -> GraphSnapshot:
    """Konvertiert einen Service-GraphSnapshot in den Pydantic-Contract GraphSnapshot.

    node_count wird aus den eindeutigen source_id/target_id-Werten der Kanten
    geschätzt (Phase-2: exakter Node-Count via eigene Storage-Abfrage).
    """
    edges_data: list[EdgeData] = [_edge_to_contract(e) for e in snap.edges]
    edge_count = len(edges_data)

    node_ids: set[str] = set()
    for e in snap.edges:
        src = str(e.get("source_id") or e.get("source") or "")
        tgt = str(e.get("target_id") or e.get("target") or "")
        if src:
            node_ids.add(src)
        if tgt:
            node_ids.add(tgt)

    node_count = len(node_ids)
    max_edges = node_count * (node_count - 1) if node_count > 1 else 1
    density = round(edge_count / max_edges, 6) if max_edges > 0 else 0.0
    density = min(1.0, max(0.0, density))

    return GraphSnapshot(
        graph_id=graph_id,
        round_num=round_num,
        snapshot_id=f"{graph_id}:round:{round_num}",
        created_at=datetime.now(tz=timezone.utc),
        node_count=node_count,
        edge_count=edge_count,
        density=density,
        cluster_count=0,         # Phase-2: Louvain-Clustering
        dominant_clusters=[],    # Phase-2
        bridge_agents=[],        # Phase-2: Betweenness-Centrality
        edges=edges_data,
    )


def _compute_metrics(
    edges_added: list[EdgeData],
    edges_removed: list[EdgeData],
    edges_reinforced: list[EdgeReinforcement],
    edges_weakened: list[Any],
    snap_a: GraphSnapshot,
    snap_b: GraphSnapshot,
) -> GraphDiffMetrics:
    """Berechnet aggregierte GraphDiffMetrics aus den Diff-Listen."""
    avg_reinf_delta = 0.0
    if edges_reinforced:
        avg_reinf_delta = sum(
            e.weight_after - e.weight_before for e in edges_reinforced
        ) / len(edges_reinforced)

    avg_weak_delta = 0.0
    if edges_weakened:
        avg_weak_delta = sum(
            e.weight_after - e.weight_before for e in edges_weakened
        ) / len(edges_weakened)

    density_delta = round(snap_b.density - snap_a.density, 6)

    return GraphDiffMetrics(
        total_edges_added=len(edges_added),
        total_edges_removed=len(edges_removed),
        total_edges_reinforced=len(edges_reinforced),
        total_edges_weakened=len(edges_weakened),
        avg_reinforcement_delta=avg_reinf_delta,
        avg_weakening_delta=avg_weak_delta,
        density_delta=density_delta,
        node_properties_changed=0,    # Phase-2
        agents_changed_clusters=0,    # Phase-2
        clusters_new=0,               # Phase-2
        clusters_removed=0,           # Phase-2
        bridge_agents_joined=0,       # Phase-2
        bridge_agents_left=0,         # Phase-2
    )


def build_pydantic_graph_diff(
    service_diff: Any,
    snap_a: Any,
    snap_b: Any,
    graph_id: str,
    start_round: int,
    end_round: int,
) -> GraphDiff:
    """Baut ein vollständiges PydanticGraphDiff aus Service-Objekten zusammen.

    Args:
        service_diff: TemporalGraphService.GraphDiff-Dataclass-Instanz.
        snap_a:       TemporalGraphService.GraphSnapshot für start_round.
        snap_b:       TemporalGraphService.GraphSnapshot für end_round.
        graph_id:     Graph-ID als String.
        start_round:  Startrunde (int).
        end_round:    Endrunde (int).

    Returns:
        Vollständig valides ``app.contracts.GraphDiff``-Pydantic-Objekt.
    """
    edges_added = [_edge_to_contract(e) for e in service_diff.added]
    edges_removed = [_edge_to_contract(e) for e in service_diff.removed]
    edges_reinforced = [_reinforced_to_contract(r) for r in service_diff.reinforced]
    edges_weakened: list[Any] = []  # Phase-2: TemporalGraphService kennt noch keine geschwächten Kanten

    pydantic_snap_a = _snapshot_to_contract(snap_a, graph_id, start_round)
    pydantic_snap_b = _snapshot_to_contract(snap_b, graph_id, end_round)
    metrics = _compute_metrics(
        edges_added, edges_removed, edges_reinforced, edges_weakened,
        pydantic_snap_a, pydantic_snap_b,
    )

    return GraphDiff(
        graph_id=graph_id,
        snapshot_a_id=pydantic_snap_a.snapshot_id or f"{graph_id}:round:{start_round}",
        snapshot_b_id=pydantic_snap_b.snapshot_id or f"{graph_id}:round:{end_round}",
        created_at=datetime.now(tz=timezone.utc),
        comparison_type="round-to-round",
        snapshot_a=pydantic_snap_a,
        snapshot_b=pydantic_snap_b,
        edges_added=edges_added,
        edges_removed=edges_removed,
        edges_reinforced=edges_reinforced,
        edges_weakened=edges_weakened,
        node_properties_changed=[],   # Phase-2
        cluster_shifts=[],            # Phase-2
        clusters_new=[],              # Phase-2
        clusters_removed=[],          # Phase-2
        bridge_agent_shifts=[],       # Phase-2
        metrics=metrics,
    )


__all__ = [
    "build_pydantic_graph_diff",
    "_edge_to_contract",
    "_reinforced_to_contract",
    "_snapshot_to_contract",
    "_compute_metrics",
]
