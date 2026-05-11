"""CompareService — Branch-Vergleich für vollständig simulierte Branches.

Aggregiert BranchMetrics aus drei Quellen:
- NetworkAnalyticsService (Polarisations-Metriken, Cluster, Bridge-Agents)
- ReportManager (Confidence-Verteilung, Evidence-Coverage, Contradiction-Ratio)
- Neo4j (Persona-Segment-Aktivierung)

und berechnet signierte Deltas (Branch B − Branch A).

Spec: docs/archive/history/2026-05-03-task-23-compare-model-spike.md
Closes #66 (Sub-Slice 24)
"""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from app.contracts.branch_comparison import (
    BranchComparison,
    BranchMetrics,
    ClusterChange,
    ComparisonDeltas,
    SegmentReach,
)
from app.contracts.graph_diff import ClusterSummary
from app.utils.logger import get_logger

logger = get_logger("agora.compare_service")

# Literal-Typ für Confidence-Keys (gespiegelt aus branch_comparison.py)
_CONFIDENCE_KEYS = ("low", "medium", "high", "verified")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class BranchNotFoundError(Exception):
    """Wird geworfen, wenn ein Branch / eine SimulationState nicht gefunden wird."""

    def __init__(self, branch_id: str, simulation_id: str | None = None) -> None:
        self.branch_id = branch_id
        self.simulation_id = simulation_id
        super().__init__(f"Branch '{branch_id}' nicht gefunden")


class BranchIncompleteError(Exception):
    """Wird geworfen, wenn ein Branch nicht den Status COMPLETED hat."""

    def __init__(self, branch_id: str, status: str) -> None:
        self.branch_id = branch_id
        self.status = status
        super().__init__(f"Branch '{branch_id}' ist nicht simuliert (Status: {status})")


# ---------------------------------------------------------------------------
# CompareService
# ---------------------------------------------------------------------------


