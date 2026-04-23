"""Unit tests for NetworkAnalyticsService (Issue #12).

Drives the service with hand-crafted action dicts that shape a known
interaction graph (two tight clusters, one bridge agent) and asserts
the polarization metrics reflect that topology.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.network_analytics import NetworkAnalyticsService


def _follow(src: int, tgt: int, round_num: int = 0) -> Dict[str, Any]:
    return {
        "agent_id": src,
        "action_type": "FOLLOW",
        "action_args": {"followee_id": tgt},
        "round": round_num,
    }


def _like(src: int, tgt: int, round_num: int = 0) -> Dict[str, Any]:
    return {
        "agent_id": src,
        "action_type": "LIKE_POST",
        "action_args": {"author_id": tgt},
        "round": round_num,
    }


def test_empty_input_returns_zeros():
    svc = NetworkAnalyticsService()
    m = svc.compute_metrics([])

    assert m.total_agents == 0
    assert m.total_interactions == 0
    assert m.cluster_count == 0
    assert m.echo_chamber_index == 0.0
    assert m.bridge_agents == []


def test_single_agent_no_interactions():
    svc = NetworkAnalyticsService()
    # Self-follow is filtered out; CREATE_POST isn't an interaction.
    actions = [
        {"agent_id": 1, "action_type": "CREATE_POST", "action_args": {}},
        _follow(1, 1),
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 0
    assert m.cluster_count == 0


def test_two_tight_clusters_with_bridge():
    svc = NetworkAnalyticsService(top_bridge_k=3)
    actions: List[Dict[str, Any]] = []
    # Cluster A: 1, 2, 3 all follow each other.
    for src in (1, 2, 3):
        for tgt in (1, 2, 3):
            if src != tgt:
                actions.append(_follow(src, tgt))
    # Cluster B: 4, 5, 6 all follow each other.
    for src in (4, 5, 6):
        for tgt in (4, 5, 6):
            if src != tgt:
                actions.append(_follow(src, tgt))
    # Bridge: agent 7 follows one member of each cluster, and one member
    # of each cluster follows 7 back.
    actions.append(_follow(7, 1))
    actions.append(_follow(1, 7))
    actions.append(_follow(7, 4))
    actions.append(_follow(4, 7))

    m = svc.compute_metrics(actions)

    # We expect at least 2 distinct clusters; Louvain could split the
    # bridge into its own singleton, so allow 2 or 3.
    assert m.cluster_count >= 2
    # 7 should be among the top bridge agents because it sits between
    # two dense clusters and has high betweenness.
    assert 7 in m.bridge_agents
    # Echo-chamber index is high because the vast majority of edges are
    # intra-cluster (cluster A + cluster B dominate the bridge edges).
    assert m.echo_chamber_index > 0.5


def test_window_filters_old_rounds():
    svc = NetworkAnalyticsService()
    actions = [
        _follow(1, 2, round_num=1),
        _follow(3, 4, round_num=5),
        _follow(5, 6, round_num=10),
    ]

    m = svc.compute_metrics(actions, window_size_rounds=3)

    # Only rounds 8,9,10 are in scope → just the 5→6 follow remains.
    assert m.total_interactions == 1


def test_broadcast_actions_ignored():
    svc = NetworkAnalyticsService()
    actions = [
        {
            "agent_id": 1,
            "action_type": "CREATE_POST",
            "action_args": {"content": "hi"},
            "round": 0,
        },
        {
            "agent_id": 2,
            "action_type": "DO_NOTHING",
            "action_args": {},
            "round": 0,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 0


def test_metrics_to_dict_shape():
    svc = NetworkAnalyticsService()
    actions = [_follow(1, 2), _follow(2, 1)]
    m = svc.compute_metrics(actions, simulation_id="sim_abc").to_dict()

    assert m["simulation_id"] == "sim_abc"
    assert "echo_chamber_index" in m
    assert "dominant_clusters" in m
    assert "bridge_agents" in m


def test_interactions_without_target_ignored():
    svc = NetworkAnalyticsService()
    actions = [
        {
            "agent_id": 1,
            "action_type": "LIKE_POST",
            "action_args": {"post_id": 42},  # no author_id → unusable
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 0
