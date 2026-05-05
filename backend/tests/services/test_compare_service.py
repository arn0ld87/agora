"""Unit-Tests für CompareService (Sub-Slice 24, Closes #66).

Alle externen Dependencies werden via MagicMock isoliert.
Keine echte Neo4j- / Filesystem-Abhängigkeit in diesem Modul.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.contracts.branch_comparison import (
    BranchComparison,
)
from app.services.compare_service import (
    BranchIncompleteError,
    BranchNotFoundError,
    CompareService,
)
from app.services.network_analytics import ClusterDef, PolarizationMetrics
from app.services.simulation_manager import SimulationStatus


# ---------------------------------------------------------------------------
# Fixture-Helfer
# ---------------------------------------------------------------------------


def _make_state(sim_id: str, *, status: SimulationStatus = SimulationStatus.COMPLETED):
    """Minimalversion eines SimulationState-Mocks."""
    state = MagicMock()
    state.simulation_id = sim_id
    state.status = status
    state.updated_at = "2026-05-05T10:00:00"
    return state


def _make_polarization(
    *,
    echo_chamber_index: float = 0.5,
    cluster_count: int = 2,
    total_agents: int = 10,
    total_interactions: int = 50,
    clusters: list[ClusterDef] | None = None,
    bridge_agents: list[int] | None = None,
) -> PolarizationMetrics:
    return PolarizationMetrics(
        simulation_id="test",
        echo_chamber_index=echo_chamber_index,
        cluster_count=cluster_count,
        total_agents=total_agents,
        total_interactions=total_interactions,
        dominant_clusters=clusters or [],
        bridge_agents=bridge_agents or [],
    )


def _make_report(*, label_sequence: list[str] | None = None):
    """Einfacher Report-Mock mit Claims."""
    if label_sequence is None:
        label_sequence = ["low", "medium", "high"]

    claims = []
    for label in label_sequence:
        claim = MagicMock()
        claim.confidence_label = label
        claim.evidence = ["ev1"]  # 1 Evidence-Item pro Claim
        claim.audit_trail = None
        claims.append(claim)

    section = MagicMock()
    section.claims = claims

    outline = MagicMock()
    outline.sections = [section]

    report = MagicMock()
    report.outline = outline
    return report


def _make_service(
    *,
    polarization_a: PolarizationMetrics | None = None,
    polarization_b: PolarizationMetrics | None = None,
    state_a=None,
    state_b=None,
    neo4j_rows: list[dict] | None = None,
):
    """Baut einen CompareService mit vorgegebenen Mocks."""
    network = MagicMock()
    report_reader = MagicMock()
    neo4j = MagicMock()
    sim_manager = MagicMock()

    # get_simulation liefert state_a für branch_a, state_b für branch_b
    def _get_sim(branch_id: str):
        if branch_id == "sim_aaaaaaaaaaaa":
            return state_a
        if branch_id == "sim_bbbbbbbbbbbb":
            return state_b
        return None

    sim_manager.get_simulation.side_effect = _get_sim

    # compute_metrics-Reihenfolge: erst A, dann B
    _call_count = [0]

    def _compute_metrics(action_dicts, *, simulation_id=None, window_size_rounds=None):
        _call_count[0] += 1
        if _call_count[0] == 1:
            return polarization_a or _make_polarization()
        return polarization_b or _make_polarization()

    network.compute_metrics.side_effect = _compute_metrics

    report_reader.get_report_by_simulation.return_value = _make_report()

    neo4j.run_query.return_value = neo4j_rows or []

    return CompareService(
        network_analytics=network,
        report_reader=report_reader,
        neo4j_storage=neo4j,
        simulation_manager=sim_manager,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIdenticalBranchIds:
    def test_identical_branch_ids_raise_value_error(self):
        service = CompareService(
            network_analytics=MagicMock(),
            report_reader=MagicMock(),
            neo4j_storage=MagicMock(),
            simulation_manager=MagicMock(),
        )
        with pytest.raises(ValueError, match="müssen verschieden sein"):
            service.compare_branches(
                simulation_id="sim_000000000000",
                branch_a_id="sim_aaaaaaaaaaaa",
                branch_b_id="sim_aaaaaaaaaaaa",
            )


class TestBranchResolution:
    def test_branch_not_found_raises(self):
        sim_manager = MagicMock()
        sim_manager.get_simulation.return_value = None

        service = CompareService(
            network_analytics=MagicMock(),
            report_reader=MagicMock(),
            neo4j_storage=MagicMock(),
            simulation_manager=sim_manager,
        )
        with pytest.raises(BranchNotFoundError) as exc_info:
            service.compare_branches(
                simulation_id="sim_000000000000",
                branch_a_id="sim_aaaaaaaaaaaa",
                branch_b_id="sim_bbbbbbbbbbbb",
            )
        assert exc_info.value.branch_id == "sim_aaaaaaaaaaaa"

    def test_branch_not_completed_raises(self):
        sim_manager = MagicMock()

        state_a = _make_state("sim_aaaaaaaaaaaa", status=SimulationStatus.PREPARING)
        state_b = _make_state("sim_bbbbbbbbbbbb")

        def _get(branch_id: str):
            return state_a if branch_id == "sim_aaaaaaaaaaaa" else state_b

        sim_manager.get_simulation.side_effect = _get

        service = CompareService(
            network_analytics=MagicMock(),
            report_reader=MagicMock(),
            neo4j_storage=MagicMock(),
            simulation_manager=sim_manager,
        )
        with pytest.raises(BranchIncompleteError) as exc_info:
            service.compare_branches(
                simulation_id="sim_000000000000",
                branch_a_id="sim_aaaaaaaaaaaa",
                branch_b_id="sim_bbbbbbbbbbbb",
            )
        assert exc_info.value.branch_id == "sim_aaaaaaaaaaaa"
        assert exc_info.value.status == "preparing"


class TestMetricsAggregation:
    def test_metrics_aggregation_happy_path(self, monkeypatch):
        """Alle vier Quellen (network/report/neo4j/sim_manager) fließen in BranchMetrics."""
        pol = _make_polarization(
            echo_chamber_index=0.6,
            cluster_count=3,
            total_agents=20,
            total_interactions=80,
            clusters=[ClusterDef(cluster_id=0, size=10, agent_ids=[1, 2], label="thema-a")],
            bridge_agents=[1, 2, 3],
        )

        state_a = _make_state("sim_aaaaaaaaaaaa")
        state_b = _make_state("sim_bbbbbbbbbbbb")

        def _get(bid: str):
            return state_a if bid == "sim_aaaaaaaaaaaa" else state_b

        sim_manager = MagicMock()
        sim_manager.get_simulation.side_effect = _get

        network = MagicMock()
        network.compute_metrics.return_value = pol

        report_reader = MagicMock()
        report_reader.get_report_by_simulation.return_value = _make_report(
            label_sequence=["low", "medium", "high", "verified"]
        )

        neo4j = MagicMock()
        neo4j.run_query.return_value = [
            {"segment": "Politik", "total_count": 5, "active_count": 4}
        ]

        # Monkeypatch SimulationRunner.get_all_actions
        import app.services.simulation_runner as sr

        monkeypatch.setattr(sr.SimulationRunner, "get_all_actions", lambda *a, **kw: [])

        service = CompareService(
            network_analytics=network,
            report_reader=report_reader,
            neo4j_storage=neo4j,
            simulation_manager=sim_manager,
        )
        result = service.compare_branches(
            simulation_id="sim_000000000000",
            branch_a_id="sim_aaaaaaaaaaaa",
            branch_b_id="sim_bbbbbbbbbbbb",
        )

        assert isinstance(result, BranchComparison)
        # Netzwerk
        assert result.metrics_a.echo_chamber_index == 0.6
        assert result.metrics_a.cluster_count == 3
        assert result.metrics_a.total_agents == 20
        # Report
        assert result.metrics_a.confidence_distribution["low"] == 1
        assert result.metrics_a.confidence_distribution["verified"] == 1
        # Persona-Reach
        assert "Politik" in result.metrics_a.persona_reach
        assert result.metrics_a.persona_reach["Politik"].ratio == pytest.approx(0.8)


class TestDeltas:
    def test_deltas_signed_b_minus_a(self, monkeypatch):
        """Positives Delta wenn B höheren Echo-Chamber-Index hat als A."""
        pol_a = _make_polarization(echo_chamber_index=0.4)
        pol_b = _make_polarization(echo_chamber_index=0.7)

        call_n = [0]

        def _compute(actions, *, simulation_id=None, window_size_rounds=None):
            call_n[0] += 1
            return pol_a if call_n[0] == 1 else pol_b

        state_a = _make_state("sim_aaaaaaaaaaaa")
        state_b = _make_state("sim_bbbbbbbbbbbb")

        def _get(bid: str):
            return state_a if bid == "sim_aaaaaaaaaaaa" else state_b

        sim_manager = MagicMock()
        sim_manager.get_simulation.side_effect = _get

        network = MagicMock()
        network.compute_metrics.side_effect = _compute

        report_reader = MagicMock()
        report_reader.get_report_by_simulation.return_value = None

        neo4j = MagicMock()
        neo4j.run_query.return_value = []

        import app.services.simulation_runner as sr

        monkeypatch.setattr(sr.SimulationRunner, "get_all_actions", lambda *a, **kw: [])

        service = CompareService(
            network_analytics=network,
            report_reader=report_reader,
            neo4j_storage=neo4j,
            simulation_manager=sim_manager,
        )
        result = service.compare_branches(
            simulation_id="sim_000000000000",
            branch_a_id="sim_aaaaaaaaaaaa",
            branch_b_id="sim_bbbbbbbbbbbb",
        )
        assert result.deltas.echo_chamber_delta == pytest.approx(0.3, abs=1e-9)
        assert result.deltas.echo_chamber_delta > 0

    def test_clusters_only_in_b(self, monkeypatch):
        """Cluster nur in B vorhanden → in clusters_only_in_b, nicht in clusters_changed."""
        cluster_a = ClusterDef(cluster_id=0, size=5, agent_ids=[1], label="thema-x")
        cluster_b_shared = ClusterDef(cluster_id=0, size=6, agent_ids=[1], label="thema-x")
        cluster_b_new = ClusterDef(cluster_id=99, size=3, agent_ids=[5], label="thema-neu")

        pol_a = _make_polarization(clusters=[cluster_a])
        pol_b = _make_polarization(clusters=[cluster_b_shared, cluster_b_new])

        call_n = [0]

        def _compute(actions, *, simulation_id=None, window_size_rounds=None):
            call_n[0] += 1
            return pol_a if call_n[0] == 1 else pol_b

        state_a = _make_state("sim_aaaaaaaaaaaa")
        state_b = _make_state("sim_bbbbbbbbbbbb")

        def _get(bid: str):
            return state_a if bid == "sim_aaaaaaaaaaaa" else state_b

        sim_manager = MagicMock()
        sim_manager.get_simulation.side_effect = _get

        network = MagicMock()
        network.compute_metrics.side_effect = _compute

        report_reader = MagicMock()
        report_reader.get_report_by_simulation.return_value = None

        neo4j = MagicMock()
        neo4j.run_query.return_value = []

        import app.services.simulation_runner as sr

        monkeypatch.setattr(sr.SimulationRunner, "get_all_actions", lambda *a, **kw: [])

        service = CompareService(
            network_analytics=network,
            report_reader=report_reader,
            neo4j_storage=neo4j,
            simulation_manager=sim_manager,
        )
        result = service.compare_branches(
            simulation_id="sim_000000000000",
            branch_a_id="sim_aaaaaaaaaaaa",
            branch_b_id="sim_bbbbbbbbbbbb",
        )
        only_b_ids = {c.cluster_id for c in result.deltas.clusters_only_in_b}
        changed_ids = {c.cluster_id for c in result.deltas.clusters_changed}

        assert 99 in only_b_ids
        assert 99 not in changed_ids
        assert 0 in changed_ids  # gemeinsamer Cluster in clusters_changed


class TestSegmentReach:
    def test_segment_reach_zero_total(self, monkeypatch):
        """Segment ohne Personas → ratio=0.0, kein ZeroDivisionError."""
        pol = _make_polarization()
        state_a = _make_state("sim_aaaaaaaaaaaa")
        state_b = _make_state("sim_bbbbbbbbbbbb")

        def _get(bid: str):
            return state_a if bid == "sim_aaaaaaaaaaaa" else state_b

        sim_manager = MagicMock()
        sim_manager.get_simulation.side_effect = _get

        network = MagicMock()
        network.compute_metrics.return_value = pol

        report_reader = MagicMock()
        report_reader.get_report_by_simulation.return_value = None

        neo4j = MagicMock()
        neo4j.run_query.return_value = [
            {"segment": "Leer", "total_count": 0, "active_count": 0}
        ]

        import app.services.simulation_runner as sr

        monkeypatch.setattr(sr.SimulationRunner, "get_all_actions", lambda *a, **kw: [])

        service = CompareService(
            network_analytics=network,
            report_reader=report_reader,
            neo4j_storage=neo4j,
            simulation_manager=sim_manager,
        )
        result = service.compare_branches(
            simulation_id="sim_000000000000",
            branch_a_id="sim_aaaaaaaaaaaa",
            branch_b_id="sim_bbbbbbbbbbbb",
        )
        leer = result.metrics_a.persona_reach.get("Leer")
        assert leer is not None
        assert leer.ratio == 0.0
        assert leer.total_count == 0
        assert leer.active_count == 0
