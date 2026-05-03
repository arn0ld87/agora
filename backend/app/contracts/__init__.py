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
    EvidenceType,
    ReportClaimModel,
    ReportContractModel,
    ReportModel,
    ReportOutlineModel,
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

__all__ = [
    "BridgeAgentShift",
    "ClusterShift",
    "ClusterSummary",
    "ConfidenceLabel",
    "EdgeData",
    "EdgeReinforcement",
    "EdgeWeakening",
    "EvidenceItemModel",
    "EvidenceMapModel",
    "EvidenceType",
    "GraphDiff",
    "GraphDiffMetrics",
    "GraphSnapshot",
    "NodePropertyShift",
    "PersonaModel",
    "PersonaQuotaActual",
    "PersonaQuotaPlan",
    "ReportClaimModel",
    "ReportContractModel",
    "ReportModel",
    "ReportOutlineModel",
    "ReportSectionModel",
    "ReportStatus",
    "RunDetail",
    "RunsAggregation",
    "RunsFilterQuery",
    "RunsListResponse",
    "RunStatus",
    "RunSummary",
    "VoiceRegister",
]
