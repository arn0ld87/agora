"""Drift-Guard fuer ADR-0002 Anker 3 + 4 + 5 (Sub-Slice M11.7b).

Pinnt:
- ``EvidenceSourceKind`` als geschlossenes 4-Werte-Set (Anker 3).
- ``agent_quote_needs_stakeholder_group`` auf EvidenceItemModel.
- ``cross_stakeholder_for_high`` auf ReportClaimModel (Anker 4).
- ``reject_inferred_in_high_confidence`` auf ReportClaimModel (Anker 5).

Spec: docu/decisions/0002-evidence-gating.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import (
    ConfidenceLabel,
    EvidenceItemModel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)


def _agent_quote(group: str, *, supports: bool = True, score: float = 0.7) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.agent_interview,
        source="agent-log",
        snippet=f"Persona aus {group}: Beispiel-Aussage.",
        match_score=score,
        supports_claim=supports,
        source_kind=EvidenceSourceKind.agent_quote,
        persona_stakeholder_group=group,
    )


def _seed_evidence(*, supports: bool = True, score: float = 0.7) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.graph_metric,
        source="seed",
        snippet="Seed-Korpus-Datenpunkt.",
        match_score=score,
        supports_claim=supports,
    )


def _inferred(*, supports: bool = True, score: float = 0.6) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.graph_fact,
        source="reasoning",
        snippet="Abgeleiteter Hinweis ohne Primaerquelle.",
        match_score=score,
        supports_claim=supports,
        source_kind=EvidenceSourceKind.inferred,
    )


def test_source_kind_default_seed_corpus() -> None:
    """Default sichert Backward-Compat fuer Fixtures ohne explizites Feld."""
    item = EvidenceItemModel(
        type=EvidenceType.graph_metric,
        source="x",
        snippet="snippet",
    )
    assert item.source_kind == EvidenceSourceKind.seed_corpus
    assert item.persona_stakeholder_group is None


def test_agent_quote_requires_stakeholder_group() -> None:
    """source_kind=agent_quote ohne persona_stakeholder_group -> ValidationError."""
    with pytest.raises(ValidationError, match="persona_stakeholder_group"):
        EvidenceItemModel(
            type=EvidenceType.agent_interview,
            source="agent-log",
            snippet="Persona aeusserte sich.",
            source_kind=EvidenceSourceKind.agent_quote,
            persona_stakeholder_group=None,
        )

    item = EvidenceItemModel(
        type=EvidenceType.agent_interview,
        source="agent-log",
        snippet="Persona aeusserte sich.",
        source_kind=EvidenceSourceKind.agent_quote,
        persona_stakeholder_group="Geschaeftsfuehrung",
    )
    assert item.persona_stakeholder_group == "Geschaeftsfuehrung"


def test_high_needs_two_stakeholder_groups() -> None:
    """high/verified: agent_quote-Evidence aus mindestens 2 verschiedenen Gruppen."""
    # Single-Group -> Fehler
    with pytest.raises(ValidationError, match="2 unterschiedlichen Stakeholder-Gruppen"):
        ReportClaimModel(
            claim_id="claim_01",
            claim_text="High-Claim mit nur einer Stakeholder-Gruppe.",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.78,
            evidence=[_agent_quote("Geschaeftsfuehrung")],
        )

    # Zwei verschiedene Gruppen -> ok
    claim = ReportClaimModel(
        claim_id="claim_02",
        claim_text="High-Claim mit zwei Stakeholder-Gruppen.",
        confidence_label=ConfidenceLabel.high,
        confidence_score=0.78,
        evidence=[
            _agent_quote("Geschaeftsfuehrung"),
            _agent_quote("IT-Abteilung"),
        ],
    )
    assert claim.confidence_label == ConfidenceLabel.high

    # Verified analog: zwei Gruppen + match_score >= 0.85
    claim_verified = ReportClaimModel(
        claim_id="claim_03",
        claim_text="Verified-Claim mit zwei Gruppen.",
        confidence_label=ConfidenceLabel.verified,
        confidence_score=0.92,
        evidence=[
            _agent_quote("Geschaeftsfuehrung", score=0.88),
            _agent_quote("Vertrieb", score=0.86),
        ],
    )
    assert claim_verified.confidence_label == ConfidenceLabel.verified


def test_high_rejects_inferred_evidence() -> None:
    """high/verified darf keine source_kind=inferred-Evidence enthalten."""
    with pytest.raises(ValidationError, match="source_kind=inferred"):
        ReportClaimModel(
            claim_id="claim_04",
            claim_text="High-Claim mit unzulaessiger inferred-Evidence.",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.78,
            evidence=[
                _agent_quote("Geschaeftsfuehrung"),
                _agent_quote("Vertrieb"),
                _inferred(),
            ],
        )


def test_low_and_medium_unaffected() -> None:
    """low/medium duerfen single-group oder inferred-Evidence haben."""
    low_claim = ReportClaimModel(
        claim_id="claim_05",
        claim_text="Low-Claim mit nur einer Stakeholder-Gruppe.",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.2,
        evidence=[_agent_quote("Geschaeftsfuehrung", supports=False)],
    )
    assert low_claim.confidence_label == ConfidenceLabel.low

    medium_claim = ReportClaimModel(
        claim_id="claim_06",
        claim_text="Medium-Claim mit inferred-Evidence.",
        confidence_label=ConfidenceLabel.medium,
        confidence_score=0.5,
        evidence=[_seed_evidence(), _inferred()],
    )
    assert medium_claim.confidence_label == ConfidenceLabel.medium


def test_enum_values_pinned() -> None:
    """Drift-Guard: genau 4 Werte, exakt diese Strings."""
    expected = {"seed_corpus", "agent_quote", "graph_relation", "inferred"}
    actual = {kind.value for kind in EvidenceSourceKind}
    assert actual == expected
    assert len(EvidenceSourceKind) == 4
