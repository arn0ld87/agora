"""
BranchComparison-Contract v1 (Pydantic v2) — Single Source of Truth für Branch-Vergleiche.

Modelliert den Vergleich zweier vollständig simulierter Branches einer Simulation,
inkl. aggregierter Metriken pro Branch und signierten Differenzen (Deltas).

Datenquellen:
- backend/app/services/network_analytics.py  (NetworkAnalyticsService, PolarizationMetrics)
- backend/app/services/confidence_calculator.py  (compute_confidence)
- backend/app/models/report.py  (Report, ReportSection, ReportClaim)
- docs/2026-05-03-task-23-compare-model-spike.md § 3+4 (autoritatives Spec-Dokument)

Designentscheidungen (Abweichungen vom Spike-Pseudocode):
- confidence_distribution: dict[Literal["low", "medium", "high", "verified"], int] statt
  dict[str, int] — typisierte Keys verhindern ungültige Label, extra="forbid" wäre sonst
  semantisch lückenhaft für dieses Feld.
- clusters_changed: list[ClusterChange] statt list[Dict] — typisierter Ersatz, der
  label_a und label_b separat führt statt einem kombinierten label_change-String.
- SegmentReach: model_validator prüft active_count <= total_count sowie
  ratio ≈ active_count / total_count (Toleranz < 1e-6) wenn total_count > 0.
- BranchComparison: model_validator prüft branch_a_id != branch_b_id.
- ClusterSummary: KEIN eigenes Modell — Reuse aus app.contracts.graph_diff.

Aufruf zum Schema-Dump: cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.graph_diff import ClusterSummary  # Single Source of Truth — KEIN Duplikat

# Gemeinsame Konfiguration für alle Modelle dieses Moduls
_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)

# Typisierter Literal-Typ für Confidence-Distribution-Keys
_ConfidenceKey = Literal["low", "medium", "high", "verified"]


class SegmentReach(BaseModel):
    """Activation coverage for a single persona segment in a simulated branch.

    Measures how many generated personas of a segment have executed at least
    one action during the simulation (Aktivitäts-Indikator).
    """

    model_config = _STRICT

    segment_name: str = Field(..., description="Name des Persona-Segments, z. B. 'Politik'")
    active_count: int = Field(ge=0, description="Personas mit mindestens 1 Action")
    total_count: int = Field(ge=0, description="Alle generierten Personas im Segment")
    ratio: float = Field(ge=0.0, le=1.0, description="active_count / total_count")

    @model_validator(mode="after")
    def _validate_counts_and_ratio(self) -> "SegmentReach":
        # active darf total nicht überschreiten
        if self.active_count > self.total_count:
            raise ValueError(
                f"SegmentReach: active_count ({self.active_count}) darf nicht größer als "
                f"total_count ({self.total_count}) sein."
            )
        # Konsistenzprüfung ratio ≈ active_count / total_count (bei total_count > 0)
        if self.total_count > 0:
            expected_ratio = self.active_count / self.total_count
            if abs(self.ratio - expected_ratio) > 1e-6:
                raise ValueError(
                    f"SegmentReach: ratio ({self.ratio}) stimmt nicht mit "
                    f"active_count/total_count ({expected_ratio:.9f}) überein "
                    f"(Toleranz 1e-6)."
                )
        else:
            # total_count == 0 → ratio muss 0.0 sein
            if self.ratio != 0.0:
                raise ValueError(
                    f"SegmentReach: ratio muss 0.0 sein wenn total_count==0, "
                    f"erhalten: {self.ratio}."
                )
        return self


class ClusterChange(BaseModel):
    """Typed record for a cluster that changed its composition or label between two branches.

    Ersatz für den Spike-Hint `List[Dict]` in ComparisonDeltas.clusters_changed.
    label_a und label_b werden separat geführt — der API-Klient kann den Pfeil im UI rendern.
    """

    model_config = _STRICT

    cluster_id: int = Field(..., description="Cluster-ID (gemeinsamer Bezugspunkt zwischen Branches)")
    size_a: int = Field(ge=0, description="Cluster-Größe in Branch A")
    size_b: int = Field(ge=0, description="Cluster-Größe in Branch B")
    label_a: str = Field(..., description="TF-Top-3-Label in Branch A")
    label_b: str = Field(..., description="TF-Top-3-Label in Branch B")


class BranchMetrics(BaseModel):
    """Aggregated metrics snapshot for a single fully-simulated branch.

    Deckt Netzwerk-Metriken, Evidence-Qualität und Persona-Aktivierung ab.
    Alle float-Felder werden in der API-Response auf 2–4 Dezimalstellen gerundet.
    """

    model_config = _STRICT

    # --- Netzwerk ---
    echo_chamber_index: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Anteil Agenteninteraktionen innerhalb desselben Clusters "
            "(0.0 = vollständig integriert, 1.0 = völlig polarisiert)"
        ),
    )
    cluster_count: int = Field(ge=0, description="Anzahl dominanter Cluster")
    dominant_clusters: list[ClusterSummary] = Field(
        default_factory=list,
        description="Top-k Cluster nach Größe, deterministisch sortiert — Reuse aus graph_diff",
    )
    bridge_agent_ids: list[int] = Field(
        default_factory=list,
        description="Top-k Agenten nach Betweenness-Centrality (Cross-Cluster-Brückenbau)",
    )
    total_agents: int = Field(ge=0, description="Gesamtanzahl Agenten im Branch")
    total_interactions: int = Field(ge=0, description="Gesamtanzahl Agenten-Interaktionen")
    interaction_density: float = Field(
        ge=0.0,
        description="Durchschnittliche Interaktionen pro Runde (interactions / rounds, approx)",
    )

    # --- Report / Evidence ---
    confidence_distribution: dict[_ConfidenceKey, int] = Field(
        ...,
        description=(
            "Histogramm der Claim-Confidence-Scores: "
            "{low: int, medium: int, high: int, verified: int}"
        ),
    )
    avg_evidence_per_claim: float = Field(
        ge=0.0, description="Durchschnittliche Anzahl Evidence-Items pro Claim"
    )
    claims_without_evidence_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Anteil Claims ohne Evidence-Items (struktureller Drift-Marker)",
    )
    contradiction_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Anteil Claims mit Widerspruchsmarkierungen in der Evidence",
    )

    # --- Personas ---
    persona_reach: dict[str, SegmentReach] = Field(
        default_factory=dict,
        description="Segment-Name → SegmentReach (Aktivitätsquote pro Segment)",
    )


class ComparisonDeltas(BaseModel):
    """Signed differences between Branch B and Branch A (B - A).

    Negative Werte bedeuten: Branch A hat höhere Ausprägung.
    Positive Werte bedeuten: Branch B hat höhere Ausprägung.
    """

    model_config = _STRICT

    # --- Netzwerk-Deltas ---
    echo_chamber_delta: float = Field(
        description="Delta Echo-Chamber-Index (positiv = mehr Polarisation in B)"
    )
    cluster_delta: int = Field(description="Delta Cluster-Anzahl (positiv = mehr Cluster in B)")
    bridge_agents_delta: int = Field(
        description="Delta Bridge-Agent-Anzahl (positiv = mehr Bridge-Agents in B)"
    )

    # --- Evidence-Qualität-Deltas ---
    confidence_distribution_delta: dict[_ConfidenceKey, int] = Field(
        ...,
        description="Signed Differenz pro Confidence-Label (B - A)",
    )
    avg_evidence_delta: float = Field(
        description="Delta durchschnittliche Evidence-Items pro Claim (B - A)"
    )
    contradiction_ratio_delta: float = Field(
        description="Delta Contradiction-Ratio (B - A, signed)"
    )

    # --- Engagement-Delta ---
    interaction_density_delta: float = Field(
        description="Delta Interaction-Density (positiv = dichteres Engagement in B)"
    )

    # --- Semantic Cluster-Highlights ---
    clusters_only_in_a: list[ClusterSummary] = Field(
        default_factory=list,
        description="Cluster die nur in Branch A existieren (in B verschwunden)",
    )
    clusters_only_in_b: list[ClusterSummary] = Field(
        default_factory=list,
        description="Cluster die nur in Branch B existieren (in A nicht vorhanden)",
    )
    clusters_changed: list[ClusterChange] = Field(
        default_factory=list,
        description=(
            "Cluster die in beiden Branches vorhanden sind, aber Größe oder Label geändert haben. "
            "Typisiert als ClusterChange — KEIN list[dict]."
        ),
    )


class BranchComparison(BaseModel):
    """Top-level contract for comparing two fully-simulated branches of a simulation.

    Enthält vollständige Metriken beider Branches sowie signierte Deltas.
    Der Consumer benötigt keine zweite Anfrage für die Einzelmetriken.
    """

    model_config = _STRICT

    simulation_id: str = Field(..., description="ID der gemeinsamen Parent-Simulation")
    branch_a_id: str = Field(..., description="ID Branch A (UUID oder Neo4j SimulationBranch-ID)")
    branch_b_id: str = Field(..., description="ID Branch B (UUID oder Neo4j SimulationBranch-ID)")

    # --- Metadaten ---
    created_at: datetime = Field(description="Zeitstempel dieses Vergleichs (nicht der Simulation)")
    branch_a_completed_at: datetime = Field(description="Simulation-Completion-Zeit Branch A")
    branch_b_completed_at: datetime = Field(description="Simulation-Completion-Zeit Branch B")

    # --- Metriken pro Branch ---
    metrics_a: BranchMetrics = Field(description="Aggregierter Metriken-Snapshot Branch A")
    metrics_b: BranchMetrics = Field(description="Aggregierter Metriken-Snapshot Branch B")

    # --- Differenzen ---
    deltas: ComparisonDeltas = Field(description="Signierte Differenzen (Branch B - Branch A)")

    @model_validator(mode="after")
    def _validate_different_branches(self) -> "BranchComparison":
        # Zwei verschiedene Branches sind Pflicht — gleiche IDs ergeben keinen sinnvollen Vergleich
        if self.branch_a_id == self.branch_b_id:
            raise ValueError(
                f"BranchComparison: branch_a_id und branch_b_id müssen verschieden sein, "
                f"erhalten: '{self.branch_a_id}' für beide."
            )
        return self
