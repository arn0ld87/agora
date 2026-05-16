"""
Contract-Tests für branch_comparison.py — gegen den echten Vertrag,
nicht gegen die Implementierung.

Datenquelle für Fixtures: docs/2026-05-03-task-23-compare-model-spike.md § 4
(JSON-Response-Beispiel, leicht vereinfacht für Unit-Tests).
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.contracts.branch_comparison import (
    BranchComparison,
    BranchMetrics,
    ClusterChange,
    ComparisonDeltas,
    SegmentReach,
)
from app.contracts.graph_diff import ClusterSummary


# ---------------------------------------------------------------------------
# Hilfsfunktionen / Fixtures
# ---------------------------------------------------------------------------

def _make_segment_reach(
    segment_name: str = "Politik",
    active_count: int = 8,
    total_count: int = 10,
    ratio: float = 0.8,
) -> SegmentReach:
    return SegmentReach(
        segment_name=segment_name,
        active_count=active_count,
        total_count=total_count,
        ratio=ratio,
    )


def _make_branch_metrics(
    echo_chamber_index: float = 0.62,
    cluster_count: int = 3,
    bridge_agent_ids: list[int] | None = None,
    total_agents: int = 38,
    total_interactions: int = 287,
    interaction_density: float = 3.58,
    avg_evidence_per_claim: float = 2.1,
    claims_without_evidence_ratio: float = 0.08,
    contradiction_ratio: float = 0.02,
) -> BranchMetrics:
    return BranchMetrics(
        echo_chamber_index=echo_chamber_index,
        cluster_count=cluster_count,
        dominant_clusters=[
            ClusterSummary(cluster_id=0, size=18, label="energiepolitik, diskurs, europaeisch", member_count=18),
            ClusterSummary(cluster_id=1, size=12, label="finanzmarkt, handel, europa", member_count=12),
            ClusterSummary(cluster_id=2, size=8, label="digital, datenschutz, reform", member_count=8),
        ],
        bridge_agent_ids=bridge_agent_ids if bridge_agent_ids is not None else [5, 12, 18],
        total_agents=total_agents,
        total_interactions=total_interactions,
        interaction_density=interaction_density,
        confidence_distribution={"low": 3, "medium": 8, "high": 12, "verified": 1},
        avg_evidence_per_claim=avg_evidence_per_claim,
        claims_without_evidence_ratio=claims_without_evidence_ratio,
        contradiction_ratio=contradiction_ratio,
        persona_reach={
            "Politik": _make_segment_reach("Politik", 8, 10, 0.8),
            "Medien": _make_segment_reach("Medien", 6, 8, 0.75),
            "Akademie": _make_segment_reach("Akademie", 4, 5, 0.8),
        },
    )


def _make_metrics_b() -> BranchMetrics:
    return BranchMetrics(
        echo_chamber_index=0.71,
        cluster_count=4,
        dominant_clusters=[
            ClusterSummary(cluster_id=0, size=20, label="energiepolitik, fossil, transition", member_count=20),
            ClusterSummary(cluster_id=1, size=10, label="finanzmarkt, gruen, esg", member_count=10),
            ClusterSummary(cluster_id=2, size=6, label="digital, blockchain, web3", member_count=6),
            ClusterSummary(cluster_id=3, size=5, label="klima, migration, sozialpolitik", member_count=5),
        ],
        bridge_agent_ids=[3, 7, 15, 22],
        total_agents=41,
        total_interactions=312,
        interaction_density=3.9,
        confidence_distribution={"low": 2, "medium": 7, "high": 14, "verified": 3},
        avg_evidence_per_claim=2.4,
        claims_without_evidence_ratio=0.05,
        contradiction_ratio=0.01,
        persona_reach={
            "Politik": _make_segment_reach("Politik", 9, 10, 0.9),
            "Medien": _make_segment_reach("Medien", 7, 8, 0.875),
            "Akademie": _make_segment_reach("Akademie", 5, 5, 1.0),
        },
    )


def _make_deltas() -> ComparisonDeltas:
    return ComparisonDeltas(
        echo_chamber_delta=0.09,
        cluster_delta=1,
        bridge_agents_delta=1,
        confidence_distribution_delta={"low": -1, "medium": -1, "high": 2, "verified": 2},
        avg_evidence_delta=0.3,
        contradiction_ratio_delta=-0.01,
        interaction_density_delta=0.32,
        clusters_only_in_a=[],
        clusters_only_in_b=[
            ClusterSummary(cluster_id=3, size=5, label="klima, migration, sozialpolitik", member_count=5),
        ],
        clusters_changed=[
            ClusterChange(
                cluster_id=0,
                size_a=18,
                size_b=20,
                label_a="energiepolitik, diskurs, europaeisch",
                label_b="energiepolitik, fossil, transition",
            )
        ],
    )


def _make_full_branch_comparison() -> BranchComparison:
    """Vollständiges BranchComparison-Objekt analog zum Spike-§-4-JSON-Response."""
    return BranchComparison(
        simulation_id="sim-abc123",
        branch_a_id="branch-001",
        branch_b_id="branch-002",
        created_at="2026-05-03T14:22:15Z",
        branch_a_completed_at="2026-05-03T14:10:00Z",
        branch_b_completed_at="2026-05-03T14:18:45Z",
        metrics_a=_make_branch_metrics(),
        metrics_b=_make_metrics_b(),
        deltas=_make_deltas(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_branch_comparison_round_trip():
    """Vollständiges Round-Trip: model_validate → model_dump → erneutes model_validate."""
    original = _make_full_branch_comparison()
    dumped = original.model_dump()
    restored = BranchComparison.model_validate(dumped)
    assert original == restored


def test_extra_key_rejected_top_level():
    """Unbekannte Felder auf Top-Level-BranchComparison müssen ValidationError auslösen."""
    comparison = _make_full_branch_comparison()
    data = comparison.model_dump()
    data["unknown_field"] = "verboten"
    with pytest.raises(ValidationError, match="unknown_field"):
        BranchComparison.model_validate(data)


def test_extra_key_rejected_nested():
    """Unbekannte Felder in BranchMetrics und SegmentReach müssen abgelehnt werden."""
    # BranchMetrics
    with pytest.raises(ValidationError):
        BranchMetrics(
            echo_chamber_index=0.5,
            cluster_count=2,
            total_agents=10,
            total_interactions=50,
            interaction_density=1.0,
            confidence_distribution={"low": 1, "medium": 2, "high": 3, "verified": 0},
            avg_evidence_per_claim=1.5,
            claims_without_evidence_ratio=0.1,
            contradiction_ratio=0.05,
            undeclared_field="boom",  # ungültig
        )
    # SegmentReach
    with pytest.raises(ValidationError):
        SegmentReach(
            segment_name="Test",
            active_count=5,
            total_count=10,
            ratio=0.5,
            extra_key="verboten",  # ungültig
        )


def test_echo_chamber_out_of_bounds():
    """echo_chamber_index > 1.0 muss ValidationError auslösen (Field(le=1.0))."""
    with pytest.raises(ValidationError):
        BranchMetrics(
            echo_chamber_index=1.5,  # ungültig
            cluster_count=2,
            total_agents=10,
            total_interactions=50,
            interaction_density=1.0,
            confidence_distribution={"low": 1, "medium": 2, "high": 3, "verified": 0},
            avg_evidence_per_claim=1.5,
            claims_without_evidence_ratio=0.1,
            contradiction_ratio=0.05,
        )


def test_segment_reach_consistency():
    """SegmentReach-Validator prüft active <= total und ratio == active/total."""
    # active_count > total_count → ungültig
    with pytest.raises(ValidationError, match="active_count"):
        SegmentReach(segment_name="X", active_count=10, total_count=5, ratio=0.5)

    # ratio stimmt nicht mit active/total überein (8/10 = 0.8, nicht 0.5)
    with pytest.raises(ValidationError, match="ratio"):
        SegmentReach(segment_name="X", active_count=8, total_count=10, ratio=0.5)

    # Korrekte Werte müssen valide sein
    valid = SegmentReach(segment_name="X", active_count=8, total_count=10, ratio=0.8)
    assert valid.active_count == 8

    # total_count=0 → ratio muss 0.0 sein
    zero = SegmentReach(segment_name="Y", active_count=0, total_count=0, ratio=0.0)
    assert zero.ratio == 0.0

    # total_count=0 mit ratio != 0.0 → ungültig
    with pytest.raises(ValidationError, match="ratio"):
        SegmentReach(segment_name="Z", active_count=0, total_count=0, ratio=0.5)


def test_confidence_distribution_literal_keys():
    """Nur Literal-Keys 'low', 'medium', 'high', 'verified' sind gültig in confidence_distribution."""
    # Gültige Keys müssen akzeptiert werden
    valid_metrics = _make_branch_metrics()
    assert valid_metrics.confidence_distribution["low"] == 3
    assert valid_metrics.confidence_distribution["verified"] == 1

    # Ungültiger Key muss ValidationError auslösen
    with pytest.raises(ValidationError):
        BranchMetrics(
            echo_chamber_index=0.5,
            cluster_count=2,
            total_agents=10,
            total_interactions=50,
            interaction_density=1.0,
            confidence_distribution={"unknown": 1, "medium": 2, "high": 3, "verified": 0},  # ungültig
            avg_evidence_per_claim=1.5,
            claims_without_evidence_ratio=0.1,
            contradiction_ratio=0.05,
        )


def test_same_branch_id_rejected():
    """BranchComparison mit branch_a_id == branch_b_id muss ValidationError auslösen."""
    with pytest.raises(ValidationError, match="branch_a_id"):
        BranchComparison(
            simulation_id="sim-abc123",
            branch_a_id="branch-001",
            branch_b_id="branch-001",  # gleiche ID — ungültig
            created_at="2026-05-03T14:22:15Z",
            branch_a_completed_at="2026-05-03T14:10:00Z",
            branch_b_completed_at="2026-05-03T14:18:45Z",
            metrics_a=_make_branch_metrics(),
            metrics_b=_make_metrics_b(),
            deltas=_make_deltas(),
        )


def test_cluster_summary_reuse_from_graph_diff():
    """ClusterSummary aus graph_diff.py wird in BranchMetrics korrekt eingebettet."""
    # Import aus beiden Modulen muss funktionieren
    from app.contracts.graph_diff import ClusterSummary as ClusterSummaryFromDiff
    from app.contracts.branch_comparison import BranchMetrics as BranchMetricsFromModule

    cluster = ClusterSummaryFromDiff(
        cluster_id=0, size=10, label="energie, politik", member_count=10
    )

    metrics = BranchMetricsFromModule(
        echo_chamber_index=0.5,
        cluster_count=1,
        dominant_clusters=[cluster],
        total_agents=10,
        total_interactions=50,
        interaction_density=1.0,
        confidence_distribution={"low": 1, "medium": 2, "high": 3, "verified": 0},
        avg_evidence_per_claim=1.5,
        claims_without_evidence_ratio=0.1,
        contradiction_ratio=0.05,
    )
    assert len(metrics.dominant_clusters) == 1
    assert metrics.dominant_clusters[0].cluster_id == 0
    # Sicherstellen: ClusterSummary aus graph_diff ist identische Klasse
    assert isinstance(metrics.dominant_clusters[0], ClusterSummaryFromDiff)


def test_empty_comparison():
    """Minimaler BranchComparison mit leeren Listen und Deltas=0 muss valide parsen."""
    empty_metrics = BranchMetrics(
        echo_chamber_index=0.0,
        cluster_count=0,
        dominant_clusters=[],
        bridge_agent_ids=[],
        total_agents=0,
        total_interactions=0,
        interaction_density=0.0,
        confidence_distribution={"low": 0, "medium": 0, "high": 0, "verified": 0},
        avg_evidence_per_claim=0.0,
        claims_without_evidence_ratio=0.0,
        contradiction_ratio=0.0,
        persona_reach={},
    )
    empty_deltas = ComparisonDeltas(
        echo_chamber_delta=0.0,
        cluster_delta=0,
        bridge_agents_delta=0,
        confidence_distribution_delta={"low": 0, "medium": 0, "high": 0, "verified": 0},
        avg_evidence_delta=0.0,
        contradiction_ratio_delta=0.0,
        interaction_density_delta=0.0,
        clusters_only_in_a=[],
        clusters_only_in_b=[],
        clusters_changed=[],
    )
    comparison = BranchComparison(
        simulation_id="sim-empty",
        branch_a_id="branch-a",
        branch_b_id="branch-b",
        created_at="2026-05-03T12:00:00Z",
        branch_a_completed_at="2026-05-03T11:00:00Z",
        branch_b_completed_at="2026-05-03T11:30:00Z",
        metrics_a=empty_metrics,
        metrics_b=empty_metrics,
        deltas=empty_deltas,
    )
    assert comparison.deltas.clusters_changed == []
    assert comparison.metrics_a.total_agents == 0


def test_schema_dump_idempotent():
    """BranchComparison.model_json_schema() zweimal aufrufen muss identisches Dict liefern."""
    schema_1 = BranchComparison.model_json_schema()
    schema_2 = BranchComparison.model_json_schema()
    assert json.dumps(schema_1, sort_keys=True) == json.dumps(schema_2, sort_keys=True)
