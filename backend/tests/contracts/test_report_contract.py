"""
Contract-Tests für report_contract.py — gegen den echten Vertrag,
nicht gegen die Implementierung.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ConfidenceLabel,
    EntailmentVerdict,
    EvidenceItemModel,
    EvidenceMapModel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
    ReportContractModel,
    ReportOutlineModel,
    ReportOutlineSectionModel,
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


def _agent_quote_evidence(group: str, score: float = 0.88) -> EvidenceItemModel:
    """Helfer fuer high/verified-Tests nach ADR-0002 Anker 4 (Sub-Slice M11.7b).

    Enthält ein nicht-leeres ``quote``-Feld, sodass die Evidence auch die
    agent_grounded-Stufe (medium, ADR-0002 Z. 54) erfuellt.
    """
    return EvidenceItemModel(
        type=EvidenceType.agent_interview,
        source="agent-log",
        snippet=f"Aussage aus {group}.",
        quote=f"Original-Zitat aus {group}.",
        match_score=score,
        # Issue #1160 B: ``supports_claim`` ist laut Contract-Kommentar genau
        # dann True, wenn das Entailment SUPPORTED lautet. Der Helfer hat das
        # bisher behauptet, ohne das Urteil mitzuliefern — seit `verified` das
        # Urteil verlangt, muss die Fixture den Vertrag vollstaendig erfuellen.
        entailment=EntailmentVerdict.SUPPORTED,
        supports_claim=True,
        source_kind=EvidenceSourceKind.agent_quote,
        persona_stakeholder_group=group,
    )


def _seed_evidence() -> EvidenceItemModel:
    """Helfer fuer seed_corpus-Evidence (ADR-0002 Stufe seed_only/agent_grounded)."""
    return EvidenceItemModel(
        type=EvidenceType.graph_fact,
        source="seed-doc",
        snippet="Seed-Dokument-Auszug mit genug Text.",
        supports_claim=True,
        source_kind=EvidenceSourceKind.seed_corpus,
    )


def test_verified_with_strong_match_passes():
    # ADR-0002 Anker 4: verified verlangt zwei Stakeholder-Gruppen via agent_quote.
    claim = ReportClaimModel(
        claim_id="claim_01",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.verified,
        confidence_score=0.92,
        evidence=[
            _agent_quote_evidence("Geschaeftsfuehrung", score=0.88),
            _agent_quote_evidence("Vertrieb", score=0.86),
        ],
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


def test_medium_claim_without_evidence_is_rejected():
    """P2.1: Claims oberhalb von low brauchen mindestens einen Evidence-Anker."""
    with pytest.raises(ValidationError, match="mindestens eine Evidence"):
        ReportClaimModel(
            claim_id="claim_04",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.medium,
            confidence_score=0.45,
            evidence=[],
        )


# ---- ADR-0002 agent_grounded: medium-Validator (Issue #906 Defekt 1) ----


def test_medium_with_only_seed_corpus_is_rejected():
    """ADR-0002 Stufe seed_only → max low. medium mit ausschließlich seed_corpus-
    Evidence ist verboten; das Label muss low lauten. Bisher passierte das
    unbeanstandet, weil kein Validator medium bewachte (Issue #906)."""
    with pytest.raises(ValidationError, match="agent_quote"):
        ReportClaimModel(
            claim_id="claim_04",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.medium,
            confidence_score=0.45,
            evidence=[_seed_evidence()],
        )


def test_medium_with_only_agent_quote_is_rejected():
    """ADR-0002 Stufe agent_grounded verlangt mind. 1 agent_quote UND mind. 1
    seed_corpus. medium mit ausschließlich agent_quote (ohne Korpus-Bezug) ist
    ebenfalls verboten — beide Quellengattungen müssen vorhanden sein."""
    with pytest.raises(ValidationError, match="seed_corpus"):
        ReportClaimModel(
            claim_id="claim_04",
            claim_text="Test claim text long enough",
            confidence_label=ConfidenceLabel.medium,
            confidence_score=0.45,
            evidence=[_agent_quote_evidence("Vertrieb")],
        )


def test_medium_with_agent_quote_and_seed_corpus_is_valid():
    """ADR-0002 Stufe agent_grounded: medium ist gültig, wenn mind. 1 agent_quote
    UND mind. 1 seed_corpus vorhanden sind. supports_claim ist für medium nicht
    Pflicht (nur für high/verified)."""
    claim = ReportClaimModel(
        claim_id="claim_04",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.medium,
        confidence_score=0.45,
        evidence=[_agent_quote_evidence("Vertrieb"), _seed_evidence()],
    )
    assert claim.confidence_label == ConfidenceLabel.medium


def test_medium_supports_claim_false_is_valid():
    """Sichert die Decision aus Issue #906 Punkt 1: ``supports_claim`` ist für
    ``medium`` NICHT Pflicht (im Gegensatz zu high/verified). Ein agent_grounded-
    Claim mit ausschließlich widersprechender/opposing Evidence bleibt als
    medium gültig — die Provenance-Stufe agent_grounded trägt das Label
    unabhängig von der Stützungsrichtung."""
    claim = ReportClaimModel(
        claim_id="claim_04",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.medium,
        confidence_score=0.45,
        evidence=[
            EvidenceItemModel(
                type=EvidenceType.agent_interview,
                source="agent-log",
                snippet="Aussage aus Vertrieb.",
                quote="Original-Zitat aus Vertrieb.",
                source_kind=EvidenceSourceKind.agent_quote,
                persona_stakeholder_group="Vertrieb",
                supports_claim=False,
            ),
            EvidenceItemModel(
                type=EvidenceType.graph_fact,
                source="seed-doc",
                snippet="Seed-Dokument-Auszug mit genug Text.",
                source_kind=EvidenceSourceKind.seed_corpus,
                supports_claim=False,
            ),
        ],
    )
    assert claim.confidence_label == ConfidenceLabel.medium


def test_low_claim_without_evidence_remains_legacy_readable():
    """P2.1: Alte Low-Orphans bleiben lesbar; Writer routet neue in data_gaps."""
    claim = ReportClaimModel(
        claim_id="claim_05",
        claim_text="Test claim text long enough",
        confidence_label=ConfidenceLabel.low,
        confidence_score=0.15,
        evidence=[],
    )

    assert claim.evidence == []


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


def test_outline_rejects_missing_required_sections() -> None:
    """Sub-Slice P1.1: ReportOutlineModel listet fehlende Default-Sections explizit."""
    from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

    first_default_title = DEFAULT_REPORT_SECTIONS[0][0]
    with pytest.raises(ValidationError) as exc_info:
        ReportOutlineModel(
            title="Test-Outline",
            summary="Nur ein Abschnitt, sonst nichts.",
            sections=[
                ReportOutlineSectionModel(title=first_default_title, description="Stub"),
            ],
        )
    msg = str(exc_info.value)
    for title, _ in DEFAULT_REPORT_SECTIONS[1:]:
        assert title in msg, f"Erwartet '{title}' in ValidationError-Message"


def test_validate_required_sections_case_insensitive() -> None:
    from app.services.report_agent.contract_validator import validate_required_sections

    assert validate_required_sections(
        ["  Cover  ", "EXECUTIVE summary"],
        ["Cover", "Executive Summary", "Datenlage"],
    ) == ["Datenlage"]
    assert validate_required_sections([], ["A", "B"]) == ["A", "B"]
    assert validate_required_sections(["A"], ["A"]) == []

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


# ---- EvidenceItemModel: quote + source_id_anchor (Task 12) ----

def test_evidence_with_quote_and_anchor_valid():
    """Neue Felder quote + source_id_anchor werden korrekt gesetzt."""
    item = EvidenceItemModel(
        type=EvidenceType.agent_action,
        source="agent_log",
        snippet="Persona kmu_ceo äußerte Bedenken.",
        quote="Persona kmu_ceo äußerte Bedenken.",
        source_id_anchor="web:https://example.com/x#:~:text=Anker-Tests",
    )
    assert item.quote == "Persona kmu_ceo äußerte Bedenken."
    assert item.source_id_anchor == "web:https://example.com/x#:~:text=Anker-Tests"


def test_evidence_without_provenance_still_valid():
    """Ohne quote und source_id_anchor bleibt EvidenceItemModel valide."""
    item = EvidenceItemModel(
        type=EvidenceType.graph_fact,
        source="graph",
        snippet="Kein Zitat verfügbar.",
    )
    assert item.quote is None
    assert item.source_id_anchor is None


def test_evidence_quote_too_long_rejected():
    """quote mit 501 Zeichen überschreitet max_length=500 → ValidationError."""
    with pytest.raises(ValidationError):
        EvidenceItemModel(
            type=EvidenceType.graph_fact,
            source="x",
            snippet="snippet",
            quote="x" * 501,
        )


def test_evidence_quote_empty_rejected():
    """quote='' verletzt min_length=1 → ValidationError."""
    with pytest.raises(ValidationError):
        EvidenceItemModel(
            type=EvidenceType.graph_fact,
            source="x",
            snippet="snippet",
            quote="",
        )


def test_evidence_source_id_anchor_too_long_rejected():
    """source_id_anchor mit 201 Zeichen überschreitet max_length=200 → ValidationError."""
    with pytest.raises(ValidationError):
        EvidenceItemModel(
            type=EvidenceType.graph_fact,
            source="x",
            snippet="snippet",
            source_id_anchor="x" * 201,
        )


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
            "schema_version": 3,
            "report_id": "report_abc",
            "simulation_id": "sim_abc",
            "evidence_index": {
                "ev_00000000000000000000000000000001": {
                    "evidence_id": "ev_00000000000000000000000000000001",
                    "producer_key": "agent:kmu_ceo:interview:1",
                    "type": "agent_interview",
                    "source": "agent_log",
                    "snippet": "Persona kmu_ceo äußerte Bedenken.",
                    "source_kind": "agent_quote",
                    "persona_stakeholder_group": "Geschaeftsfuehrung",
                },
                "ev_00000000000000000000000000000002": {
                    "evidence_id": "ev_00000000000000000000000000000002",
                    "producer_key": "agent:it_lead:interview:1",
                    "type": "agent_interview",
                    "source": "agent_log",
                    "snippet": "Persona it_lead bestaetigte das Problem.",
                    "source_kind": "agent_quote",
                    "persona_stakeholder_group": "IT-Abteilung",
                },
            },
            "global_evidence_refs": [],
            "sections": [{
                "section_index": 1,
                "section_title": "Erster Eindruck",
                "section_summary": "Zusammenfassung",
                "hypotheses": [{
                    "hypothesis_id": "hypothesis_01",
                    "hypothesis_text": "Indizien legen eine zweite Zielgruppe nahe.",
                    "rationale": "Es gibt Signale im Abschnitt, aber noch keine direkte Evidence.",
                    "suggested_evidence": ["weitere Persona-Quote"],
                }],
                "claims": [{
                    "claim_id": "claim_01",
                    "claim_text": "Die Personas reagieren skeptisch.",
                    "confidence_label": "high",
                    "confidence_score": 0.78,
                    # ADR-0002 Anker 4 (Sub-Slice M11.7b): high verlangt
                    # agent_quote-Evidence aus mindestens 2 Stakeholder-Gruppen.
                    "evidence": [
                        {
                            "evidence_id": "ev_00000000000000000000000000000001",
                            "match_score": 0.7,
                            "supports_claim": True,
                        },
                        {
                            "evidence_id": "ev_00000000000000000000000000000002",
                            "match_score": 0.72,
                            "supports_claim": True,
                        },
                    ],
                    "audit_trail": [],
                }],
            }],
        },
    }
    contract = ReportContractModel.model_validate(payload)
    assert contract.schema_version == 2
    assert contract.evidence is not None
    assert len(contract.evidence.sections) == 1
    assert contract.evidence.sections[0].hypotheses[0].hypothesis_id == "hypothesis_01"
