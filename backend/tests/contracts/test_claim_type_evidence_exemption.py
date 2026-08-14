"""Issue #1301 — Claim-Typ-Differenzierung.

Vorher behandelte die Evidence-Bindung jeden Claim gleich: Ueberschriften,
Empfehlungen und analytische Uebergangssaetze wurden wie empirische
Tatsachenbehauptungen gegen den Evidence-Index geprueft und bekamen
unangemessen niedrige Confidence, weil sie naturgemaess keine direkte
Evidence haben.

``ClaimType`` (``empirical`` default, plus ``analytical``/``recommendation``/
``structural``) exemptiert die drei nicht-empirischen Typen von der
Evidence-Index-Pruefung — auf beiden Claim-Shapes, die diese Pruefung
unabhaengig implementieren:

- ``ReportClaimModel`` (``non_low_claims_need_evidence`` /
  ``agent_grounded_for_medium``)
- ``IndexedReportClaimModel`` (``require_binding_for_non_low_claim``) — die
  tatsaechlich verwendete Claim-Form innerhalb ``ReportSectionModel.claims``
  (EvidenceMap schema_version=3).

ADR-0002-Grenze: keiner der fuenf Hartanker (Prompt-Block, Hedge-Snapshot,
``EvidenceSourceKind``-Enum, ``cross_stakeholder_for_high``,
``reject_inferred_in_high_confidence``) wird beruehrt. Beide geaenderten
Validatoren gehoeren nicht zu den Hartankern.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ClaimType,
    IndexedReportClaimModel,
    ReportClaimModel,
    ReportSectionModel,
)


class TestClaimTypeDefaultsToEmpirical:
    def test_report_claim_model_defaults_without_the_field(self) -> None:
        """Bestandsberichte ohne ``claim_type``-Feld bleiben lesbar."""
        claim = ReportClaimModel(
            claim_id="claim_01",
            claim_text="Ein Bestandsclaim ohne explizites claim_type-Feld.",
            confidence_label="low",
            confidence_score=0.5,
            evidence=[],
        )
        assert claim.claim_type == ClaimType.empirical

    def test_indexed_report_claim_model_defaults_without_the_field(self) -> None:
        claim = IndexedReportClaimModel(
            claim_id="claim_01",
            claim_text="Ein Bestandsclaim ohne explizites claim_type-Feld.",
            confidence_label="low",
            confidence_score=0.5,
            evidence=[],
        )
        assert claim.claim_type == ClaimType.empirical


class TestNonEmpiricalClaimsAreExemptFromTheEvidenceIndexCheck:
    """Akzeptanzkriterium: nicht-empirische Claims werden nicht gegen den
    Evidence-Index geprueft."""

    @pytest.mark.parametrize("claim_type", ["structural", "recommendation", "analytical"])
    def test_report_claim_model_medium_without_evidence_is_allowed(self, claim_type: str) -> None:
        claim = ReportClaimModel(
            claim_id="claim_02",
            claim_text="Ein nicht-empirischer Claim ohne jede Evidence.",
            confidence_label="medium",
            confidence_score=0.7,
            evidence=[],
            claim_type=claim_type,
        )
        assert claim.claim_type == ClaimType(claim_type)

    @pytest.mark.parametrize("claim_type", ["structural", "recommendation", "analytical"])
    def test_indexed_report_claim_model_medium_without_binding_is_allowed(
        self, claim_type: str
    ) -> None:
        claim = IndexedReportClaimModel(
            claim_id="claim_02",
            claim_text="Ein nicht-empirischer Claim ohne jedes Evidence-Binding.",
            confidence_label="medium",
            confidence_score=0.7,
            evidence=[],
            claim_type=claim_type,
        )
        assert claim.claim_type == ClaimType(claim_type)

    def test_report_claim_model_low_needs_no_exemption_either_way(self) -> None:
        """Gegenprobe: low brauchte nie Evidence — die Ausnahme aendert daran nichts."""
        claim = ReportClaimModel(
            claim_id="claim_03",
            claim_text="Ein empirischer low-Claim ohne Evidence — schon immer erlaubt.",
            confidence_label="low",
            confidence_score=0.5,
            evidence=[],
            claim_type="empirical",
        )
        assert claim.confidence_label.value == "low"


class TestEmpiricalClaimsStillRequireEvidence:
    """Gegenprobe: die Ausnahme betrifft ausschliesslich die drei
    nicht-empirischen Typen — ``empirical`` (Default) bleibt so streng wie
    vor #1301."""

    def test_report_claim_model_medium_without_evidence_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="mindestens eine Evidence"):
            ReportClaimModel(
                claim_id="claim_04",
                claim_text="Ein empirischer Claim ohne jede Evidence.",
                confidence_label="medium",
                confidence_score=0.7,
                evidence=[],
                claim_type="empirical",
            )

    def test_indexed_report_claim_model_medium_without_binding_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Evidence-Binding"):
            IndexedReportClaimModel(
                claim_id="claim_04",
                claim_text="Ein empirischer Claim ohne jedes Evidence-Binding.",
                confidence_label="medium",
                confidence_score=0.7,
                evidence=[],
                claim_type="empirical",
            )

    def test_default_claim_type_is_still_rejected_like_before(self) -> None:
        """Ohne explizites claim_type-Feld gilt der Default empirical — das
        alte, strenge Verhalten bleibt fuer Bestandsdaten unveraendert."""
        with pytest.raises(ValidationError):
            ReportClaimModel(
                claim_id="claim_05",
                claim_text="Ein Bestandsclaim ohne claim_type, ohne Evidence.",
                confidence_label="high",
                confidence_score=0.85,
                evidence=[],
            )


