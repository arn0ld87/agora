"""Unit tests for NetworkAnalyticsService (Issue #12).

Drives the service with hand-crafted action dicts that shape a known
interaction graph (two tight clusters, one bridge agent) and asserts
the polarization metrics reflect that topology.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.network_analytics import (
    METRICS_STATUS_NO_ACTIONS,
    METRICS_STATUS_NO_PAIRWISE,
    METRICS_STATUS_OK,
    NetworkAnalyticsService,
)


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


# --- S2-pre: real OASIS action_args schema ---------------------------------
#
# OASIS schreibt Target-Identitäten als *Strings* (`*_author_name`,
# `target_user_name`), nicht als numerische IDs. Diese Tests fixieren das
# Schema, das die Diagnose in `docs/archive/history/2026-05-01-metric-snapshot-diagnose.md`
# dokumentiert hat.


def _seed_alice_creates_post(post_author_id: int = 1) -> Dict[str, Any]:
    """Hilfs-Action: erzeugt eine Identitätsspur für `Alice` im name_to_id-Index."""
    return {
        "agent_id": post_author_id,
        "agent_name": "Alice",
        "action_type": "CREATE_POST",
        "action_args": {"content": "..."},
        "round": 0,
    }


def test_like_post_resolved_via_post_author_name():
    svc = NetworkAnalyticsService()
    actions = [
        _seed_alice_creates_post(),
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "LIKE_POST",
            "action_args": {
                "post_id": 1,
                "like_id": 1,
                "post_content": "...",
                "post_author_name": "Alice",
            },
            "round": 1,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 1
    assert m.total_agents == 2


def test_follow_resolved_via_target_user_name():
    svc = NetworkAnalyticsService()
    actions = [
        _seed_alice_creates_post(),
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "FOLLOW",
            "action_args": {"follow_id": 1, "target_user_name": "Alice"},
            "round": 1,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 1
    assert m.total_agents == 2


def test_repost_and_quote_post_resolved_via_original_author_name():
    svc = NetworkAnalyticsService()
    actions = [
        _seed_alice_creates_post(),
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "REPOST",
            "action_args": {
                "new_post_id": 2,
                "original_content": "...",
                "original_author_name": "Alice",
            },
            "round": 1,
        },
        {
            "agent_id": 3,
            "agent_name": "Carol",
            "action_type": "QUOTE_POST",
            "action_args": {
                "quoted_id": 1,
                "new_post_id": 3,
                "original_content": "...",
                "original_author_name": "Alice",
                "quote_content": "...",
            },
            "round": 2,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 2
    assert m.total_agents == 3


def test_like_comment_resolved_via_comment_id_index():
    svc = NetworkAnalyticsService()
    actions = [
        # Alice schreibt comment_id=42
        {
            "agent_id": 1,
            "agent_name": "Alice",
            "action_type": "CREATE_COMMENT",
            "action_args": {"content": "...", "comment_id": 42},
            "round": 0,
        },
        # Bob liked comment_id=42 — comment_author_name fehlt absichtlich,
        # damit der comment_id-Index als alleinige Auflösungsquelle greifen muss.
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "LIKE_COMMENT",
            "action_args": {"comment_id": 42, "comment_content": "..."},
            "round": 1,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 1
    assert m.total_agents == 2


def test_mute_without_target_is_ignored():
    svc = NetworkAnalyticsService()
    actions = [
        _seed_alice_creates_post(),
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "MUTE",
            "action_args": {},  # OASIS loggt MUTE ohne Target
            "round": 1,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 0


def test_unknown_author_name_skipped_not_crashing():
    svc = NetworkAnalyticsService()
    actions = [
        # Alice taucht im Index auf
        _seed_alice_creates_post(),
        # Aber Bob liked einen Post von "Eve" — die niemals eine Action geloggt hat
        {
            "agent_id": 2,
            "agent_name": "Bob",
            "action_type": "LIKE_POST",
            "action_args": {
                "post_id": 7,
                "post_author_name": "Eve",
            },
            "round": 1,
        },
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 0


# --- S2a: Status flag + snapshot metadata ----------------------------------


def test_status_no_actions_for_empty_input():
    svc = NetworkAnalyticsService()
    m = svc.compute_metrics([])

    assert m.status == METRICS_STATUS_NO_ACTIONS
    assert m.snapshot_id and m.snapshot_id.startswith("metrics_")
    assert m.calculated_at is not None


def test_status_no_pairwise_for_broadcast_only():
    svc = NetworkAnalyticsService()
    actions = [
        {"agent_id": 1, "agent_name": "Alice", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
        {"agent_id": 2, "agent_name": "Bob", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
    ]

    m = svc.compute_metrics(actions)

    assert m.status == METRICS_STATUS_NO_PAIRWISE
    assert m.total_interactions == 0
    assert m.snapshot_id and m.snapshot_id.startswith("metrics_")


def test_status_ok_when_interactions_present():
    svc = NetworkAnalyticsService()
    actions = [
        {"agent_id": 1, "agent_name": "Alice", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
        {"agent_id": 2, "agent_name": "Bob", "action_type": "LIKE_POST",
         "action_args": {"post_id": 1, "post_author_name": "Alice"}, "round": 1},
    ]

    m = svc.compute_metrics(actions)

    assert m.status == METRICS_STATUS_OK
    assert m.total_interactions == 1


def test_to_dict_includes_status_and_metadata():
    svc = NetworkAnalyticsService()
    d = svc.compute_metrics([], simulation_id="sim_xyz").to_dict()

    assert d["status"] == METRICS_STATUS_NO_ACTIONS
    assert d["snapshot_id"].startswith("metrics_")
    assert d["calculated_at"] is not None


def test_full_oasis_run_mixed_directed_actions():
    """Smoke-Test mit dem typischen OASIS-Mix aus directed actions und
    CREATE_POST-Broadcasts. Drei Agents in zwei Clustern."""
    svc = NetworkAnalyticsService()
    actions = [
        # Alle drei publishen Posts (broadcast, ignoriert für Metriken).
        {"agent_id": 1, "agent_name": "Alice", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
        {"agent_id": 2, "agent_name": "Bob", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
        {"agent_id": 3, "agent_name": "Carol", "action_type": "CREATE_POST",
         "action_args": {"content": "..."}, "round": 0},
        # Bob<->Alice und Bob->Carol per LIKE/FOLLOW.
        {"agent_id": 2, "agent_name": "Bob", "action_type": "LIKE_POST",
         "action_args": {"post_id": 1, "post_author_name": "Alice"}, "round": 1},
        {"agent_id": 1, "agent_name": "Alice", "action_type": "FOLLOW",
         "action_args": {"target_user_name": "Bob"}, "round": 1},
        {"agent_id": 2, "agent_name": "Bob", "action_type": "FOLLOW",
         "action_args": {"target_user_name": "Carol"}, "round": 2},
    ]

    m = svc.compute_metrics(actions)

    assert m.total_interactions == 3
    assert m.total_agents == 3
    assert m.cluster_count >= 1


# --- Task 14: Cluster-Label Integration ------------------------------------


def test_cluster_label_set_when_post_content_present():
    """compute_metrics setzt dominant_clusters[*].label auf nicht-leeren String,
    wenn Member-Actions post_content-Felder tragen."""
    svc = NetworkAnalyticsService()
    actions: List[Dict[str, Any]] = []
    # Zwei Agents bilden durch gegenseitiges FOLLOW eine Cluster.
    for src, tgt in ((1, 2), (2, 1)):
        actions.append(_follow(src, tgt))
    # Zusaetzlich Posts mit Text, damit _derive_cluster_label etwas findet.
    actions.append({"agent_id": 1, "action_type": "CREATE_POST",
                    "action_args": {}, "post_content": "klimawandel energie solar"})
    actions.append({"agent_id": 2, "action_type": "CREATE_POST",
                    "action_args": {}, "post_content": "klimawandel erneuerbar"})

    m = svc.compute_metrics(actions)

    assert m.cluster_count >= 1
    for cluster in m.dominant_clusters:
        assert cluster.label != "", f"Cluster {cluster.cluster_id} hat kein Label"
        # Label darf keine deutschen Stoppwoerter enthalten.
        for part in cluster.label.split(", "):
            assert part not in {"der", "die", "und", "ist"}


def test_cluster_label_in_to_dict():
    """to_dict() exponiert das label-Feld jedes Clusters."""
    svc = NetworkAnalyticsService()
    actions = [
        _follow(1, 2), _follow(2, 1),
        {"agent_id": 1, "post_content": "testlabel testlabel testlabel"},
    ]
    d = svc.compute_metrics(actions).to_dict()
    for cluster_dict in d["dominant_clusters"]:
        assert "label" in cluster_dict
