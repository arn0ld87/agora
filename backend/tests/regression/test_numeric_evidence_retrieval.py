"""Golden Set: numerische Evidence, die im Referenzlauf nicht gefunden wurde.

Aus ``report_cc2ef45da5e9``. Alle Werte unten standen im kanonischen
Evidence-Index, und trotzdem lautete das Urteil "numerischer Claim ohne
passenden Zahlenbeleg". Die Ursache lag nicht im Entailment, sondern eine
Stufe davor: das Retrieval ist rein embedding-basiert und verwirft alles
unter Cosine 0.65. Eine Quelle, die exakt dieselbe Zahl in anderer
Formulierung nennt, erreicht diese Schwelle regelmäßig nicht — sie kam nie
zur inhaltlichen Prüfung.

Die Antwort darauf ist ein deterministischer Vorabruf: wer dieselbe Zahl in
derselben Einheit nennt, ist Kandidat, unabhängig vom Embedding. Ob er den
Claim *belegt*, entscheidet weiterhin allein das Entailment.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.contracts.report_contract import ClaimEvidenceBindingModel
from app.services.evidence_binder import bind_evidence_to_claim
from app.services.evidence_entailment import EntailmentVerdict, classify_evidence
from app.services.numeric_evidence import (
    numeric_candidates,
    shares_numeric_fact,
)


def _item(text: str, evidence_id: str) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "type": "seed_document", "snippet": text}


#: Die Formulierungspaare aus dem Referenzlauf: links wie der Bericht es
#: schreibt, rechts wie die Quelle es schreibt.
GOLDEN_PAIRS: List[tuple[str, str]] = [
    (
        "Vor Produktivstart müssen mindestens 80 Prozent geschult sein.",
        "Der Projektplan fordert vor Produktivstart mindestens 80 Prozent der "
        "unmittelbar betroffenen Beschäftigten als geschult.",
    ),
    (
        "Es traten 38 abweichende Dringlichkeitsfälle auf.",
        "In der Testphase wichen 38 Empfehlungen in der Dringlichkeitsstufe ab.",
    ),
    (
        "Der manuelle Fallback ist auf maximal 15 Minuten begrenzt.",
        "Für den manuellen Fallback sind höchstens 15 Minuten vorgesehen.",
    ),
    (
        "In der Pflege liegt die Quote bei 54 Prozent.",
        "Die Pflege erreichte 54 Prozent.",
    ),
    (
        "Die Sprachunterstützung im Norden erreicht 14 Prozent.",
        "Im Bereich Nord liegt die Sprachunterstützung bei 14 Prozent.",
    ),
    (
        "61 Prozent der Fälle wurden als kritisch eingestuft.",
        "Von 412 geprüften Fällen galten 61 Prozent als kritisch.",
    ),
    (
        "24 Prozent äußerten sich positiv.",
        "Positiv äußerten sich 24 Prozent der Befragten.",
    ),
    (
        "15 Prozent blieben unentschieden.",
        "Unentschieden blieben 15 Prozent der Befragten.",
    ),
]


@pytest.mark.parametrize(
    "claim, evidence", GOLDEN_PAIRS, ids=[c[:28] for c, _ in GOLDEN_PAIRS]
)
def test_the_numeric_prefilter_finds_the_matching_source(claim: str, evidence: str):
    """Stufe 1: der deterministische Vorabruf findet den Beleg."""
    pool = [
        _item("Die Kantine bleibt an Feiertagen geschlossen.", "ev_noise"),
        _item(evidence, "ev_hit"),
    ]

    found = numeric_candidates(claim, pool)

    assert [item["evidence_id"] for item in found] == ["ev_hit"]


@pytest.mark.parametrize(
    "claim, evidence", GOLDEN_PAIRS, ids=[c[:28] for c, _ in GOLDEN_PAIRS]
)
def test_a_matching_source_is_never_judged_as_unbacked(claim: str, evidence: str):
    """Stufe 2: das Urteil darf nicht "kein Zahlenbeleg" lauten.

    Ob die Quelle den Claim vollständig trägt, ist eine andere Frage — sie
    kann durchaus als ``INSUFFICIENT`` enden, wenn der Claim mehr behauptet.
    Was sie nicht mehr darf, ist die Zahl selbst für unbelegt zu erklären.
    """
    result = classify_evidence(claim, _item(evidence, "ev_hit"))

    assert "no_matching_number" not in result.checks


def test_a_different_population_is_not_matched():
    """Gegenprobe: gleiche Zahl, fremde Grundgesamtheit."""
    result = classify_evidence(
        "In der Pflege liegt die Quote bei 54 Prozent.",
        _item("Die Verwaltung erreichte 54 Prozent.", "ev_admin"),
    )

    assert result.verdict is not EntailmentVerdict.SUPPORTED


def test_a_source_without_the_number_is_no_numeric_candidate():
    assert not shares_numeric_fact(
        "In der Pflege liegt die Quote bei 54 Prozent.",
        "Die Einführung erfolgt in drei Wellen.",
    )


def test_a_claim_without_numbers_yields_no_numeric_candidates():
    pool = [_item("Die Pflege erreichte 54 Prozent.", "ev_care")]

    assert numeric_candidates("Die Belegschaft ist skeptisch.", pool) == []


# --- Verdrahtung im Binder --------------------------------------------------


def _weak_embedder(text: str) -> List[float]:
    """Ein Embedder, der nichts zusammenbringt.

    Er bildet den Referenzfall ab: das Retrieval findet die Quelle nicht,
    obwohl sie da ist. Ohne den deterministischen Pfad bliebe die Bindung leer.
    """
    return [1.0, 0.0] if "Claim" in text else [0.0, 1.0]


def test_the_binder_keeps_a_numeric_hit_the_embedding_would_have_dropped():
    claim = "Claim: In der Pflege liegt die Quote bei 54 Prozent."
    pool = [_item("Die Pflege erreichte 54 Prozent.", "ev_care")]

    bound = bind_evidence_to_claim(claim, pool, _weak_embedder)

    assert [item["evidence_id"] for item in bound] == ["ev_care"]


def test_a_binding_carries_no_field_the_contract_forbids():
    """``ClaimEvidenceBindingModel`` ist ``extra="forbid"``.

    Ein zusätzliches Feld auf der Bindung lässt die Section-Validierung
    scheitern — und der dritte Reparaturlauf löscht daraufhin *jeden* Claim,
    dessen Fehlerpfad genannt wird, also jeden mit gebundener Evidence. Der
    Vorabruf-Treffer gehört deshalb in die Sortierung, nicht in die Bindung.
    """
    claim = "Claim: In der Pflege liegt die Quote bei 54 Prozent."
    # Contract-konforme ID: das Muster ist Teil derselben Validierung.
    evidence_id = "ev_" + "a1" * 16
    pool = [_item("Die Pflege erreichte 54 Prozent.", evidence_id)]

    bindings = bind_evidence_to_claim(claim, pool, _weak_embedder)

    assert bindings
    for binding in bindings:
        ClaimEvidenceBindingModel.model_validate(binding)


def test_a_numeric_hit_does_not_outrank_a_real_retrieval_hit():
    """Der Vorabruf ergänzt das Retrieval, er verdrängt es nicht."""
    claim = "Claim: In der Pflege liegt die Quote bei 54 Prozent."
    pool = [
        _item("Die Pflege erreichte 54 Prozent.", "ev_care"),
        _item("Claim-nahes Rauschen ohne Zahl.", "ev_topical"),
    ]

    bound = bind_evidence_to_claim(claim, pool, _weak_embedder)
    ids = [item["evidence_id"] for item in bound]

    assert "ev_care" in ids
    assert "ev_topical" in ids


def test_the_prefilter_stays_out_of_the_way_without_numbers():
    """Ohne Zahlen im Claim bleibt das Binding unverändert embedding-basiert."""
    pool = [_item("Die Pflege erreichte 54 Prozent.", "ev_care")]

    assert bind_evidence_to_claim("Claim: Die Belegschaft ist skeptisch.", pool, _weak_embedder) == []