class TestAgentGroundedForMediumExemption:
    """Issue #1301 auch fuer die zweite ReportClaimModel-Evidence-Regel:
    agent_grounded_for_medium (agent_quote + seed_corpus fuer medium)."""

    def test_non_empirical_medium_skips_the_agent_grounded_requirement(self) -> None:
        claim = ReportClaimModel(
            claim_id="claim_06",
            claim_text="Wir empfehlen einen stufenweisen Rollout.",
            confidence_label="medium",
            confidence_score=0.7,
            evidence=[],
            claim_type="recommendation",
        )
        assert claim.claim_type == ClaimType.recommendation

    def test_empirical_medium_still_needs_agent_quote_and_seed_corpus(self) -> None:
        with pytest.raises(ValidationError, match="agent_grounded"):
            ReportClaimModel(
                claim_id="claim_07",
                claim_text="Ein empirischer medium-Claim mit nur einer Quellengattung.",
                confidence_label="medium",
                confidence_score=0.7,
                evidence=[
                    {
                        "type": "seed_document",
                        "source": "insight_forge",
                        "snippet": "Beleg aus dem Dokument.",
                        "source_kind": "seed_corpus",
                    },
                ],
                claim_type="empirical",
            )

    def test_well_formed_empirical_medium_claim_still_works(self) -> None:
        """Gegenprobe: ein korrekt gebundener empirischer medium-Claim
        validiert unveraendert."""
        claim = ReportClaimModel(
            claim_id="claim_08",
            claim_text="Ein gut belegter empirischer Claim.",
            confidence_label="medium",
            confidence_score=0.7,
            evidence=[
                {
                    "type": "agent_interview",
                    "source": "interview_agents",
                    "snippet": "Zitat aus dem Interview.",
                    "source_kind": "agent_quote",
                    "quote": "Ein woertliches Zitat.",
                    "persona_stakeholder_group": "kunden",
                },
                {
                    "type": "seed_document",
                    "source": "insight_forge",
                    "snippet": "Beleg aus dem Dokument.",
                    "source_kind": "seed_corpus",
                },
            ],
            claim_type="empirical",
        )
        assert claim.confidence_label.value == "medium"


class TestReportSectionModelEndToEnd:
    """Der tatsaechliche Verwendungsort: ReportSectionModel.claims ist eine
    list[IndexedReportClaimModel] (EvidenceMap schema_version=3)."""

    def test_section_with_a_structural_claim_validates(self) -> None:
        section = ReportSectionModel(
            section_index=1,
            section_title="Testsektion",
            section_summary="Zusammenfassung der Testsektion.",
            claims=[
                {
                    "claim_id": "claim_09",
                    "claim_text": "## Zusammenfassung der Ergebnisse",
                    "confidence_label": "medium",
                    "confidence_score": 0.6,
                    "evidence": [],
                    "claim_type": "structural",
                },
            ],
        )
        assert len(section.claims) == 1
        assert section.claims[0].claim_type == ClaimType.structural

    def test_section_with_an_unbound_empirical_claim_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReportSectionModel(
                section_index=1,
                section_title="Testsektion",
                section_summary="Zusammenfassung der Testsektion.",
                claims=[
                    {
                        "claim_id": "claim_10",
                        "claim_text": "Ein empirischer Claim ohne Binding in der Section.",
                        "confidence_label": "medium",
                        "confidence_score": 0.6,
                        "evidence": [],
                        "claim_type": "empirical",
                    },
                ],
            )