class CompareService:
    """Berechnet den Vergleich zweier vollständig simulierter Branches.

    Dependencies werden per Constructor injiziert — erleichtert Unit-Tests
    ohne echtes Neo4j / Filesystem.
    """

    def __init__(
        self,
        network_analytics: Any,
        report_reader: Any,
        neo4j_storage: Any,
        simulation_manager: Any,
    ) -> None:
        self._network_analytics = network_analytics
        self._report_reader = report_reader
        self._neo4j_storage = neo4j_storage
        self._simulation_manager = simulation_manager

    # -- public ----------------------------------------------------------------

    def compare_branches(
        self,
        simulation_id: str,
        branch_a_id: str,
        branch_b_id: str,
        window_size_rounds: int | None = None,
    ) -> BranchComparison:
        """Vergleicht zwei Branches und gibt ein vollständiges BranchComparison zurück.

        Raises:
            ValueError: wenn branch_a_id == branch_b_id
            BranchNotFoundError: wenn einer der Branches nicht existiert
            BranchIncompleteError: wenn ein Branch nicht COMPLETED ist
        """
        if branch_a_id == branch_b_id:
            raise ValueError(
                "BranchComparison: branch_a_id und branch_b_id müssen verschieden sein"
            )

        # Branch-Resolution + Statusprüfung
        state_a = self._simulation_manager.get_simulation(branch_a_id)
        if state_a is None:
            raise BranchNotFoundError(branch_id=branch_a_id, simulation_id=simulation_id)

        state_b = self._simulation_manager.get_simulation(branch_b_id)
        if state_b is None:
            raise BranchNotFoundError(branch_id=branch_b_id, simulation_id=simulation_id)

        _COMPLETED = "completed"
        if state_a.status.value != _COMPLETED:
            raise BranchIncompleteError(branch_id=branch_a_id, status=state_a.status.value)
        if state_b.status.value != _COMPLETED:
            raise BranchIncompleteError(branch_id=branch_b_id, status=state_b.status.value)

        # Timestamps aus dem SimulationState (updated_at als Proxy für completed_at)
        def _parse_ts(ts_str: str) -> datetime:
            try:
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)

        branch_a_completed_at = _parse_ts(state_a.updated_at)
        branch_b_completed_at = _parse_ts(state_b.updated_at)

        # Metriken aggregieren
        metrics_a = self._build_metrics(branch_a_id, window_size_rounds=window_size_rounds)
        metrics_b = self._build_metrics(branch_b_id, window_size_rounds=window_size_rounds)

        # Deltas berechnen
        deltas = self._compute_deltas(metrics_a, metrics_b)

        return BranchComparison(
            simulation_id=simulation_id,
            branch_a_id=branch_a_id,
            branch_b_id=branch_b_id,
            created_at=datetime.now(timezone.utc),
            branch_a_completed_at=branch_a_completed_at,
            branch_b_completed_at=branch_b_completed_at,
            metrics_a=metrics_a,
            metrics_b=metrics_b,
            deltas=deltas,
        )

    # -- private ---------------------------------------------------------------

    def _build_metrics(
        self,
        branch_id: str,
        *,
        window_size_rounds: int | None = None,
    ) -> BranchMetrics:
        """Aggregiert BranchMetrics aus Network, Report und Neo4j."""

        # 1) Netzwerk-Metriken via SimulationRunner.get_all_actions → NetworkAnalyticsService
        from app.services.simulation_runner import SimulationRunner

        actions = SimulationRunner.get_all_actions(branch_id)
        action_dicts = [a.to_dict() for a in actions]
        polarization = self._network_analytics.compute_metrics(
            action_dicts,
            simulation_id=branch_id,
            window_size_rounds=window_size_rounds,
        )

        # Cluster-Liste → ClusterSummary (Reuse aus graph_diff)
        dominant_clusters: list[ClusterSummary] = [
            ClusterSummary(
                cluster_id=c.cluster_id,
                size=c.size,
                label=c.label,
                member_count=c.size,  # ClusterDef hat keine separate member_count, size = member_count
            )
            for c in polarization.dominant_clusters
        ]

        # Interaction-Density: interactions / max(rounds, 1)
        max_round = 0
        if action_dicts:
            try:
                max_round = max(
                    int(a.get("round") or a.get("round_num") or 0)
                    for a in action_dicts
                )
            except (ValueError, TypeError):
                max_round = 0
        interaction_density = polarization.total_interactions / max(max_round, 1)

        # 2) Report-Metriken via ReportManager
        report = self._report_reader.get_report_by_simulation(branch_id)

        confidence_distribution: dict[str, int] = {k: 0 for k in _CONFIDENCE_KEYS}
        avg_evidence_per_claim = 0.0
        claims_without_evidence_ratio = 0.0
        contradiction_ratio = 0.0

        if report is not None:
            all_claims = self._extract_claims(report)
            if all_claims:
                # Confidence-Histogramm aus confidence_label
                for claim in all_claims:
                    label = (getattr(claim, "confidence_label", None) or "").lower()
                    if label in confidence_distribution:
                        confidence_distribution[label] += 1

                # Evidence-Coverage
                evidence_counts = [
                    len(getattr(claim, "evidence", None) or [])
                    for claim in all_claims
                ]
                avg_evidence_per_claim = mean(evidence_counts) if evidence_counts else 0.0
                without_evidence = sum(1 for c in evidence_counts if c == 0)
                claims_without_evidence_ratio = without_evidence / len(all_claims)

                # Contradiction-Ratio (aus audit_trail wenn vorhanden, sonst 0.0)
                contradiction_count = 0
                for claim in all_claims:
                    audit_trail = getattr(claim, "audit_trail", None)
                    if audit_trail is not None:
                        detected = getattr(audit_trail, "contradiction_detected", False)
                        if detected:
                            contradiction_count += 1
                contradiction_ratio = contradiction_count / len(all_claims)

        # 3) Persona-Reach via Neo4j
        persona_reach = self._build_persona_reach(branch_id)

        return BranchMetrics(
            echo_chamber_index=polarization.echo_chamber_index,
            cluster_count=polarization.cluster_count,
            dominant_clusters=dominant_clusters,
            bridge_agent_ids=list(polarization.bridge_agents[:5]),
            total_agents=polarization.total_agents,
            total_interactions=polarization.total_interactions,
            interaction_density=interaction_density,
            confidence_distribution=confidence_distribution,  # type: ignore[arg-type]
            avg_evidence_per_claim=avg_evidence_per_claim,
            claims_without_evidence_ratio=claims_without_evidence_ratio,
            contradiction_ratio=contradiction_ratio,
            persona_reach=persona_reach,
        )

    def _extract_claims(self, report: Any) -> list[Any]:
        """Extrahiert alle Claims aus allen Sections eines Reports."""
        claims: list[Any] = []
        outline = getattr(report, "outline", None)
        if outline is None:
            return claims
        sections = getattr(outline, "sections", None) or []
        for section in sections:
            section_claims = getattr(section, "claims", None) or []
            claims.extend(section_claims)
        return claims

    def _build_persona_reach(self, branch_id: str) -> dict[str, SegmentReach]:
        """Fragt Neo4j nach Segment-Aktivierungsquoten pro Branch."""
        cypher = (
            "MATCH (sim:SimulationBranch {id: $branch_id})"
            "-[:HAS_AGENT]->(a:Agent)-[:HAS_PERSONA]->(p:Persona) "
            "WITH p.segment AS segment, "
            "count(a) AS total_count, "
            "count(CASE WHEN a.action_count > 0 THEN 1 END) AS active_count "
            "RETURN segment, total_count, active_count"
        )
        try:
            rows = self._neo4j_storage.run_query(cypher, {"branch_id": branch_id})
        except Exception:
            logger.warning(
                "Persona-Reach-Query für Branch %s fehlgeschlagen — leeres dict",
                branch_id,
            )
            return {}

        result: dict[str, SegmentReach] = {}
        for row in rows or []:
            segment = row.get("segment") or "unbekannt"
            total = int(row.get("total_count") or 0)
            active = int(row.get("active_count") or 0)
            ratio = (active / total) if total > 0 else 0.0
            result[segment] = SegmentReach(
                segment_name=segment,
                active_count=active,
                total_count=total,
                ratio=ratio,
            )
        return result

    def _compute_deltas(
        self,
        metrics_a: BranchMetrics,
        metrics_b: BranchMetrics,
    ) -> ComparisonDeltas:
        """Berechnet signierte Differenzen (B - A) zwischen zwei BranchMetrics."""

        # Confidence-Distribution-Delta
        # Zugriff über cast(Literal[...], key) vermeidet mypy call-overload-Fehler
        from typing import Literal, cast as _cast

        _ConfKey = Literal["low", "medium", "high", "verified"]
        conf_delta: dict[str, int] = {}
        for key in _CONFIDENCE_KEYS:
            typed_key = _cast(_ConfKey, key)
            val_a = metrics_a.confidence_distribution.get(typed_key, 0)
            val_b = metrics_b.confidence_distribution.get(typed_key, 0)
            conf_delta[key] = val_b - val_a

        # Cluster-Sets (ID-basiert, keine semantic similarity in v1)
        ids_a = {c.cluster_id for c in metrics_a.dominant_clusters}
        ids_b = {c.cluster_id for c in metrics_b.dominant_clusters}

        clusters_only_in_a = [c for c in metrics_a.dominant_clusters if c.cluster_id not in ids_b]
        clusters_only_in_b = [c for c in metrics_b.dominant_clusters if c.cluster_id not in ids_a]

        # Gemeinsame Cluster → ClusterChange (auch wenn nichts geändert hat)
        shared_ids = ids_a & ids_b
        map_a = {c.cluster_id: c for c in metrics_a.dominant_clusters}
        map_b = {c.cluster_id: c for c in metrics_b.dominant_clusters}
        clusters_changed: list[ClusterChange] = [
            ClusterChange(
                cluster_id=cid,
                size_a=map_a[cid].size,
                size_b=map_b[cid].size,
                label_a=map_a[cid].label,
                label_b=map_b[cid].label,
            )
            for cid in sorted(shared_ids)
        ]

        return ComparisonDeltas(
            echo_chamber_delta=metrics_b.echo_chamber_index - metrics_a.echo_chamber_index,
            cluster_delta=metrics_b.cluster_count - metrics_a.cluster_count,
            bridge_agents_delta=(
                len(metrics_b.bridge_agent_ids) - len(metrics_a.bridge_agent_ids)
            ),
            confidence_distribution_delta=conf_delta,  # type: ignore[arg-type]
            avg_evidence_delta=metrics_b.avg_evidence_per_claim - metrics_a.avg_evidence_per_claim,
            contradiction_ratio_delta=(
                metrics_b.contradiction_ratio - metrics_a.contradiction_ratio
            ),
            interaction_density_delta=(
                metrics_b.interaction_density - metrics_a.interaction_density
            ),
            clusters_only_in_a=clusters_only_in_a,
            clusters_only_in_b=clusters_only_in_b,
            clusters_changed=clusters_changed,
        )
