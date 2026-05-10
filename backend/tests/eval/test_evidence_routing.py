"""P2.1: Evidence-Routing-Tests für medium/high/verified Claims ohne Evidence-Anker.

Spec (PLAN.md §3.1):
- Claim ohne Evidence + medium/high/verified → data_gaps[] (kein Validator-Fehler)
- Claim ohne Evidence + low + score < 0.4 → hypotheses[] + data_gaps[]
- Claim ohne Evidence + low bleibt als Legacy-Claim (ReportClaimModel erlaubt das)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import ReportClaimModel, ReportSectionModel
from app.contracts.report_contract import ConfidenceLabel
from app.services.evidence_migrations import migrate_legacy_claims_to_anchored
from app.services.report_agent import ReportAgent


FIXTURE_MIXED = (
    Path(__file__).parent / "fixtures" / "bad" / "orphan_medium_high_claims.json"
)


# ---------------------------------------------------------------------------
# _finalize_section_claims: medium/high ohne Evidence → data_gaps, nicht claims
# ---------------------------------------------------------------------------

def test_medium_high_orphans_route_to_data_gaps() -> None:
    """medium + high Claims ohne Evidence landen in data_gaps, low in hypotheses."""
    raw = json.loads(FIXTURE_MIXED.read_text(encoding="utf-8"))

    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps = agent._finalize_section_claims(raw["claims"])

    # claim_03 ist low + score 0.18 < 0.4 → hypothesis + data_gap
    # claim_01 ist medium + score 0.55 → data_gap only
    # claim_02 ist high + score 0.72 → data_gap only
    assert claims == [], f"Erwartet keine finalisierten Claims, erhalten: {claims}"
    assert len(hypotheses) == 1, f"Erwartet 1 hypothesis (low-Claim), erhalten: {len(hypotheses)}"
    assert hypotheses[0]["hypothesis_text"].startswith("Datenschutzbedenken")

    # data_gaps: low-orphan + medium + high = 3
    assert len(data_gaps) == 3, f"Erwartet 3 data_gaps, erhalten: {len(data_gaps)}"
    gap_reasons = {gap["gap_reason"] for gap in data_gaps}
    assert gap_reasons == {"no_evidence_bound"}


def test_medium_high_orphan_section_validates() -> None:
    """ReportSectionModel validiert ohne Fehler, wenn orphans in data_gaps liegen."""
    raw = json.loads(FIXTURE_MIXED.read_text(encoding="utf-8"))

    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps = agent._finalize_section_claims(raw["claims"])

    section = ReportSectionModel.model_validate({
        "section_index": 1,
        "section_title": "Zielgruppenreaktion",
        "section_summary": "Analyse der Reaktionsmuster.",
        "claims": claims,
        "hypotheses": hypotheses,
        "data_gaps": data_gaps,
    })

    assert len(section.claims) == 0
    assert len(section.data_gaps) == 3
    assert len(section.hypotheses) == 1


# ---------------------------------------------------------------------------
# ReportClaimModel: Validator-Verhalten direkt prüfen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["medium", "high"])
def test_claim_model_rejects_evidence_empty_for_non_low(label: str) -> None:
    """ReportClaimModel.non_low_claims_need_evidence schlägt für medium/high zu."""
    with pytest.raises(ValidationError, match="mindestens eine Evidence"):
        ReportClaimModel(
            claim_id="claim_01",
            claim_text="Testaussage mit genug Zeichen",
            confidence_label=label,
            confidence_score=0.6,
            evidence=[],
        )


def test_claim_model_allows_empty_evidence_for_low() -> None:
    """low-Confidence-Claims dürfen keine Evidence haben (Legacy-Kompatibilität)."""
    claim = ReportClaimModel(
        claim_id="claim_01",
        claim_text="Testaussage mit genug Zeichen",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.2,
        evidence=[],
    )
    assert claim.confidence_label == ConfidenceLabel.low


# ---------------------------------------------------------------------------
# migrate_legacy_claims_to_anchored: Migration von bestehenden Maps
# ---------------------------------------------------------------------------

def test_migrate_legacy_none_returns_none() -> None:
    assert migrate_legacy_claims_to_anchored(None) is None


def test_migrate_legacy_empty_sections() -> None:
    raw: dict = {"schema_version": 2, "sections": []}
    result = migrate_legacy_claims_to_anchored(raw)
    assert result is not None
    assert result["sections"] == []


def test_migrate_legacy_medium_claim_moved_to_data_gap() -> None:
    raw = {
        "schema_version": 2,
        "sections": [{
            "section_index": 1,
            "section_title": "Test",
            "section_summary": "summary",
            "claims": [{
                "claim_id": "claim_01",
                "claim_text": "Behauptung ohne Beleg, aber mittleres Vertrauen.",
                "confidence_label": "medium",
                "confidence_score": 0.5,
                "evidence": [],
                "audit_trail": [],
            }],
        }],
    }

    result = migrate_legacy_claims_to_anchored(raw)
    assert result is not None
    section = result["sections"][0]
    assert section["claims"] == []
    assert len(section["data_gaps"]) == 1
    assert section["data_gaps"][0]["gap_reason"] == "no_evidence_bound"


def test_migrate_legacy_low_claim_survives() -> None:
    """Low-confidence Claims ohne Evidence werden nicht migriert."""
    raw = {
        "schema_version": 2,
        "sections": [{
            "section_index": 1,
            "section_title": "Test",
            "section_summary": "summary",
            "claims": [{
                "claim_id": "claim_01",
                "claim_text": "Schwache Indiz-Behauptung ohne direkten Beleg.",
                "confidence_label": "low",
                "confidence_score": 0.2,
                "evidence": [],
                "audit_trail": [],
            }],
        }],
    }

    result = migrate_legacy_claims_to_anchored(raw)
    assert result is not None
    section = result["sections"][0]
    assert len(section["claims"]) == 1
    assert section["data_gaps"] == []


def test_migrate_legacy_mixed_section() -> None:
    """In einer Section: medium-Claim → data_gap, low-Claim → bleibt."""
    raw = {
        "schema_version": 2,
        "sections": [{
            "section_index": 1,
            "section_title": "Gemischte Claims",
            "section_summary": "summary",
            "claims": [
                {
                    "claim_id": "claim_01",
                    "claim_text": "Mittlere Konfidenz ohne Beleg, nicht haltbar.",
                    "confidence_label": "medium",
                    "confidence_score": 0.5,
                    "evidence": [],
                    "audit_trail": [],
                },
                {
                    "claim_id": "claim_02",
                    "claim_text": "Schwache Behauptung auf Basis von Indizien.",
                    "confidence_label": "low",
                    "confidence_score": 0.15,
                    "evidence": [],
                    "audit_trail": [],
                },
            ],
        }],
    }

    result = migrate_legacy_claims_to_anchored(raw)
    assert result is not None
    section = result["sections"][0]
    assert len(section["claims"]) == 1
    assert section["claims"][0]["claim_id"] == "claim_02"
    assert len(section["data_gaps"]) == 1
    assert section["data_gaps"][0]["gap_reason"] == "no_evidence_bound"
