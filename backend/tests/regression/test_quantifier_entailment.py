"""Quantoren brauchen einen aggregierten Beleg (Issue #1345).

Referenz: AURORA-Lauf ``report_3c594fcc7613`` / ``sim_4245ff3d7b23``. Der Claim
„Nahezu alle befragten Akteure bevorzugen einen kontrollierten Pilotbetrieb"
war an einen einzigen Dokumentsatz gebunden, der die Empfehlung belegt — aber
nicht, dass nahezu alle sie teilen.

Gegenprobe (#1317): Claims ohne Quantor bleiben unverändert gedeckt.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import EntailmentVerdict, classify_evidence
from app.services.quantifier_claims import (
    CHECK_CORE_SUPPORTED,
    CHECK_NEEDS_AGGREGATION,
    QuantifierStrength,
    detect_quantifier,
    evidence_backs_quantifier,
)

FALKENBRUECK_CLAIM = (
    "Nahezu alle befragten Akteure bevorzugen einen kontrollierten Pilotbetrieb."
)
FALKENBRUECK_EVIDENCE: Dict[str, Any] = {
    "evidence_id": "ev_seed_falkenbrueck",
    "snippet": "Vorgeschlagen wird: zunächst ausschließlich Falkenbrück-Mitte.",
    "type": "seed_document",
    "source_kind": "seed_corpus",
}


def _always_supported(_claim: str, _evidence: str) -> str:
    return "SUPPORTED"


def _embed(_text: str) -> List[float]:
    # Identische Vektoren: Cosine 1.0, jeder Kandidat erreicht die Stufe 2.
    return [1.0, 0.0, 0.0]


def _interview(
    idx: int,
    family: Optional[str],
    text: str = "Ein kontrollierter Pilotbetrieb auf einer Station ist uns lieber.",
) -> Dict[str, Any]:
    return {
        "evidence_id": f"ev_quote_{idx}",
        "snippet": text,
        "quote": text,
        "type": "agent_interview",
        "source_kind": "agent_quote",
        "persona_stakeholder_group": f"Persona {idx}",
        "persona_role_family": family,
    }


# --- Erkennung -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Alle Akteure lehnen den Vollstart ab.", QuantifierStrength.UNIVERSAL),
        ("Sämtliche Stationen melden Bedarf.", QuantifierStrength.UNIVERSAL),
        (FALKENBRUECK_CLAIM, QuantifierStrength.NEAR_UNIVERSAL),
        ("Fast alle Beteiligten sehen Risiken.", QuantifierStrength.NEAR_UNIVERSAL),
        ("Die Akteure unterstützen den Pilot mehrheitlich.", QuantifierStrength.MAJORITY),
        ("Die meisten Pflegekräfte fürchten Mehrarbeit.", QuantifierStrength.MAJORITY),
        ("Niemand befürwortet den Vollstart.", QuantifierStrength.NONE),
        ("Keiner der Befragten will den Vollstart.", QuantifierStrength.NONE),
        ("Kaum jemand vertraut dem Zeitplan.", QuantifierStrength.NEAR_NONE),
        ("Der Betriebsrat lehnt den Vollstart ab.", None),
        ("Trotz aller Bedenken stimmt der Betriebsrat zu.", None),
        ("Das ist auf alle Fälle zu klären.", None),
    ],
)
def test_quantoren_werden_nach_staerke_erkannt(text, expected):
    assert detect_quantifier(text) is expected


def test_eine_quelle_traegt_den_quantor_nur_mit_gleich_starker_mengenaussage():
    near = QuantifierStrength.NEAR_UNIVERSAL
    assert evidence_backs_quantifier(near, "Alle Stationen sind angeschlossen.")
    assert evidence_backs_quantifier(near, "Nahezu alle Stationen sind angeschlossen.")
    assert not evidence_backs_quantifier(near, "Die meisten Stationen sind angeschlossen.")
    assert not evidence_backs_quantifier(near, "Niemand ist angeschlossen.")
    assert not evidence_backs_quantifier(near, "Die Station Mitte ist angeschlossen.")


# --- Der Falkenbrück-Fall --------------------------------------------------


def test_falkenbrueck_einzelner_dokumentsatz_traegt_nahezu_alle_nicht():
    """Referenz existiert, ist relevant — beweist den Quantor aber nicht."""
    result = classify_evidence(
        FALKENBRUECK_CLAIM,
        FALKENBRUECK_EVIDENCE,
        judge=_always_supported,
        retrieval_score=0.72,
    )
    assert result.verdict is EntailmentVerdict.RELATED_ONLY, result.reason
    assert CHECK_NEEDS_AGGREGATION in result.checks
    assert "nahezu alle" in result.reason


def test_falkenbrueck_ueber_den_binder_bleibt_ungestuetzt():
    bound = bind_evidence_to_claim(
        FALKENBRUECK_CLAIM,
        [FALKENBRUECK_EVIDENCE],
        _embed,
        threshold=0.5,
        judge=_always_supported,
    )
    assert len(bound) == 1
    assert bound[0]["supports_claim"] is False
    assert bound[0]["entailment"] == EntailmentVerdict.RELATED_ONLY.value


def test_ein_einzelnes_interview_traegt_keine_mehrheit():
    """Der Judge sieht eine Stimme und kann über Mengen nicht urteilen."""
    claim = "Die meisten Akteure bevorzugen einen kontrollierten Pilotbetrieb."
    bound = bind_evidence_to_claim(
        claim, [_interview(1, "Pflege")], _embed, threshold=0.5, judge=_always_supported
    )
    assert bound[0]["supports_claim"] is False
    assert "belegt: 1" in bound[0]["entailment_reason"]


# --- Aggregation über Stakeholder-Gruppen ----------------------------------


def test_drei_gruppen_ohne_gegenstimme_tragen_nahezu_alle():
    candidates = [
        _interview(1, "Pflege"),
        _interview(2, "Ärztlicher Dienst"),
        _interview(3, "IT-Betrieb"),
    ]
    bound = bind_evidence_to_claim(
        FALKENBRUECK_CLAIM, candidates, _embed, threshold=0.5, judge=_always_supported
    )
    assert all(b["supports_claim"] is True for b in bound), [b["entailment_reason"] for b in bound]
    assert all(b["entailment"] == "SUPPORTED" for b in bound)
    assert "3 übereinstimmende Stakeholder-Gruppen" in bound[0]["entailment_reason"]


def test_dieselbe_rollenfamilie_zaehlt_nur_einmal():
    candidates = [_interview(i, "Pflege") for i in range(1, 4)]
    bound = bind_evidence_to_claim(
        FALKENBRUECK_CLAIM, candidates, _embed, threshold=0.5, judge=_always_supported
    )
    assert not any(b["supports_claim"] for b in bound)
    assert "belegt: 1" in bound[0]["entailment_reason"]


def test_eine_gegenstimme_bricht_alle_aber_nicht_die_mehrheit():
    def judge(_claim: str, evidence: str) -> str:
        return "CONTRADICTED" if "Vollstart" in evidence else "SUPPORTED"

    candidates = [
        _interview(1, "Pflege"),
        _interview(2, "Ärztlicher Dienst"),
        _interview(3, "IT-Betrieb"),
        _interview(4, "Geschäftsführung", "Wir wollen den Vollstart für alle Kliniken."),
    ]
    universal = bind_evidence_to_claim(
        "Alle Akteure bevorzugen einen kontrollierten Pilotbetrieb.",
        candidates,
        _embed,
        threshold=0.5,
        judge=judge,
    )
    assert not any(b["supports_claim"] for b in universal)
    assert "Gegenstimmen: 1" in universal[0]["entailment_reason"]

    majority = bind_evidence_to_claim(
        "Die meisten Akteure bevorzugen einen kontrollierten Pilotbetrieb.",
        candidates,
        _embed,
        threshold=0.5,
        judge=judge,
    )
    supporting = [b for b in majority if b["supports_claim"]]
    assert {b["evidence_id"] for b in supporting} == {"ev_quote_1", "ev_quote_2", "ev_quote_3"}


def test_dokumentfakten_zaehlen_nicht_als_stimmen():
    """Nur Interview-Stimmen bilden die Grundgesamtheit „befragte Akteure"."""
    seeds = [
        {**FALKENBRUECK_EVIDENCE, "evidence_id": f"ev_seed_{i}"} for i in range(3)
    ]
    bound = bind_evidence_to_claim(
        FALKENBRUECK_CLAIM, seeds, _embed, threshold=0.5, judge=_always_supported
    )
    assert not any(b["supports_claim"] for b in bound)


