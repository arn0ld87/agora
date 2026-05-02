"""
Contract-Tests für report_contract.py — gegen den echten Vertrag,
nicht gegen die Implementierung.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ConfidenceLabel,
    EvidenceItemModel,
    EvidenceMapModel,
    EvidenceType,
    ReportClaimModel,
    ReportContractModel,
)


# ---- EvidenceItemModel ----

def test_forbidden_evidence_type_rejected():
    """model_generated_inference darf NICHT als evidence stehen, nur in audit_trail."""
    with pytest.raises(ValidationError, match="model_generated_inference"):
        EvidenceItemModel(
            type=EvidenceType.model_generated_inference,
            source="x",
            snippet="x",
        )


def test_normal_evidence_passes():
    item = EvidenceItemModel(
        type=EvidenceType.graph_metric,
        source="simulation_metrics",
        snippet="echo_chamber_index: 0.42",
        match_score=0.7,
        supports_claim=True,
    )
    assert item.type == EvidenceType.graph_metric


def test_match_score_range():
    with pytest.raises(ValidationError):
        EvidenceItemModel(
            type=EvidenceType.graph_fact, source="x", snippet="x", match_score=1.5
        )


# ---- ReportClaimModel ----

def _make_evidence(match_score: float, supports: bool = True) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.graph_metric,
        source="x",
        snippet="snippet text",
        match_score=match_score,
        supports_claim=supports,
    )


def test_verified_requires_strong_match():
    """verified-Label verlangt match_score >= 0.85."""
    with pytest.raises(ValidationError, match="match_score >= 0.85"):
        ReportClaimModel(
            claim_id="claim_01",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.verified,
            confidence_score=0.9,
            evidence=[_make_evidence(0.4, True)],
        )


def test_verified_with_strong_match_passes():
    claim = ReportClaimModel(
        claim_id="claim_01",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.verified,
        confidence_score=0.92,
        evidence=[_make_evidence(0.88, True)],
    )
    assert claim.confidence_label == ConfidenceLabel.verified


def test_high_without_supports_claim_rejected():
    """Anti-Dekorations-Regel: high braucht supports_claim=True."""
    with pytest.raises(ValidationError, match="supports_claim=True"):
        ReportClaimModel(
            claim_id="claim_02",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.7,
            evidence=[_make_evidence(0.6, supports=False)],
        )


def test_low_confidence_no_supports_claim_required():
    """low/medium ohne supports_claim ist OK."""
    claim = ReportClaimModel(
        claim_id="claim_03",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.2,
        evidence=[_make_evidence(0.1, supports=False)],
    )
    assert claim.confidence_label == ConfidenceLabel.low


def test_claim_id_pattern():
    with pytest.raises(ValidationError):
        ReportClaimModel(
            claim_id="not_a_claim",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.low,
            confidence_score=0.1,
            evidence=[],
        )


# ---- ReportContractModel: Schema-Version-Drift unmöglich ----

def test_schema_version_must_be_2():
    """Literal[2] verhindert dass jemand schema_version=1 setzt."""
    with pytest.raises(ValidationError):
        ReportContractModel.model_validate({
            "schema_version": 1,
            "exported_at": "2026-05-02T10:00:00Z",
            "report": {
                "schema_version": 2,
                "report_id": "r", "simulation_id": "s", "graph_id": "g",
                "simulation_requirement": "x", "status": "completed",
            },
            "evidence": None,
        })


def test_evidence_map_must_be_v2():
    """EvidenceMap kann nicht mehr auf 1 zurückgezogen werden (Z. 567 Bug)."""
    with pytest.raises(ValidationError):
        EvidenceMapModel.model_validate({
            "schema_version": 1,
            "report_id": "r",
            "simulation_id": "s",
            "global_evidence": [],
            "sections": [],
        })


def test_full_contract_round_trip():
    """End-to-End: vollständiges, valides Report-Contract-Objekt."""
    payload = {
        "schema_version": 2,
        "exported_at": "2026-05-02T10:00:00Z",
        "report": {
            "schema_version": 2,
            "report_id": "report_abc",
            "simulation_id": "sim_abc",
            "graph_id": "graph_abc",
            "simulation_requirement": "Wahrnehmung simulieren",
            "status": "completed",
            "markdown_content": "# Bericht",
            "has_evidence": True,
            "evidence_sections": 1,
        },
        "evidence": {
            "schema_version": 2,
            "report_id": "report_abc",
            "simulation_id": "sim_abc",
            "global_evidence": [],
            "sections": [{
                "section_index": 1,
                "section_title": "Erster Eindruck",
                "section_summary": "Zusammenfassung",
                "claims": [{
                    "claim_id": "claim_01",
                    "claim_text": "Die Personas reagieren skeptisch.",
                    "confidence_label": "high",
                    "confidence_score": 0.78,
                    "evidence": [{
                        "type": "agent_action",
                        "source": "agent_log",
                        "snippet": "Persona kmu_ceo äußerte Bedenken.",
                        "match_score": 0.7,
                        "supports_claim": True,
                    }],
                    "audit_trail": [],
                }],
            }],
        },
    }
    contract = ReportContractModel.model_validate(payload)
    assert contract.schema_version == 2
    assert contract.evidence is not None
    assert len(contract.evidence.sections) == 1
