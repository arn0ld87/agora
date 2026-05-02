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

__all__ = [
    "ConfidenceLabel",
    "EvidenceItemModel",
    "EvidenceMapModel",
    "EvidenceType",
    "PersonaModel",
    "PersonaQuotaActual",
    "PersonaQuotaPlan",
    "ReportClaimModel",
    "ReportContractModel",
    "ReportModel",
    "ReportOutlineModel",
    "ReportSectionModel",
    "ReportStatus",
    "VoiceRegister",
]
