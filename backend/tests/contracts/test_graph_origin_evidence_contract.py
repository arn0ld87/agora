"""Manuelle Herkunft im Evidence-Vertrag (ADR-0022, Issue #1808).

Evidence aus von Hand angelegten oder bearbeiteten Graph-Elementen trägt das
optionale Feld ``graph_origin``. ``source_kind`` bleibt ``graph_relation``;
``EvidenceSourceKind`` (ADR-0002 Anker 3) bekommt keinen neuen Wert. Solche
Evidence zählt für keine Confidence-Stufe: ein Claim darf ``high`` behalten,
wenn er die bestehenden Regeln auch ohne sie erfüllt, aber nie *durch* sie.
"""
from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.contracts import (
    ConfidenceLabel,
    EvidenceItemModel,
    EvidenceMapModel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)
from app.contracts.report_contract import EntailmentVerdict, EvidenceRecordModel

EV_MANUAL = "ev_000000000000000000000000000000aa"
EV_QUOTE_A = "ev_000000000000000000000000000000bb"
EV_QUOTE_B = "ev_000000000000000000000000000000cc"


def _agent_quote(group: str, *, score: float = 0.7) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.agent_interview,
        source="agent-log",
        snippet=f"Persona aus {group}: Beispiel-Aussage.",
        quote=f"Original-Zitat aus {group}.",
        match_score=score,
        entailment=EntailmentVerdict.SUPPORTED,
        supports_claim=True,
        source_kind=EvidenceSourceKind.agent_quote,
        persona_stakeholder_group=group,
    )


def _graph_fact(
    *, graph_origin: str | None, score: float = 0.7, supports: bool = True
) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.graph_fact,
        source="report_tool",
        snippet="Der Verband unterstützt die Reform.",
        match_score=score,
        entailment=EntailmentVerdict.SUPPORTED if supports else None,
        supports_claim=supports,
        source_kind=EvidenceSourceKind.graph_relation,
        graph_origin=graph_origin,
    )


def _claim(label: ConfidenceLabel, evidence: list[EvidenceItemModel], score: float = 0.86):
    return ReportClaimModel(
        claim_id="claim_01",
        claim_text="Die Reform wird von mehreren Gruppen getragen.",
        confidence_label=label,
        confidence_score=score,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Feld und Altbestand
# ---------------------------------------------------------------------------


def test_graph_origin_defaults_to_none_on_item_and_record() -> None:
    """Altbestand ohne das Feld validiert unverändert."""
    item = EvidenceItemModel(type=EvidenceType.graph_fact, source="x", snippet="snippet")
    assert item.graph_origin is None

    record = EvidenceRecordModel.model_validate({
        "evidence_id": EV_MANUAL,
        "producer_key": "graph-fact:abc",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Ein extrahierter Fakt aus dem Bestand.",
        "source_kind": "graph_relation",
    })
    assert record.graph_origin is None
    # Kein Pflichtfeld im Schema: ein Leser ohne Kenntnis des Felds bleibt gültig.
    assert "graph_origin" not in EvidenceRecordModel.model_json_schema().get("required", [])
    assert "graph_origin" not in EvidenceItemModel.model_json_schema().get("required", [])


@pytest.mark.parametrize("origin", ["manual", "edited"])
def test_graph_origin_accepts_manual_and_edited(origin: str) -> None:
    item = _graph_fact(graph_origin=origin)
    assert item.graph_origin == origin
    assert item.source_kind == EvidenceSourceKind.graph_relation


def test_graph_origin_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError, match="graph_origin"):
        _graph_fact(graph_origin="extracted")


def test_source_kind_enum_has_no_manual_value() -> None:
    """ADR-0002 Anker 3 bleibt geschlossen — die Herkunft steht im eigenen Feld."""
    assert {kind.value for kind in EvidenceSourceKind} == {
        "seed_corpus",
        "agent_quote",
        "agent_action",
        "graph_relation",
        "web_source",
        "inferred",
    }


