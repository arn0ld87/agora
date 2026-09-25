"""Claim-Typisierung: empirical / analytical / recommendation / structural (#1400).

Slice 2 von #1301. Empfehlungen, Analysen und Struktursätze haben naturgemäß
keine direkte Evidence und fielen dadurch auf ``speculative``. Der Typ-Boden
hebt sie auf ``low`` — nie darüber hinaus (ADR-0002 Anker 4/5).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ClaimType,
    IndexedReportClaimModel,
    ReportSectionHypothesisModel,
)
from app.contracts.report_v3 import Claim as ReportV3Claim
from app.services.claim_type_classifier import classify_claim_type
from app.services.confidence_calculator import (
    NON_EMPIRICAL_CONFIDENCE_FLOOR,
    apply_claim_type_floor,
    compute_confidence,
)
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import (
    _record_text_confidence_downgrade,
    text_confidence_label_of,
)

# --- Snapshot: bekannte Sätze aus Referenzläufen und ihr Typ ----------------

#: Tatsachen dürfen nicht als Empfehlung/Analyse durchrutschen (sie entgingen
#: sonst der vollen Abwertung) — und Empfehlungen nicht als Tatsache gelten.
KNOWN_SENTENCES = [
    # empirical — Seed- und Simulationsfakten
    ("22 festangestellte Dozenten stehen auf der Personalliste des Trägers.", "empirical"),
    ("Der Betriebsrat lehnt die Auswertungsfunktion ab.", "empirical"),
    ("Der Träger muss den Unterrichtsumfang formal unverändert lassen.", "empirical"),
    ("Die Geschäftsführung soll bis Februar entscheiden.", "empirical"),
    ("Die Pflegekräfte befürchten wahrscheinlich Mehrarbeit.", "empirical"),
    ("70 % der Lehrkräfte sollten geschult werden.", "empirical"),
    # analytical — Kausal-/Schlussaussagen
    (
        "Die Honorarkräfte lehnen stärker ab, weil sie keinen Anteil an der "
        "Entlastung haben.",
        "analytical",
    ),
    ("Daraus ergibt sich ein Zielkonflikt zwischen Tempo und Akzeptanz.", "analytical"),
    ("Der gestaffelte Start führt zu geringerer Belastung der Notaufnahme.", "analytical"),
    # recommendation — Handlungsempfehlungen
    ("Der Träger sollte zunächst eine einzelne Station pilotieren.", "recommendation"),
    ("Wir empfehlen eine schriftliche Betriebsvereinbarung vor dem Start.", "recommendation"),
    ("Die Datenhaltung ist vor dem Rollout verbindlich zu regeln.", "recommendation"),
    ("Ein gestaffelter Start wäre ratsam.", "recommendation"),
    # structural — Meta- und Gliederungssätze, die den Vorfilter passieren
    ("Zusammenfassend zeigen sich drei Spannungen zwischen den Akteuren.", "structural"),
    ("Drei Konfliktlinien prägen die Ausgangslage des Projekts.", "structural"),
    ("Dieser Bericht behandelt die Einführung aus Sicht aller Stakeholder.", "structural"),
]


@pytest.mark.parametrize(("sentence", "expected"), KNOWN_SENTENCES)
def test_bekannte_saetze_werden_korrekt_typisiert(sentence, expected):
    assert classify_claim_type(sentence).value == expected


def test_leerer_text_ist_empirisch():
    assert classify_claim_type("") is ClaimType.empirical


# --- Claim-Typen × Match-Scores → Confidence-Bänder -------------------------


def _supporting(match_score: float, n: int = 1) -> List[Dict[str, Any]]:
    return [
        {
            "type": "graph_fact",
            "source": f"quelle_{i}",
            "snippet": "x",
            "match_score": match_score,
            "supports_claim": True,
            "entailment": "SUPPORTED",
        }
        for i in range(n)
    ]


_ORDER = ["speculative", "low", "medium", "high", "verified"]


@pytest.mark.parametrize("claim_type", [t.value for t in ClaimType] + [None])
@pytest.mark.parametrize(
    "evidence",
    [
        [],
        _supporting(0.40),
        _supporting(0.60),
        _supporting(0.70, n=2),
        _supporting(0.92, n=3),
    ],
    ids=["ohne", "schwach", "mittel", "zwei_quellen", "stark"],
)
def test_typ_boden_hebt_nur_bis_low_und_senkt_nie(claim_type, evidence):
    base_score, base_label = compute_confidence(evidence)
    score, label = apply_claim_type_floor(claim_type, base_score, base_label)

    # Nie abgesenkt.
    assert score >= base_score
    assert _ORDER.index(label) >= _ORDER.index(base_label)
    if claim_type in (None, "empirical"):
        assert (score, label) == (base_score, base_label)
    else:
        assert _ORDER.index(label) >= _ORDER.index("low")
    # Nie über das hinaus, was die Evidence ohnehin trägt, außer bis low.
    if (score, label) != (base_score, base_label):
        assert (score, label) == (NON_EMPIRICAL_CONFIDENCE_FLOOR, "low")


@pytest.mark.parametrize("claim_type", ["analytical", "recommendation", "structural"])
def test_typ_boden_erreicht_nie_medium_oder_high(claim_type):
    """ADR-0002 Anker 4/5: ``high`` nur über Cross-Stakeholder-Evidence."""
    score, label = apply_claim_type_floor(claim_type, 0.0, "speculative")
    assert label == "low"
    assert score < 0.65


# --- Routing ohne stützende Evidence ---------------------------------------


def _claim(idx: int, text: str) -> Dict[str, Any]:
    return {
        "claim_id": f"claim_{idx:02d}",
        "claim_text": text,
        "confidence_label": "low",
        "confidence_score": NON_EMPIRICAL_CONFIDENCE_FLOOR,
        "evidence": [],
        "audit_trail": [],
        "claim_type": classify_claim_type(text).value,
    }


def test_unbelegte_empfehlung_wird_hypothese_ohne_datenluecke():
    agent = ReportAgent.__new__(ReportAgent)
    claims, hypotheses, data_gaps, decisions = agent._finalize_section_claims(
        [
            _claim(1, "Der Träger sollte zunächst eine einzelne Station pilotieren."),
            _claim(2, "Der Betriebsrat lehnt die Auswertungsfunktion ab."),
        ]
    )
    assert claims == [], "ADR-0002: kein Claim ohne stützende Quelle"
    assert [h.get("claim_type") for h in hypotheses] == ["recommendation", "empirical"]
    assert "Keine Tatsachenbehauptung" in hypotheses[0]["rationale"]
    # Nur die Tatsachenbehauptung ist eine Informationslücke.
    assert len(data_gaps) == 1
    assert data_gaps[0]["hypothesis_id"] == hypotheses[1]["hypothesis_id"]
    assert decisions[0]["detail"].startswith("[non_factual:recommendation]")
    for hypothesis in hypotheses:
        ReportSectionHypothesisModel.model_validate(hypothesis)


def test_unbelegte_analyse_laeuft_wie_eine_tatsachenbehauptung():
    agent = ReportAgent.__new__(ReportAgent)
    _claims, hypotheses, data_gaps, _decisions = agent._finalize_section_claims(
        [_claim(1, "Die Honorarkräfte lehnen ab, weil sie keinen Anteil an der Entlastung haben.")]
    )
    assert hypotheses[0]["claim_type"] == "analytical"
    assert len(data_gaps) == 1


# --- Wortlaut-Hinweis nur für Tatsachen ------------------------------------


@pytest.mark.parametrize(
    ("claim_type", "expected"),
    [(None, "high"), ("empirical", "high"), ("recommendation", None), ("analytical", None)],
)
def test_text_confidence_hinweis_nur_fuer_empirische_claims(claim_type, expected):
    claim: Dict[str, Any] = {"audit_trail": []}
    if claim_type:
        claim["claim_type"] = claim_type
    _record_text_confidence_downgrade(claim, from_label="high", to_label="low")
    assert text_confidence_label_of(claim) == expected


# --- Contract ----------------------------------------------------------------


def _indexed(**extra: Any) -> Dict[str, Any]:
    return {
        "claim_id": "claim_01",
        "claim_text": "Der Träger sollte zunächst pilotieren.",
        "confidence_label": "low",
        "confidence_score": 0.45,
        **extra,
    }


def test_contract_akzeptiert_claim_type_und_altbestand():
    assert IndexedReportClaimModel.model_validate(_indexed()).claim_type is None
    model = IndexedReportClaimModel.model_validate(_indexed(claim_type="recommendation"))
    assert model.claim_type is ClaimType.recommendation


def test_contract_lehnt_unbekannten_claim_type_ab():
    with pytest.raises(ValidationError):
        IndexedReportClaimModel.model_validate(_indexed(claim_type="opinion"))


def test_report_v3_claim_traegt_claim_type():
    claim = ReportV3Claim(
        id="C1_01",
        statement="Der Träger sollte zunächst pilotieren.",
        evidence_refs=["ev_1"],
        confidence="low",
        aggregation_basis="seed",
        claim_type="recommendation",
    )
    assert claim.claim_type == "recommendation"
