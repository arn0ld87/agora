"""M11.7c: ReportSectionModel.hypotheses[] Contract-Guards."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import ReportSectionHypothesisModel
from app.contracts.report_contract import (
    ConfidenceLabel,
    ReportClaimModel,
    ReportSectionDataGapModel,
    ReportSectionModel,
)


def _claim() -> ReportClaimModel:
    return ReportClaimModel(
        claim_id="claim_01",
        claim_text="Ein belegter Claim mit ausreichend langem Text.",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.2,
        evidence=[],
    )


def test_section_hypotheses_default_empty() -> None:
    section = ReportSectionModel(
        section_index=1,
        section_title="Abschnitt",
        section_summary="Zusammenfassung",
        claims=[_claim()],
    )

    assert section.hypotheses == []
    assert section.data_gaps == []


def test_section_accepts_no_claims_when_gaps_are_explicit() -> None:
    section = ReportSectionModel(
        section_index=1,
        section_title="Abschnitt",
        section_summary="Zusammenfassung",
        claims=[],
        hypotheses=[
            {
                "hypothesis_id": "hypothesis_01",
                "hypothesis_text": "Indizien legen eine zweite Zielgruppe nahe.",
                "rationale": "Keine direkte Evidence gebunden; deshalb kein Claim.",
                "suggested_evidence": ["Persona-Interview aus Gruppe B ergänzen"],
            }
        ],
        data_gaps=[
            {
                "gap_id": "gap_01",
                "claim_text": "Indizien legen eine zweite Zielgruppe nahe.",
                "gap_reason": "no_evidence_bound",
                "suggested_fix": "Persona-Interview aus Gruppe B ergänzen",
            }
        ],
    )

    assert section.claims == []
    assert section.data_gaps[0].gap_reason == "no_evidence_bound"


def test_section_accepts_hypothesis_without_evidence() -> None:
    section = ReportSectionModel(
        section_index=1,
        section_title="Abschnitt",
        section_summary="Zusammenfassung",
        claims=[_claim()],
        hypotheses=[
            {
                "hypothesis_id": "hypothesis_01",
                "hypothesis_text": "Indizien legen eine zweite Zielgruppe nahe.",
                "rationale": "Der Abschnitt enthält Signale, aber noch keine direkte Evidence.",
                "suggested_evidence": ["Persona-Interview aus Gruppe B ergänzen"],
            }
        ],
    )

    assert section.hypotheses[0].hypothesis_id == "hypothesis_01"
    assert section.hypotheses[0].suggested_evidence == [
        "Persona-Interview aus Gruppe B ergänzen"
    ]


def test_hypothesis_id_pattern_is_pinned() -> None:
    with pytest.raises(ValidationError, match="hypothesis_id"):
        ReportSectionHypothesisModel(
            hypothesis_id="h_1",
            hypothesis_text="Hypothese mit ausreichend langem Text.",
            rationale="Begründung mit ausreichend langem Text.",
        )


def test_hypothesis_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra"):
        ReportSectionHypothesisModel.model_validate(
            {
                "hypothesis_id": "hypothesis_01",
                "hypothesis_text": "Hypothese mit ausreichend langem Text.",
                "rationale": "Begründung mit ausreichend langem Text.",
                "evidence": [],
            }
        )


def test_data_gap_id_pattern_is_pinned() -> None:
    with pytest.raises(ValidationError, match="gap_id"):
        ReportSectionDataGapModel(
            gap_id="g_1",
            claim_text="Nicht belegbarer Claim mit ausreichend langem Text.",
            gap_reason="no_evidence_bound",
        )