@pytest.mark.parametrize("model", [EvidenceItemModel, EvidenceRecordModel])
def test_graph_origin_never_appears_as_document_fact(model) -> None:
    """Geänderter oder von Hand eingegebener Text ist nie ``seed_corpus``."""
    payload = {
        "type": "seed_document",
        "source": "report_tool",
        "snippet": "Von Hand geänderter Satz.",
        "source_kind": "seed_corpus",
        "source_id_anchor": "seed_doc:doc_a1#chunk:3",
        "graph_origin": "edited",
    }
    if model is EvidenceRecordModel:
        payload |= {"evidence_id": EV_MANUAL, "producer_key": "seed-doc:doc_a1:3"}
    with pytest.raises(ValidationError, match="graph_origin"):
        model.model_validate(payload)


def test_graph_origin_rejects_seed_doc_anchor_even_on_graph_relation() -> None:
    with pytest.raises(ValidationError, match="seed_doc"):
        EvidenceItemModel(
            type=EvidenceType.graph_fact,
            source="report_tool",
            snippet="Von Hand geänderter Satz.",
            source_kind=EvidenceSourceKind.graph_relation,
            source_id_anchor="seed_doc:doc_a1#chunk:3",
            graph_origin="edited",
        )


# ---------------------------------------------------------------------------
# Claim-Modell: zusätzlicher Validator neben den Ankern 4 und 5
# ---------------------------------------------------------------------------


def test_manual_fact_alone_supports_no_high_confidence() -> None:
    """Hier greift bereits ADR-0002 Anker 4, nicht die neue Herkunftsregel.

    Anker 4 verlangt zwei stuetzende Rollenfamilien aus ``agent_quote``; eine
    Graph-Relation liefert sie nicht. Die Isolation der neuen Regel — ein Label,
    das nur *durch* Handarbeit erreichbar waere — prueft
    ``test_verified_resting_on_manual_strong_match_is_rejected``.
    """
    with pytest.raises(
        ValidationError, match="mindestens 2 unterschiedlichen Stakeholder-Rollenfamilien"
    ):
        _claim(ConfidenceLabel.high, [_graph_fact(graph_origin="manual", score=0.95)])


@pytest.mark.parametrize("origin", ["manual", "edited"])
def test_claim_with_only_hand_made_evidence_is_never_medium(origin: str) -> None:
    """Auch hier greift die medium-Regel aus ADR-0002 zuerst."""
    with pytest.raises(ValidationError, match="agent_quote=False, seed_corpus=False"):
        _claim(
            ConfidenceLabel.medium,
            [_graph_fact(graph_origin=origin, score=0.95)],
            score=0.7,
        )


def test_claim_with_only_hand_made_evidence_may_stay_low() -> None:
    """Sichtbar, aber ohne Gewicht: der Claim bleibt lesbar auf ``low``."""
    claim = _claim(ConfidenceLabel.low, [_graph_fact(graph_origin="manual")], score=0.5)
    assert claim.evidence[0].graph_origin == "manual"


def test_claim_stays_high_when_met_without_manual_evidence() -> None:
    claim = _claim(
        ConfidenceLabel.high,
        [_agent_quote("Buerger"), _agent_quote("Verwaltung"), _graph_fact(graph_origin="manual")],
    )
    assert claim.confidence_label == ConfidenceLabel.high


def test_verified_resting_on_manual_strong_match_is_rejected() -> None:
    """Zwei Gruppen tragen ``high``; die ``verified``-Schwelle (match_score
    >= 0.85 mit SUPPORTED) liefert aber nur die Handeingabe."""
    evidence = [
        _agent_quote("Buerger", score=0.7),
        _agent_quote("Verwaltung", score=0.7),
        _graph_fact(graph_origin="edited", score=0.95),
    ]
    with pytest.raises(ValidationError, match="ADR-0022"):
        _claim(ConfidenceLabel.verified, evidence, score=0.93)

    # Derselbe Claim mit extrahiertem Fakt (Bestand) validiert wie bisher.
    extracted = [*evidence[:2], _graph_fact(graph_origin=None, score=0.95)]
    assert _claim(ConfidenceLabel.verified, extracted, score=0.93).confidence_label == (
        ConfidenceLabel.verified
    )


