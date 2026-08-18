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

def test_orphan_claims_route_to_hypotheses_and_data_gaps() -> None:
    """Claims ohne stützende Evidence werden Hypothesen — unabhängig vom Label.

    Vorher landeten medium/high-Orphans nur in ``data_gaps``: die Behauptung
    selbst verschwand aus dem Report, obwohl sie inhaltlich weiter im Raum
    stand. Ein unbelegtes ``high`` ist aber keine Datenlücke, sondern eine
    unbelegte Behauptung — sie gehört sichtbar als Hypothese markiert
    (P0-5). Das Label allein darf nicht darüber entscheiden, ob eine
    Aussage ungeprüft aus dem Report fällt.
    """
    raw = json.loads(FIXTURE_MIXED.read_text(encoding="utf-8"))

    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps, _decisions = agent._finalize_section_claims(raw["claims"])

    assert claims == [], f"Erwartet keine finalisierten Claims, erhalten: {claims}"
    # claim_01 (medium), claim_02 (high), claim_03 (low) — alle ohne Evidence.
    assert len(hypotheses) == 3, (
        f"Erwartet 3 Hypothesen (alle Orphans), erhalten: {len(hypotheses)}"
    )
    hypothesis_texts = [h["hypothesis_text"] for h in hypotheses]
    assert any(text.startswith("Datenschutzbedenken") for text in hypothesis_texts)

    # Der Evidence-Index dieses Agents ist leer — zu den Aussagen liegt
    # tatsächlich nichts vor, und genau dann ist ein Data Gap richtig. Ein
    # bloß gescheitertes Binding erzeugt seit der Data-Gap-Semantik keinen
    # mehr (siehe tests/regression/test_data_gap_semantics.py).
    assert len(data_gaps) == 3, f"Erwartet 3 data_gaps, erhalten: {len(data_gaps)}"
    gap_reasons = {gap["gap_reason"] for gap in data_gaps}
    assert gap_reasons == {"source_information_absent"}


def test_medium_high_orphan_section_validates() -> None:
    """ReportSectionModel validiert ohne Fehler, wenn orphans in data_gaps liegen."""
    raw = json.loads(FIXTURE_MIXED.read_text(encoding="utf-8"))

    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps, _decisions = agent._finalize_section_claims(raw["claims"])

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
    assert len(section.hypotheses) == 3


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


def test_migrate_legacy_new_gap_id_avoids_collision_with_gapped_existing_ids() -> None:
    """Issue #986: Bestands-Gaps gap_01/gap_03 duerfen keine gap_03-Kollision erzeugen.

    ``index = len(data_gaps) + 1`` zaehlte hier vorher naiv die Bestandsliste
    (2 Eintraege) hoch und vergab ``gap_03`` erneut — ein Duplikat mit dem
    bereits vorhandenen ``gap_03``. Der Test prueft die tatsaechliche
    Invariante direkt: alle gap_id-Werte der Section sind nach der Migration
    paarweise verschieden, und die neue ID liegt hinter dem hoechsten
    Bestands-Suffix.
    """
    raw = {
        "schema_version": 2,
        "sections": [{
            "section_index": 1,
            "section_title": "Test",
            "section_summary": "summary",
            "data_gaps": [
                {"gap_id": "gap_01", "claim_text": "Bestand 1", "gap_reason": "manual"},
                {"gap_id": "gap_03", "claim_text": "Bestand 2", "gap_reason": "manual"},
            ],
            "claims": [{
                "claim_id": "claim_01",
                "claim_text": "Mittlere Konfidenz ohne Beleg, nicht haltbar.",
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
    gap_ids = [gap["gap_id"] for gap in section["data_gaps"]]
    assert len(gap_ids) == len(set(gap_ids)), (
        f"gap_id-Kollision nach Migration: {gap_ids}"
    )
    assert "gap_04" in gap_ids


def test_migrate_legacy_two_new_gaps_in_same_section_are_collision_free() -> None:
    """Issue #986: Zwei ankerlose Claims in derselben Section erzeugen

    untereinander kollisionsfreie neue gap_ids, auch gegen den Bestand.
    """
    raw = {
        "schema_version": 2,
        "sections": [{
            "section_index": 1,
            "section_title": "Test",
            "section_summary": "summary",
            "data_gaps": [
                {"gap_id": "gap_01", "claim_text": "Bestand", "gap_reason": "manual"},
            ],
            "claims": [
                {
                    "claim_id": "claim_01",
                    "claim_text": "Erste Behauptung ohne Beleg, mittlere Konfidenz.",
                    "confidence_label": "medium",
                    "confidence_score": 0.5,
                    "evidence": [],
                    "audit_trail": [],
                },
                {
                    "claim_id": "claim_02",
                    "claim_text": "Zweite Behauptung ohne Beleg, hohe Konfidenz.",
                    "confidence_label": "high",
                    "confidence_score": 0.7,
                    "evidence": [],
                    "audit_trail": [],
                },
            ],
        }],
    }

    result = migrate_legacy_claims_to_anchored(raw)
    assert result is not None
    section = result["sections"][0]
    assert section["claims"] == []
    gap_ids = [gap["gap_id"] for gap in section["data_gaps"]]
    assert len(gap_ids) == 3
    assert len(gap_ids) == len(set(gap_ids)), (
        f"gap_id-Kollision nach Migration: {gap_ids}"
    )
