"""NetworkAnalyticsService — polarization & bridge-agent metrics (Issue #12).

Builds an agent-interaction DiGraph from OASIS simulation actions
(``FOLLOW``, ``LIKE_POST``, ``DISLIKE_POST``, ``REPOST``, ``CREATE_COMMENT``,
``LIKE_COMMENT``, ``DISLIKE_COMMENT``) and runs two off-the-shelf analyses:

* **Louvain community detection** over the (symmetrised) interaction graph
  → ``dominant_clusters``.
* **Betweenness centrality** on the same undirected projection → the top
  *k* agents with the highest centrality *who sit on edges between two
  different clusters* → ``bridge_agents``.

The **echo-chamber index** is the share of interactions that stay within
a single community (``intra-cluster / total``). 1.0 means everyone only
talks to their own tribe, 0.0 is a fully integrated network.

The service is stateless: callers pass the action list in and get a
``PolarizationMetrics`` DTO back. An optional sliding window restricts
analysis to the last ``window_size_rounds`` rounds; 0 or ``None`` disables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ..utils.logger import get_logger

logger = get_logger("agora.network_analytics")


# Interaction types and their target-agent extraction strategy. Everything
# not in this map is ignored (CREATE_POST etc. — those are broadcasts,
# not pairwise interactions).
_DIRECTED_ACTIONS = {
    "FOLLOW",
    "LIKE_POST",
    "DISLIKE_POST",
    "REPOST",
    "CREATE_COMMENT",
    "LIKE_COMMENT",
    "DISLIKE_COMMENT",
    "MUTE",
    "QUOTE_POST",
}


@dataclass
class ClusterDef:
    cluster_id: int
    size: int
    agent_ids: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "size": self.size,
            "agent_ids": self.agent_ids,
        }


@dataclass
class PolarizationMetrics:
    simulation_id: Optional[str] = None
    window_size_rounds: Optional[int] = None
    total_agents: int = 0
    total_interactions: int = 0
    echo_chamber_index: float = 0.0
    cluster_count: int = 0
    dominant_clusters: List[ClusterDef] = field(default_factory=list)
    bridge_agents: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "window_size_rounds": self.window_size_rounds,
            "total_agents": self.total_agents,
            "total_interactions": self.total_interactions,
            "echo_chamber_index": round(self.echo_chamber_index, 4),
            "cluster_count": self.cluster_count,
            "dominant_clusters": [c.to_dict() for c in self.dominant_clusters],
            "bridge_agents": self.bridge_agents,
        }


def _extract_target_agent(action: Dict[str, Any]) -> Optional[int]:
    """Best-effort pull of the target agent id from an action dict.

    Reddit/Twitter logs store the target under different keys depending on
    the action type. Falling back to a broad set of likely fields avoids
    having to hard-code platform schemas.
    """
    args = action.get("action_args") or {}
    for key in (
        "target_agent_id",
        "followee_id",
        "user_id",
        "target_user_id",
        "author_id",
    ):
        val = args.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    # Some logs reference a post/comment id instead of a user id. Those are
    # broadcast-ish interactions for polarization purposes — skip them.
    return None


class NetworkAnalyticsService:
    """Compute polarization metrics from a list of OASIS action dicts."""

    def __init__(self, top_bridge_k: int = 5) -> None:
        self._top_k = max(1, top_bridge_k)

    # -- public -----------------------------------------------------------

    def compute_metrics(
        self,
        actions: Iterable[Dict[str, Any]],
        *,
        simulation_id: Optional[str] = None,
        window_size_rounds: Optional[int] = None,
    ) -> PolarizationMetrics:
        actions = list(actions)
        if window_size_rounds and window_size_rounds > 0 and actions:
            max_round = max(int(a.get("round") or a.get("round_num") or 0) for a in actions)
            cutoff = max_round - window_size_rounds + 1
            actions = [
                a
                for a in actions
                if int(a.get("round") or a.get("round_num") or 0) >= cutoff
            ]

        interactions = list(self._iter_interactions(actions))
        if not interactions:
            return PolarizationMetrics(
                simulation_id=simulation_id,
                window_size_rounds=window_size_rounds,
            )

        clusters, bridges, echo, total_agents = self._analyse(interactions)

        return PolarizationMetrics(
            simulation_id=simulation_id,
            window_size_rounds=window_size_rounds,
            total_agents=total_agents,
            total_interactions=len(interactions),
            echo_chamber_index=echo,
            cluster_count=len(clusters),
            dominant_clusters=clusters,
            bridge_agents=bridges,
        )

    # -- internals --------------------------------------------------------

    def _iter_interactions(
        self, actions: Iterable[Dict[str, Any]]
    ) -> Iterable[Tuple[int, int]]:
        for action in actions:
            action_type = (action.get("action_type") or "").upper()
            if action_type not in _DIRECTED_ACTIONS:
                continue
            src = action.get("agent_id")
            if src is None:
                continue
            try:
                src_id = int(src)
            except (TypeError, ValueError):
                continue
            tgt_id = _extract_target_agent(action)
            if tgt_id is None or tgt_id == src_id:
                continue
            yield src_id, tgt_id

    def _analyse(
        self,
        interactions: List[Tuple[int, int]],
    ) -> Tuple[List[ClusterDef], List[int], float, int]:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        # Undirected weighted projection — edge weight = interaction count.
        graph = nx.Graph()
        for src, tgt in interactions:
            if graph.has_edge(src, tgt):
                graph[src][tgt]["weight"] += 1
            else:
                graph.add_edge(src, tgt, weight=1)

        if graph.number_of_edges() == 0:
            return [], [], 0.0, graph.number_of_nodes()

        # Louvain communities. Reproducible with a fixed seed so two runs
        # on identical data give the same cluster ids.
        communities = louvain_communities(graph, weight="weight", seed=42)

        agent_to_cluster: Dict[int, int] = {}
        clusters: List[ClusterDef] = []
        for idx, members in enumerate(sorted(communities, key=len, reverse=True)):
            member_ids = sorted(int(m) for m in members)
            for m in member_ids:
                agent_to_cluster[m] = idx
            clusters.append(
                ClusterDef(cluster_id=idx, size=len(member_ids), agent_ids=member_ids)
            )

        # Echo-chamber index = share of weighted interactions within the
        # same cluster (intra / total).
        intra = 0
        total = 0
        for src, tgt in interactions:
            total += 1
            if agent_to_cluster.get(src) == agent_to_cluster.get(tgt):
                intra += 1
        echo = intra / total if total else 0.0

        # Bridge agents: top-k betweenness AND at least one neighbour in a
        # different cluster (otherwise "bridge" is misleading).
        bc = nx.betweenness_centrality(graph, weight="weight", normalized=True)
        candidates: List[Tuple[int, float]] = []
        for node, score in bc.items():
            neighbours: Set[int] = set(graph.neighbors(node))
            own_cluster = agent_to_cluster.get(int(node))
            bridges_to = {
                agent_to_cluster.get(int(n))
                for n in neighbours
                if agent_to_cluster.get(int(n)) != own_cluster
            }
            if bridges_to:
                candidates.append((int(node), float(score)))
        candidates.sort(key=lambda t: t[1], reverse=True)
        bridge_ids = [c[0] for c in candidates[: self._top_k]]

        return clusters, bridge_ids, echo, graph.number_of_nodes()


__all__ = [
    "NetworkAnalyticsService",
    "PolarizationMetrics",
    "ClusterDef",
]