def test_verified_stays_when_strong_match_is_not_hand_made() -> None:
    claim = _claim(
        ConfidenceLabel.verified,
        [
            _agent_quote("Buerger", score=0.9),
            _agent_quote("Verwaltung", score=0.7),
            _graph_fact(graph_origin="manual", score=0.95),
        ],
        score=0.93,
    )
    assert claim.confidence_label == ConfidenceLabel.verified


# ---------------------------------------------------------------------------
# EvidenceMap v3 (persistiertes Artefakt hinter GET /api/report/<id>/evidence)
# ---------------------------------------------------------------------------


def _quote_record(evidence_id: str, group: str) -> dict:
    return {
        "evidence_id": evidence_id,
        "producer_key": f"interview:{group}",
        "type": "agent_interview",
        "source": "agent-log",
        "snippet": f"Persona aus {group}: Beispiel-Aussage.",
        "quote": f"Original-Zitat aus {group}.",
        "source_kind": "agent_quote",
        "persona_stakeholder_group": group,
    }


def _map_payload(label: str, *, graph_origin: str | None, quote_score: float) -> dict:
    manual_record = {
        "evidence_id": EV_MANUAL,
        "producer_key": "graph-fact:abc",
        "type": "graph_fact",
        "source": "report_tool",
        "snippet": "Der Verband unterstützt die Reform.",
        "source_kind": "graph_relation",
    }
    if graph_origin is not None:
        manual_record["graph_origin"] = graph_origin

    def binding(evidence_id: str, score: float) -> dict:
        return {
            "evidence_id": evidence_id,
            "match_score": score,
            "entailment": "SUPPORTED",
            "supports_claim": True,
        }

    return {
        "schema_version": 3,
        "report_id": "report-1808",
        "simulation_id": "run-1808",
        "evidence_index": {
            EV_MANUAL: manual_record,
            EV_QUOTE_A: _quote_record(EV_QUOTE_A, "Buerger"),
            EV_QUOTE_B: _quote_record(EV_QUOTE_B, "Verwaltung"),
        },
        "global_evidence_refs": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Wirkungsanalyse",
                "section_summary": "Zusammenfassung der beobachteten Wirkung.",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Reform wird von mehreren Gruppen getragen.",
                        "confidence_label": label,
                        "confidence_score": 0.93 if label == "verified" else 0.86,
                        "evidence": [
                            binding(EV_MANUAL, 0.95),
                            binding(EV_QUOTE_A, quote_score),
                            binding(EV_QUOTE_B, quote_score),
                        ],
                    }
                ],
            }
        ],
    }


def test_evidence_map_roundtrips_graph_origin() -> None:
    payload = _map_payload("high", graph_origin="manual", quote_score=0.7)
    dumped = EvidenceMapModel.model_validate(payload).model_dump(mode="json")
    assert dumped["evidence_index"][EV_MANUAL]["graph_origin"] == "manual"
    assert dumped["evidence_index"][EV_MANUAL]["source_kind"] == "graph_relation"
    assert dumped["evidence_index"][EV_QUOTE_A]["graph_origin"] is None
    assert dumped["sections"][0]["claims"][0]["confidence_label"] == "high"


def test_evidence_map_without_graph_origin_validates_unchanged() -> None:
    payload = _map_payload("verified", graph_origin=None, quote_score=0.7)
    assert all("graph_origin" not in record for record in payload["evidence_index"].values())
    EvidenceMapModel.model_validate(payload)


def test_evidence_map_rejects_verified_resting_on_manual_strong_match() -> None:
    payload = _map_payload("verified", graph_origin="manual", quote_score=0.7)
    with pytest.raises(ValidationError, match="ADR-0022"):
        EvidenceMapModel.model_validate(payload)

    carried = deepcopy(payload)
    for item in carried["sections"][0]["claims"][0]["evidence"][1:]:
        item["match_score"] = 0.9
    EvidenceMapModel.model_validate(carried)
