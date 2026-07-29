"""Drift-Guard fuer ADR-0002 Anker 3 + 4 + 5 (Sub-Slice M11.7b).

Pinnt:
- ``EvidenceSourceKind`` als geschlossenes 4-Werte-Set (Anker 3).
- ``agent_quote_needs_stakeholder_group`` auf EvidenceItemModel.
- ``cross_stakeholder_for_high`` auf ReportClaimModel (Anker 4).
- ``reject_inferred_in_high_confidence`` auf ReportClaimModel (Anker 5).

Spec: docs/decisions/0002-evidence-gating.md.
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
        quote=f"Original-Zitat aus {group}.",
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
        source_kind=EvidenceSourceKind.seed_corpus,
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


def test_source_kind_default_is_inferred_not_seed_corpus() -> None:
    """Ohne explizite Angabe ist die Herkunft unbekannt — also abgeleitet.

    Vorher war der Default ``seed_corpus``: jedes Item ohne Angabe wurde damit
    zum Dokumentfakt erklaert, auch Agentenaktionen und Web-Treffer. Der
    konservative Default laesst alte Fixtures weiter laden, verweigert ihnen
    aber den unverdienten Seed-Status (``reject_inferred_in_high_confidence``
    greift dann, ADR-0002 Anker 5).
    """
    item = EvidenceItemModel(
        type=EvidenceType.graph_metric,
        source="x",
        snippet="snippet",
    )
    assert item.source_kind == EvidenceSourceKind.inferred
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


def test_contradicting_quotes_dont_satisfy_cross_stakeholder() -> None:
    """Gemini-Followup PR #343: nur supports_claim=True zaehlt zur 2-Gruppen-Schwelle.

    Zwei agent_quotes aus unterschiedlichen Gruppen, beide mit supports_claim=False,
    duerfen ein high-Label nicht rechtfertigen. Sonst koennte das Evidence-Gate
    durch widersprechende Stimmen umgangen werden.
    """
    with pytest.raises(ValidationError, match="supports_claim=True"):
        ReportClaimModel(
            claim_id="claim_71",
            claim_text="High-Claim, der nur durch widersprechende Quotes gestuetzt waere.",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.78,
            evidence=[
                _seed_evidence(supports=True),  # erfuellt orphan-Test
                _agent_quote("Geschaeftsfuehrung", supports=False),
                _agent_quote("IT-Abteilung", supports=False),
            ],
        )

    # Mix: 1 unterstuetzend + 1 widersprechend reicht nicht.
    with pytest.raises(ValidationError, match="supports_claim=True"):
        ReportClaimModel(
            claim_id="claim_72",
            claim_text="Nur eine Gruppe stuetzt — die andere widerspricht.",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.78,
            evidence=[
                _agent_quote("Geschaeftsfuehrung", supports=True),
                _agent_quote("IT-Abteilung", supports=False),
            ],
        )


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


def test_low_unaffected_by_cross_stakeholder_rule() -> None:
    """low darf single-group oder inferred-Evidence haben — kein
    Cross-Stakeholder- und kein agent_grounded-Zwang (ADR-0002 seed_only → low)."""
    low_claim = ReportClaimModel(
        claim_id="claim_05",
        claim_text="Low-Claim mit nur einer Stakeholder-Gruppe.",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.2,
        evidence=[_agent_quote("Geschaeftsfuehrung", supports=False)],
    )
    assert low_claim.confidence_label == ConfidenceLabel.low


def test_medium_needs_agent_grounded_evidence() -> None:
    """medium verlangt ADR-0002 Stufe agent_grounded: mind. 1 agent_quote
    UND mind. 1 seed_corpus (Issue #906 Defekt 1). Seed-only oder
    inferred-only ist unzureichend und wird abgelehnt."""
    medium_claim = ReportClaimModel(
        claim_id="claim_06",
        claim_text="Medium-Claim mit agent_grounded-Evidence.",
        confidence_label=ConfidenceLabel.medium,
        confidence_score=0.5,
        evidence=[_seed_evidence(), _agent_quote("Vertrieb")],
    )
    assert medium_claim.confidence_label == ConfidenceLabel.medium

    with pytest.raises(ValidationError, match="agent_quote"):
        ReportClaimModel(
            claim_id="claim_07",
            claim_text="Medium-Claim mit nur Seed-Evidence.",
            confidence_label=ConfidenceLabel.medium,
            confidence_score=0.5,
            evidence=[_seed_evidence(), _inferred()],
        )


def test_enum_values_pinned() -> None:
    """Drift-Guard: genau diese 6 Werte, exakt diese Strings.

    Erweitert um ``agent_action`` und ``web_source`` (Report-Trust-Slice).
    Additiv — die urspruenglichen vier Werte bleiben unveraendert und die
    Confidence-Anker werten weiterhin nur ``agent_quote`` als
    Stakeholder-Stimme und ``seed_corpus`` als Dokumentfakt.
    """
    expected = {
        "seed_corpus",
        "agent_quote",
        "agent_action",
        "graph_relation",
        "web_source",
        "inferred",
    }
    actual = {kind.value for kind in EvidenceSourceKind}
    assert actual == expected
    assert len(EvidenceSourceKind) == 6


def test_agent_action_does_not_count_as_stakeholder_voice() -> None:
    """agent_action ist Simulationsverhalten, keine Stakeholder-Aussage.

    Zwei Agentenaktionen aus unterschiedlichen Gruppen duerfen ein
    high-Label nicht rechtfertigen — nur ``agent_quote`` zaehlt (Anker 4).
    """
    def _action(group: str) -> EvidenceItemModel:
        return EvidenceItemModel(
            type=EvidenceType.agent_action,
            source="agent-log",
            snippet=f"Agent aus {group} teilte den Beitrag.",
            match_score=0.9,
            supports_claim=True,
            source_kind=EvidenceSourceKind.agent_action,
            persona_stakeholder_group=group,
        )

    with pytest.raises(ValidationError, match="2 unterschiedlichen Stakeholder-Gruppen"):
        ReportClaimModel(
            claim_id="claim_80",
            claim_text="High-Claim, der nur auf Agentenaktionen beruht.",
            confidence_label=ConfidenceLabel.high,
            confidence_score=0.78,
            evidence=[_action("Lehrkraefte"), _action("Eltern")],
        )
