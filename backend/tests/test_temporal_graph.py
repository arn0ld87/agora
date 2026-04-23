"""Unit tests for TemporalGraphService (Issue #10).

These tests use a stub :class:`GraphStorage` so they don't need Neo4j —
they cover the service's snapshot + diff semantics against a known edge
set. Integration against a live Neo4j is validated by the existing
``tests/test_neo4j_resilience.py`` stack.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.temporal_graph import TemporalGraphService


class StubStorage:
    """Minimal in-memory stand-in for GraphStorage."""

    def __init__(self) -> None:
        self.edges: List[Dict[str, Any]] = []
        self.backfill_calls = 0

    def get_edges_at_round(self, graph_id: str, round_num: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for e in self.edges:
            if e.get("graph_id") != graph_id:
                continue
            vfr = e.get("valid_from_round")
            vtr = e.get("valid_to_round")
            vfr_eff = 0 if vfr is None else vfr
            if vfr_eff > round_num:
                continue
            if vtr is not None and vtr <= round_num:
                continue
            out.append({k: v for k, v in e.items() if k != "graph_id"})
        return out

    def backfill_temporal_defaults(self, graph_id: Optional[str] = None) -> int:
        self.backfill_calls += 1
        return 0


GRAPH = "abcdef012345abcdef012345abcdef01"


def _edge(
    uuid: str,
    vfr: Optional[int],
    vtr: Optional[int] = None,
    reinforced: int = 1,
) -> Dict[str, Any]:
    return {
        "graph_id": GRAPH,
        "uuid": uuid,
        "name": "RELATION",
        "fact": f"edge {uuid}",
        "valid_from_round": vfr,
        "valid_to_round": vtr,
        "reinforced_count": reinforced,
    }


def test_snapshot_includes_legacy_edges_with_null_valid_from_round():
    storage = StubStorage()
    storage.edges = [_edge("e1", None), _edge("e2", 5)]
    service = TemporalGraphService(storage)

    snap = service.get_snapshot(GRAPH, round_num=3)

    ids = {e["uuid"] for e in snap.edges}
    # e1 (legacy) is treated as valid_from_round=0 and still live at round 3.
    # e2 (valid_from_round=5) is not yet live at round 3.
    assert ids == {"e1"}


def test_snapshot_respects_valid_to_round():
    storage = StubStorage()
    storage.edges = [_edge("e1", 2, vtr=5), _edge("e2", 2, vtr=None)]
    service = TemporalGraphService(storage)

    assert {e["uuid"] for e in service.get_snapshot(GRAPH, 4).edges} == {"e1", "e2"}
    assert {e["uuid"] for e in service.get_snapshot(GRAPH, 5).edges} == {"e2"}


def test_diff_detects_added_removed_reinforced():
    storage = StubStorage()
    # Live in both rounds, reinforced_count bumped.
    storage.edges.append(_edge("stable", 0, reinforced=1))
    storage.edges.append(_edge("reinforced", 0, reinforced=1))
    # Added between 2 and 5.
    storage.edges.append(_edge("new", 4))
    # Removed between 2 and 5.
    storage.edges.append(_edge("gone", 0, vtr=3))

    service = TemporalGraphService(storage)

    # Simulate the reinforcement by swapping the stored reinforced_count
    # based on which round is being queried.
    original_get = storage.get_edges_at_round

    def get_edges_at_round(graph_id: str, round_num: int):
        edges = original_get(graph_id, round_num)
        for e in edges:
            if e["uuid"] == "reinforced":
                e["reinforced_count"] = 5 if round_num >= 4 else 1
        return edges

    storage.get_edges_at_round = get_edges_at_round  # type: ignore[assignment]

    diff = service.compute_diff(GRAPH, 2, 5)

    assert {e["uuid"] for e in diff.added} == {"new"}
    assert {e["uuid"] for e in diff.removed} == {"gone"}
    reinforced_ids = {e["uuid"] for e in diff.reinforced}
    assert reinforced_ids == {"reinforced"}
    r = next(e for e in diff.reinforced if e["uuid"] == "reinforced")
    assert r["reinforced_before"] == 1
    assert r["reinforced_after"] == 5


def test_backfill_runs_once_per_graph():
    storage = StubStorage()
    service = TemporalGraphService(storage)

    service.ensure_backfilled(GRAPH)
    service.ensure_backfilled(GRAPH)
    service.ensure_backfilled(GRAPH)

    assert storage.backfill_calls == 1


def test_diff_rejects_inverted_range():
    storage = StubStorage()
    service = TemporalGraphService(storage)

    with pytest.raises(ValueError):
        service.compute_diff(GRAPH, 5, 2)


def test_snapshot_rejects_negative_round():
    service = TemporalGraphService(StubStorage())
    with pytest.raises(ValueError):
        service.get_snapshot(GRAPH, -1)


def test_snapshot_serializes_to_dict():
    storage = StubStorage()
    storage.edges = [_edge("e1", 0)]
    service = TemporalGraphService(storage)

    payload = service.get_snapshot(GRAPH, 0).to_dict()

    assert payload["graph_id"] == GRAPH
    assert payload["round_num"] == 0
    assert payload["edge_count"] == 1
    assert payload["edges"][0]["uuid"] == "e1"