def test_nicht_zuordenbare_stimmen_werden_nicht_gezaehlt():
    candidates = [_interview(i, None) for i in range(1, 4)]
    for item in candidates:
        item["persona_stakeholder_group"] = None
    bound = bind_evidence_to_claim(
        FALKENBRUECK_CLAIM, candidates, _embed, threshold=0.5, judge=_always_supported
    )
    assert not any(b["supports_claim"] for b in bound)


# --- Prozentangaben --------------------------------------------------------


def test_anteil_unter_der_quantorstaerke_widerspricht():
    evidence = {
        "snippet": "62 % der Akteure bevorzugen einen kontrollierten Pilotbetrieb.",
        "source_kind": "seed_corpus",
    }
    result = classify_evidence(FALKENBRUECK_CLAIM, evidence, judge=_always_supported)
    assert result.verdict is EntailmentVerdict.CONTRADICTED
    assert "quantifier_vs_share" in result.checks


def test_ausreichender_anteil_deckt_den_quantor():
    evidence = {
        "snippet": (
            "92 % der befragten Akteure bevorzugen einen kontrollierten Pilotbetrieb."
        ),
        "source_kind": "seed_corpus",
    }
    result = classify_evidence(FALKENBRUECK_CLAIM, evidence, judge=_always_supported)
    assert result.verdict is EntailmentVerdict.SUPPORTED, result.reason
    assert "quantifier_share_backed" in result.checks


