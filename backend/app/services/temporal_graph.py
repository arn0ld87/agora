"""TemporalGraphService — time-travel queries on the knowledge graph (Issue #10).

Builds on the ``valid_from_round`` / ``valid_to_round`` / ``reinforced_count``
properties that :class:`Neo4jStorage` now stamps on RELATION edges:

* :meth:`get_snapshot` — edges that were live at a given OASIS round.
* :meth:`compute_diff` — added / removed / reinforced edges between two rounds.

Pre-existing graphs predate these properties. The service calls the
storage's idempotent ``backfill_temporal_defaults`` on first use per
graph to stamp legacy edges with ``valid_from_round=0``. Subsequent
calls are no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from ..storage import GraphStorage
from ..utils.logger import get_logger

logger = get_logger("agora.temporal_graph")


@dataclass
class GraphSnapshot:
    graph_id: str
    round_num: int
    edges: List[Dict[str, Any]] = field(default_factory=list)

    def edge_ids(self) -> Set[str]:
        return {e.get("uuid") for e in self.edges if e.get("uuid")}

    def edges_by_uuid(self) -> Dict[str, Dict[str, Any]]:
        return {e["uuid"]: e for e in self.edges if e.get("uuid")}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "round_num": self.round_num,
            "edges": self.edges,
            "edge_count": len(self.edges),
        }


@dataclass
class GraphDiff:
    graph_id: str
    start_round: int
    end_round: int
    added: List[Dict[str, Any]] = field(default_factory=list)
    removed: List[Dict[str, Any]] = field(default_factory=list)
    reinforced: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "start_round": self.start_round,
            "end_round": self.end_round,
            "added_count": len(self.added),
            "removed_count": len(self.removed),
            "reinforced_count": len(self.reinforced),
            "added": self.added,
            "removed": self.removed,
            "reinforced": self.reinforced,
        }


class TemporalGraphService:
    """Read-only time-travel service on top of :class:`GraphStorage`."""

    def __init__(self, storage: GraphStorage) -> None:
        self._storage = storage
        self._backfilled_graphs: Set[str] = set()

    def ensure_backfilled(self, graph_id: str) -> int:
        """Run the one-shot temporal migration on first access per graph."""
        if graph_id in self._backfilled_graphs:
            return 0
        try:
            touched = self._storage.backfill_temporal_defaults(graph_id)
            if touched:
                logger.info(
                    "Temporal backfill stamped %d RELATION edges in graph %s",
                    touched,
                    graph_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Temporal backfill failed for %s: %s", graph_id, exc)
            touched = 0
        self._backfilled_graphs.add(graph_id)
        return touched

    def get_snapshot(self, graph_id: str, round_num: int) -> GraphSnapshot:
        self.ensure_backfilled(graph_id)
        if round_num < 0:
            raise ValueError(f"round_num must be >= 0 (got {round_num})")
        edges = self._storage.get_edges_at_round(graph_id, round_num)
        return GraphSnapshot(graph_id=graph_id, round_num=round_num, edges=edges)

    def compute_diff(
        self,
        graph_id: str,
        start_round: int,
        end_round: int,
    ) -> GraphDiff:
        """Return edges that changed state between ``start_round`` and ``end_round``.

        * **added** — live at ``end_round`` but not at ``start_round``.
        * **removed** — live at ``start_round`` but not at ``end_round``.
        * **reinforced** — live in both snapshots with a higher
          ``reinforced_count`` at ``end_round``.
        """
        if end_round < start_round:
            raise ValueError(
                f"end_round ({end_round}) must be >= start_round ({start_round})"
            )

        start = self.get_snapshot(graph_id, start_round)
        end = self.get_snapshot(graph_id, end_round)
        start_ids = start.edge_ids()
        end_ids = end.edge_ids()
        start_by_uuid = start.edges_by_uuid()
        end_by_uuid = end.edges_by_uuid()

        added = [end_by_uuid[u] for u in end_ids - start_ids]
        removed = [start_by_uuid[u] for u in start_ids - end_ids]

        reinforced: List[Dict[str, Any]] = []
        for uuid_ in start_ids & end_ids:
            before = start_by_uuid[uuid_].get("reinforced_count") or 1
            after = end_by_uuid[uuid_].get("reinforced_count") or 1
            if after > before:
                reinforced.append(
                    {
                        **end_by_uuid[uuid_],
                        "reinforced_before": before,
                        "reinforced_after": after,
                    }
                )

        return GraphDiff(
            graph_id=graph_id,
            start_round=start_round,
            end_round=end_round,
            added=added,
            removed=removed,
            reinforced=reinforced,
        )


__all__ = ["TemporalGraphService", "GraphSnapshot", "GraphDiff"]
