# ruff: noqa: F401, E402, F811
"""
Report-Contract v2 (Pydantic v2) — Single Source of Truth & Rückwärtskompatible Fassade.

Code-verifiziert gegen:
- backend/app/models/report.py (Dataclass-Quellen)
- backend/app/services/report_agent.py (Z. 184/567/1127: schema_version-Drift)
- backend/app/api/report.py (Z. 379: EXPORT_SCHEMA_VERSION = 1)
- backend/app/services/oasis_profile_generator.py (OasisAgentProfile-Felder)
- backend/tests/api/test_response_schemas.py (Schema-Erwartungen)

Layer 3 (Task 12): EvidenceItemModel erhaelt quote + source_id_anchor fuer
Original-Zitat-Provenance. Section-Builder leitet beide per _attach_provenance ab.

Aufruf zum Schema-Dump: python -m app.contracts.dump_schemas

Aufgeteilt in kohäsive Submodule:
- ``report_evidence_types.py``: Enums, Typen, Basis-Helper
- ``report_evidence_contract.py``: EvidenceItemModel, EvidenceRecordModel, Binding
- ``report_claim_contract.py``: ReportClaimModel, Degradation, Coverage
- ``report_section_contract.py``: ReportSectionModel, ReportOutlineModel, ReportModel
- ``report_map_contract.py``: EvidenceMapModel, Omission, Responses, ReportContractModel
"""
from __future__ import annotations

from .document_manifest_contract import DocumentRole
from .report_claim_contract import (
    _GENERIC_ENTITY_TYPES,
    EvidenceCoverageEntry,
    EvidenceDegradationModel,
    IndexedReportClaimModel,
    ReportClaimModel,
    _reject_dangling_ledger_refs,
    _role_family_key,
    _stakeholder_group_key,
)
from .report_evidence_contract import (
    EVIDENCE_ID_PATTERN,
    FORBIDDEN_EVIDENCE_TYPES,
    MIN_ACTION_VOICES_FOR_MEDIUM,
    SEED_DOC_ANCHOR_PREFIX,
    SIMULATION_SOURCE_KINDS,
    _NODE_UUID_RE,
    _STRICT,
    AgentLogRef,
    ClaimEvidenceBindingModel,
    ClaimType,
    ConfidenceLabel,
    EntailmentVerdict,
    EvidenceGraphOrigin,
    EvidenceItemModel,
    EvidenceRecordModel,
    EvidenceSourceKind,
    EvidenceType,
    _reject_graph_origin_as_document_fact,
    counts_for_confidence,
    has_two_action_voices,
)
from .report_evidence_types import (
    ConfidenceLabel,
    ClaimType,
    EvidenceType,
    EvidenceSourceKind,
    SIMULATION_SOURCE_KINDS,
    SEED_DOC_ANCHOR_PREFIX,
    EvidenceGraphOrigin,
    EntailmentVerdict,
    MIN_ACTION_VOICES_FOR_MEDIUM,
    _STRICT,
    _reject_graph_origin_as_document_fact,
    counts_for_confidence,
    has_two_action_voices,
)
from .report_map_contract import (
    EvidenceMapModel,
    EvidenceMapResponseModel,
    EvidenceMapResponseOmittedVariant,
    EvidenceMapResponseSuccessVariant,
    EvidenceOmissionModel,
    ReportContractModel,
    _hand_work_reason,
    _reject_inferred_evidence,
    _reject_label_resting_on_hand_work,
    _reject_mismatched_index_keys,
    _reject_unknown_global_refs,
    _require_quote_and_seed,
    _require_two_supporting_groups,
    _validate_claim_bindings,
)
from .report_section_contract import (
    ReportModel,
    ReportOutlineModel,
    ReportOutlineSectionModel,
    ReportSectionDataGapModel,
    ReportSectionHypothesisModel,
    ReportSectionKind,
    ReportSectionModel,
    ReportSectionUnverifiedStatementModel,
    ReportStatus,
    RunDegradationModel,
    SimulationSnapshotModel,
    _coerce_text_to_max_1000,
)

__all__ = [
    "AgentLogRef",
    "ClaimEvidenceBindingModel",
    "ClaimType",
    "ConfidenceLabel",
    "DocumentRole",
    "EVIDENCE_ID_PATTERN",
    "EntailmentVerdict",
    "EvidenceCoverageEntry",
    "EvidenceDegradationModel",
    "EvidenceGraphOrigin",
    "EvidenceItemModel",
    "EvidenceMapModel",
    "EvidenceMapResponseModel",
    "EvidenceMapResponseOmittedVariant",
    "EvidenceMapResponseSuccessVariant",
    "EvidenceOmissionModel",
    "EvidenceRecordModel",
    "EvidenceSourceKind",
    "EvidenceType",
    "FORBIDDEN_EVIDENCE_TYPES",
    "IndexedReportClaimModel",
    "MIN_ACTION_VOICES_FOR_MEDIUM",
    "ReportClaimModel",
    "ReportContractModel",
    "ReportModel",
    "ReportOutlineModel",
    "ReportOutlineSectionModel",
    "ReportSectionDataGapModel",
    "ReportSectionHypothesisModel",
    "ReportSectionKind",
    "ReportSectionModel",
    "ReportSectionUnverifiedStatementModel",
    "ReportStatus",
    "RunDegradationModel",
    "SEED_DOC_ANCHOR_PREFIX",
    "SIMULATION_SOURCE_KINDS",
    "SimulationSnapshotModel",
    "_GENERIC_ENTITY_TYPES",
    "_NODE_UUID_RE",
    "_STRICT",
    "_coerce_text_to_max_1000",
    "_hand_work_reason",
    "_reject_dangling_ledger_refs",
    "_reject_graph_origin_as_document_fact",
    "_reject_inferred_evidence",
    "_reject_label_resting_on_hand_work",
    "_reject_mismatched_index_keys",
    "_reject_unknown_global_refs",
    "_require_quote_and_seed",
    "_require_two_supporting_groups",
    "_role_family_key",
    "_stakeholder_group_key",
    "_validate_claim_bindings",
    "counts_for_confidence",
    "has_two_action_voices",
]
