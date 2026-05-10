"""
Agora Contracts — Single Source of Truth für API/LLM/Frontend-Datenstrukturen.

Pflicht-Lesepfad bei Änderungen:
1. docu/design/contract-architecture.md
2. backend/tests/contracts/ (Verträge sind Testbar)
3. schemas/*.schema.json (auto-generiert via dump_schemas)
"""
from .report_contract import (
    ConfidenceLabel,
    EvidenceItemModel,
    EvidenceMapModel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
    ReportContractModel,
    ReportModel,
    ReportOutlineModel,
    ReportSectionDataGapModel,
    ReportSectionHypothesisModel,
    ReportSectionModel,
    ReportStatus,
)
from .persona_contract import (
    PersonaModel,
    PersonaQuotaActual,
    PersonaQuotaPlan,
    VoiceRegister,
)
from .runs_contract import (
    RunDetail,
    RunsAggregation,
    RunsFilterQuery,
    RunsListResponse,
    RunStatus,
    RunSummary,
)
from .branch_comparison import (
    BranchComparison,
    BranchMetrics,
    ClusterChange,
    ComparisonDeltas,
    SegmentReach,
)
from .graph_diff import (
    BridgeAgentShift,
    ClusterShift,
    ClusterSummary,
    EdgeData,
    EdgeReinforcement,
    EdgeWeakening,
    GraphDiff,
    GraphDiffMetrics,
    GraphSnapshot,
    NodePropertyShift,
)
from .persona_entity_context import EntityRelationship, PersonaEntityContext
from .report_v3 import (
    Claim,
    ChangeRecommendation,
    ContentIdea,
    DataGap,
    FrictionPoint,
    Multiplier,
    Persona,
    PositioningVariant,
    ProjectImpact,
    ReportV3,
    Segment,
    TrustSignal,
)

__all__ = [
    "BranchComparison",
    "BranchMetrics",
    "BridgeAgentShift",
    "ClusterChange",
    "ClusterShift",
    "ClusterSummary",
    "ComparisonDeltas",
    "ConfidenceLabel",
    "EdgeData",
    "EdgeReinforcement",
    "EdgeWeakening",
    "EntityRelationship",
    "EvidenceItemModel",
    "EvidenceMapModel",
    "EvidenceSourceKind",
    "EvidenceType",
    "GraphDiff",
    "GraphDiffMetrics",
    "GraphSnapshot",
    "NodePropertyShift",
    "PersonaEntityContext",
    "PersonaModel",
    "PersonaQuotaActual",
    "PersonaQuotaPlan",
    "ReportClaimModel",
    "ReportContractModel",
    "ReportModel",
    "ReportOutlineModel",
    "ReportSectionDataGapModel",
    "ReportSectionHypothesisModel",
    "ReportSectionModel",
    "ReportStatus",
    "RunDetail",
    "RunsAggregation",
    "RunsFilterQuery",
    "RunsListResponse",
    "RunStatus",
    "RunSummary",
    "SegmentReach",
    "VoiceRegister",
    # ReportV3 — 11 Pflichtabschnitt-DTOs
    "Claim",
    "ChangeRecommendation",
    "ContentIdea",
    "DataGap",
    "FrictionPoint",
    "Multiplier",
    "Persona",
    "PositioningVariant",
    "ProjectImpact",
    "ReportV3",
    "Segment",
    "TrustSignal",
]