def test_quelle_mit_eigenem_quantor_traegt_den_claim():
    evidence = {
        "snippet": "Alle befragten Akteure bevorzugen einen kontrollierten Pilotbetrieb.",
        "source_kind": "seed_corpus",
    }
    result = classify_evidence(FALKENBRUECK_CLAIM, evidence)
    assert result.verdict is EntailmentVerdict.SUPPORTED, result.reason
    assert "quantifier_backed_by_source" in result.checks


def test_sechs_von_acht_ohne_zahl_in_der_quelle_ist_nicht_belegt():
    result = classify_evidence(
        "Sechs von acht Akteuren bevorzugen einen kontrollierten Pilotbetrieb.",
        _interview(1, "Pflege"),
        judge=_always_supported,
        retrieval_score=0.72,
    )
    assert result.verdict is not EntailmentVerdict.SUPPORTED


# --- Gegenprobe #1317: belegte Einzelfakten bleiben belegt -----------------


def test_gegenprobe_claim_ohne_quantor_bleibt_durch_eine_quelle_gedeckt():
    claim = "Der Betriebsrat bevorzugt einen kontrollierten Pilotbetrieb."
    evidence = {
        "snippet": "Der Betriebsrat bevorzugt einen kontrollierten Pilotbetrieb.",
        "source_kind": "seed_corpus",
    }
    result = classify_evidence(claim, evidence)
    assert result.verdict is EntailmentVerdict.SUPPORTED
    assert CHECK_CORE_SUPPORTED not in result.checks


def test_gegenprobe_interview_ohne_quantor_bindet_wie_bisher():
    claim = "Die Pflege bevorzugt einen kontrollierten Pilotbetrieb."
    bound = bind_evidence_to_claim(
        claim, [_interview(1, "Pflege")], _embed, threshold=0.5, judge=_always_supported
    )
    assert bound[0]["supports_claim"] is True
    assert bound[0]["entailment_reason"] == "strukturierter Judge"
