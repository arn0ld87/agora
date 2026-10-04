"""Die Herkunft eines Claims wird abgeleitet, nicht behauptet (Issue #1358).

Im Referenzlauf trug jeder der sechzehn Claims ``aggregation_basis="persona"``
und ``confidence_scope="simulation_consensus"``, obwohl seine ``evidence_refs``
auf 22 ``seed_corpus``- und 2 ``agent_action``-Items aufloesten. Diese Tests
halten die beiden Ursachen fest — den Literalwert und das nicht aufgeloeste
``source_kind`` — und die Grenzen der neuen Ableitung.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from app.contracts.report_v3 import Claim
from app.services.report_agent.claim_provenance import (
    derive_aggregation_basis,
    derive_confidence_scope,
)


def _bound(evidence_id: str, *, supports: bool = True, **extra: Any) -> Dict[str, Any]:
    """Ein Evidence-Dict *am Claim*, so wie der Binder es schreibt.

    Entscheidend ist, was hier **nicht** steht: keine ``source_kind``, kein
    ``type``. Genau daran scheiterte die alte Ableitung.
    """
    item: Dict[str, Any] = {
        "evidence_id": evidence_id,
        "match_score": 0.71,
        "retrieval_score": 0.68,
        "entailment": "SUPPORTED" if supports else "RELATED_ONLY",
        "entailment_reason": "Testfixture",
        "supports_claim": supports,
        "contradicts_claim": False,
    }
    item.update(extra)
    return item


def _index(*pairs: tuple[str, str]) -> Dict[str, Dict[str, Any]]:
    return {
        evidence_id: {"evidence_id": evidence_id, "source_kind": kind, "snippet": "…"}
        for evidence_id, kind in pairs
    }


# --- Die Ursache: source_kind steht nur im Index ---------------------------

def test_the_source_kind_is_looked_up_in_the_index():
    """Der Kern von #1358.

    Ohne Index bleibt die Gattung unaufloesbar und der Claim faellt auf
    Simulationskonsens zurueck — obwohl er aus dem Seed-Dokument stammt.
    """
    evidence: List[Dict[str, Any]] = [_bound("ev_1"), _bound("ev_2")]
    index = _index(("ev_1", "seed_corpus"), ("ev_2", "seed_corpus"))

    # #1766: ohne Index ist weder Gattung noch Stimme aufloesbar — der Claim
    # gilt konservativ als Einzelstimme, nicht mehr als Konsens.
    assert derive_confidence_scope(evidence, None) == "simulation_single_voice"
    assert derive_confidence_scope(evidence, index) == "evidence"
    assert derive_aggregation_basis(evidence, index) == "seed"


def test_a_kind_on_the_item_wins_over_the_index():
    """Traegt das Item die Gattung selbst, ist kein Nachschlagen noetig."""
    evidence = [_bound("ev_1", source_kind="agent_quote")]
    assert derive_aggregation_basis(evidence, _index(("ev_1", "seed_corpus"))) == "persona"


# --- Die vier Traegerschaften ----------------------------------------------

def test_seed_carried_claims_report_seed():
    evidence = [_bound(f"ev_{i}") for i in range(3)]
    index = _index(*[(f"ev_{i}", "seed_corpus") for i in range(3)])
    assert derive_aggregation_basis(evidence, index) == "seed"


def _voice_index(*triples: tuple[str, str, str]) -> Dict[str, Dict[str, Any]]:
    """Index-Records von ``agent_quote``-Evidence mit Persona-Identitaet.

    ``raw`` ist, was ``interview.to_dict()`` am Record hinterlaesst; dort steht
    der ``agent_name`` — die stabile Identitaet einer Persona. Ein Eintrag je
    Interviewantwort: dieselbe Persona kann mehrere Evidence-IDs haben.
    """
    return {
        evidence_id: {
            "evidence_id": evidence_id,
            "source_kind": "agent_quote",
            "snippet": "…",
            "persona_stakeholder_group": group,
            "raw": {"agent_name": agent_name, "agent_role": group},
        }
        for evidence_id, agent_name, group in triples
    }


def test_quote_carried_claims_report_persona():
    evidence = [_bound(f"ev_{i}") for i in range(3)]
    index = _voice_index(
        ("ev_0", "Anna", "Lehrerin"),
        ("ev_1", "Bernd", "Schulleiter"),
        ("ev_2", "Clara", "Elternvertreterin"),
    )
    assert derive_aggregation_basis(evidence, index) == "persona"
    # Nur Agentenstimmen: quellengebunden ist der Claim damit nicht.
    assert derive_confidence_scope(evidence, index) == "simulation_consensus"


# --- Eine einzelne Stimme ist kein Konsens (#1766) -------------------------

def test_one_voice_is_not_consensus():
    """Der Fall aus Lauf report_a8fa9ff9fad0: genau ein Interview stuetzt.

    Eine einzelne synthetische Perspektive ist kein Konsens — der Claim darf
    das Label ``simulation_consensus`` nicht tragen.
    """
    evidence = [_bound("ev_1")]
    index = _voice_index(("ev_1", "Anna", "Lehrerin"))
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_two_evidence_items_of_the_same_persona_are_one_voice():
    """Zwei Fragen an dieselbe Persona sind zwei Evidence-IDs, aber eine Stimme."""
    evidence = [_bound("ev_1"), _bound("ev_2")]
    index = _voice_index(("ev_1", "Anna", "Lehrerin"), ("ev_2", "Anna", "Lehrerin"))
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_the_persona_name_is_compared_normalised():
    evidence = [_bound("ev_1"), _bound("ev_2")]
    index = _voice_index(("ev_1", "Anna  Meier", "Lehrerin"), ("ev_2", "anna meier", "Lehrerin"))
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_two_different_personas_are_a_consensus():
    evidence = [_bound("ev_1"), _bound("ev_2")]
    index = _voice_index(("ev_1", "Anna", "Lehrerin"), ("ev_2", "Bernd", "Lehrer"))
    assert derive_confidence_scope(evidence, index) == "simulation_consensus"


def test_without_a_persona_name_the_stakeholder_group_identifies_the_voice():
    """Aeltere Records tragen keinen ``raw.agent_name`` — dann zaehlt die Gruppe."""
    evidence = [
        _bound("ev_1", persona_stakeholder_group="Buerger"),
        _bound("ev_2", persona_stakeholder_group="buerger"),
        _bound("ev_3", persona_stakeholder_group="Verwaltung"),
    ]
    index = _index(*[(f"ev_{i}", "agent_quote") for i in (1, 2, 3)])
    assert derive_confidence_scope(evidence, index) == "simulation_consensus"
    assert derive_confidence_scope(evidence[:2], index) == "simulation_single_voice"


def test_an_unresolvable_voice_counts_as_one_voice():
    """Ist die Identitaet nicht ermittelbar, gilt konservativ: eine Stimme."""
    evidence = [_bound(f"ev_{i}") for i in range(3)]
    index = _index(*[(f"ev_{i}", "agent_quote") for i in range(3)])
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_an_unresolvable_voice_does_not_add_to_a_resolved_one():
    evidence = [_bound("ev_1"), _bound("ev_unbekannt")]
    index = _voice_index(("ev_1", "Anna", "Lehrerin"))
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_seed_evidence_stays_evidence_regardless_of_the_voice_count():
    evidence = [_bound("ev_1")]
    assert derive_confidence_scope(evidence, _index(("ev_1", "seed_corpus"))) == "evidence"


def test_non_supporting_voices_do_not_count():
    evidence = [_bound("ev_1"), _bound("ev_2", supports=False)]
    index = _voice_index(("ev_1", "Anna", "Lehrerin"), ("ev_2", "Bernd", "Lehrer"))
    assert derive_confidence_scope(evidence, index) == "simulation_single_voice"


def test_a_tie_is_an_aggregate_not_a_winner():
    """Bei Gleichstand traegt keine Gattung den Claim allein.

    Eine einfache Mehrheit genuegt nicht — verlangt wird mehr als die Haelfte.
    """
    evidence = [_bound("ev_1"), _bound("ev_2")]
    index = _index(("ev_1", "seed_corpus"), ("ev_2", "agent_quote"))
    assert derive_aggregation_basis(evidence, index) == "aggregat"


def test_a_strict_majority_carries_the_claim():
    evidence = [_bound("ev_1"), _bound("ev_2"), _bound("ev_3")]
    index = _index(
        ("ev_1", "seed_corpus"), ("ev_2", "seed_corpus"), ("ev_3", "agent_quote")
    )
    assert derive_aggregation_basis(evidence, index) == "seed"
    assert derive_confidence_scope(evidence, index) == "evidence"


def test_no_supporting_evidence_is_a_data_gap():
    evidence = [_bound("ev_1", supports=False)]
    assert derive_aggregation_basis(evidence, _index(("ev_1", "seed_corpus"))) == "datenluecke"
    assert derive_confidence_scope(evidence, _index(("ev_1", "seed_corpus"))) == "simulation_consensus"


@pytest.mark.parametrize("kind", ["graph_relation", "web_source"])
def test_derived_sources_bind_the_claim_without_claiming_seed_provenance(kind: str):
    """Eine Graph-Kante stammt aus dem Korpus, ist aber selbst schon Aggregation.

    Sie bindet den Claim an eine Quelle (``evidence``), darf ihn aber nicht als
    Dokumentfakt ausweisen — das unterschlaege einen Verarbeitungsschritt.
    """
    evidence = [_bound("ev_1"), _bound("ev_2")]
    index = _index(("ev_1", kind), ("ev_2", kind))
    assert derive_confidence_scope(evidence, index) == "evidence"
    assert derive_aggregation_basis(evidence, index) == "aggregat"


def test_unresolvable_kinds_cannot_carry_a_majority():
    """Ein Item, dessen Gattung nirgends steht, zaehlt mit — aber fuer nichts.

    Es erhoeht die Grundgesamtheit und kann eine Mehrheit damit verhindern,
    nie begruenden.
    """
    evidence = [_bound("ev_1"), _bound("ev_unbekannt")]
    index = _index(("ev_1", "seed_corpus"))
    assert derive_aggregation_basis(evidence, index) == "aggregat"
    # Die eine aufgeloeste Quelle bindet den Claim trotzdem.
    assert derive_confidence_scope(evidence, index) == "evidence"


def test_a_broken_evidence_list_does_not_raise():
    assert derive_aggregation_basis("kein-list", {}) == "datenluecke"
    assert derive_confidence_scope(None, {}) == "simulation_consensus"


# --- Der Vertrag weist Widersprueche ab ------------------------------------

def _claim(**overrides: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": "C1_01",
        "statement": "Der Vollstart birgt gravierende Risiken.",
        "evidence_refs": ["ev_1"],
        "confidence": "medium",
        "aggregation_basis": "seed",
        "confidence_scope": "evidence",
    }
    payload.update(overrides)
    return payload


def test_a_consistent_claim_validates():
    assert Claim.model_validate(_claim()).aggregation_basis == "seed"


def test_seed_carried_but_simulation_scoped_is_rejected():
    """Der Fall aus dem Referenzlauf, nur andersherum benannt.

    ``seed_corpus`` ist quellengebunden — ein seed-getragener Claim kann nicht
    zugleich reiner Simulationskonsens sein.
    """
    with pytest.raises(ValidationError, match="schliessen sich aus"):
        Claim.model_validate(_claim(confidence_scope="simulation_consensus"))


def test_a_data_gap_cannot_be_source_bound():
    with pytest.raises(ValidationError, match="kein quellengebundenes"):
        Claim.model_validate(
            _claim(aggregation_basis="datenluecke", confidence_scope="evidence")
        )


def test_a_data_gap_cannot_carry_a_high_label():
    with pytest.raises(ValidationError, match="traegt keinen Befund"):
        Claim.model_validate(
            _claim(
                aggregation_basis="datenluecke",
                confidence_scope="simulation_consensus",
                confidence="high",
            )
        )


def test_persona_carried_claims_may_still_be_source_bound():
    """Kein Widerspruch, und deshalb ausdruecklich erlaubt.

    Drei Zitate und ein Seed-Beleg: die Traegerschaft ist ``persona``, die
    Quellenbindung besteht trotzdem.
    """
    assert Claim.model_validate(
        _claim(aggregation_basis="persona", confidence_scope="evidence")
    ).confidence_scope == "evidence"
