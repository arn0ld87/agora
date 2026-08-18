"""Die Herkunft einer operativen Zahl wird gebunden, nicht geraten (#1359 A).

Der Bericht fordert in Abschnitt 1 vier Wochen Pilotbetrieb und in Abschnitt 7
mindestens acht. Beide Zahlen standen im Artefakt als ``model_proposal`` mit
``evidence_status="heuristic"`` und leerer ``evidence_refs``-Liste — als haette
das Modell sich beide ausgedacht. Die vier Wochen stammen aus dem Seed.

Die tragende Einsicht: **Schwellen wurden nie an Evidence gebunden.** Eine
Ableitung aus vorhandenen Referenzen haette an diesem Fall nichts geaendert,
weil es keine gab.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from app.contracts.report_v3 import Threshold
from app.services.report_agent.threshold_provenance import (
    apply_threshold_provenance,
    bind_threshold,
    resolve_threshold_provenance,
    snippet_carries_value,
)

SEED_ID = "ev_" + "a1" * 16
QUOTE_ID = "ev_" + "b2" * 16
WEB_ID = "ev_" + "c3" * 16


def _record(evidence_id: str, kind: str, snippet: str) -> Dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_kind": kind,
        "snippet": snippet,
        "type": "seed_document",
        "source": "fixture",
        "producer_key": "threshold-provenance-fixture",
    }


def _threshold(
    value: float = 4.0,
    unit: str = "weeks",
    origin: str = "model_proposal",
    evidence_status: str = "heuristic",
    evidence_refs: list[str] | None = None,
) -> Threshold:
    return Threshold(
        id="pilot_dauer_mitte",
        label="Pilotdauer",
        value=value,
        unit=unit,
        purpose="target",
        origin=origin,  # type: ignore[arg-type]
        evidence_status=evidence_status,  # type: ignore[arg-type]
        evidence_refs=evidence_refs or [],
    )


# --- Der Abgleich Wert + Einheit -------------------------------------------

@pytest.mark.parametrize("text", [
    "Der Pilotbetrieb laeuft ueber 4 Wochen.",
    "Der Pilotbetrieb laeuft ueber vier Wochen.",
    "Vorgesehen sind vier volle Wochen Pilotbetrieb.",
])
def test_the_value_is_found_in_digits_and_in_words(text: str):
    """``extract_numeric_facts`` liest nur Ziffern — „vier Wochen" faende es nicht."""
    assert snippet_carries_value(text, 4.0, "weeks") is True


def test_a_different_value_does_not_bind():
    """Ein Beleg ueber sechs Wochen belegt keine Vier-Wochen-Schwelle.

    Auch dann nicht, wenn er vom selben Pilotbetrieb handelt.
    """
    assert snippet_carries_value(
        "Der Pilotbetrieb laeuft ueber sechs Wochen.", 4.0, "weeks"
    ) is False


def test_the_unit_must_stand_close_to_the_number():
    """Sonst belegte „4 Standorte mit je 8 Wochen Vorlauf" vier Wochen."""
    text = "Vier Standorte starten mit jeweils acht Wochen Vorlauf."
    assert snippet_carries_value(text, 4.0, "weeks") is False
    assert snippet_carries_value(text, 8.0, "weeks") is True


def test_a_percentage_binds_on_its_own_unit():
    assert snippet_carries_value("Das Schulungsziel liegt bei 80 Prozent.", 80.0, "percent")
    assert snippet_carries_value("Verwaltung: 91 % geschult.", 91.0, "percent")
    assert not snippet_carries_value("Es dauert 80 Tage.", 80.0, "percent")


def test_a_bare_count_needs_no_unit_word():
    assert snippet_carries_value("17 Pflegekraefte fordern eine Verschiebung.", 17.0, "count")


def test_an_unknown_unit_never_binds():
    """Ein Zahlentreffer ohne bekanntes Einheitenwort waere Raterei."""
    assert snippet_carries_value("Der Wert liegt bei 4 Blorks.", 4.0, "blorks") is False


# --- Die Ableitung ---------------------------------------------------------

def test_a_number_from_the_seed_becomes_a_document_requirement():
    """Der Referenzfall: die vier Wochen der Pflegedienstleitung."""
    index = {SEED_ID: _record(
        SEED_ID, "seed_corpus",
        "Die Pflegedienstleitung schlaegt einen Pilotbetrieb von vier Wochen vor.",
    )}
    update = resolve_threshold_provenance(_threshold(), index)

    assert update["origin"] == "document_requirement"
    assert update["evidence_status"] == "verified"
    assert update["evidence_refs"] == [SEED_ID]


def test_a_number_only_the_agents_named_is_a_simulation_proposal():
    index = {QUOTE_ID: _record(
        QUOTE_ID, "agent_quote", "Ich haette gern vier Wochen Vorlauf.",
    )}
    update = resolve_threshold_provenance(_threshold(), index)

    assert update["origin"] == "simulation_proposal"
    assert update["evidence_status"] == "verified"


def test_the_document_wins_over_the_simulation():
    """Steht die Zahl in beiden, ist sie eine Anforderung — nicht ein Wunsch."""
    index = {
        QUOTE_ID: _record(QUOTE_ID, "agent_quote", "Vier Wochen waeren mir recht."),
        SEED_ID: _record(SEED_ID, "seed_corpus", "Pilotbetrieb: vier Wochen."),
    }
    update = resolve_threshold_provenance(_threshold(), index)
    assert update["origin"] == "document_requirement"
    assert set(update["evidence_refs"]) == {SEED_ID, QUOTE_ID}


def test_a_web_hit_backs_the_number_without_renaming_its_origin():
    """Ob ein Web-Fund Norm, Messung oder fremde Empfehlung ist, sagt die Gattung nicht."""
    index = {WEB_ID: _record(WEB_ID, "web_source", "Ueblich sind vier Wochen.")}
    update = resolve_threshold_provenance(_threshold(), index)

    assert update["evidence_status"] == "verified"
    assert update["evidence_refs"] == [WEB_ID]
    assert "origin" not in update


# --- Was ohne Beleg nicht stehenbleiben darf -------------------------------

def test_an_unbacked_document_requirement_falls_back_to_a_proposal():
    """Eine Zahl, die als Dokumentanforderung auftritt, ohne dass ein Dokument
    sie nennt, ist genau die Behauptung, gegen die #1160 E antritt."""
    update = resolve_threshold_provenance(
        _threshold(origin="document_requirement", evidence_status="derived"), {}
    )
    assert update["origin"] == "model_proposal"
    assert update["evidence_status"] == "heuristic"


@pytest.mark.parametrize(
    "origin", ["document_requirement", "empirical_data", "external_standard", "operator_policy"]
)
def test_every_authoritative_origin_needs_a_backing(origin: str):
    update = resolve_threshold_provenance(_threshold(origin=origin), {})
    assert update["origin"] == "model_proposal"


def test_an_honest_proposal_is_left_alone():
    """``model_proposal`` ohne Beleg ist korrekt — daran ist nichts zu heilen."""
    assert resolve_threshold_provenance(_threshold(), {}) == {}


def test_a_simulation_proposal_without_a_hit_is_not_downgraded():
    """Sie behauptet keine Verbindlichkeit, also gibt es nichts zu entziehen."""
    assert resolve_threshold_provenance(
        _threshold(origin="simulation_proposal"), {}
    ) == {}


def test_a_hand_curated_reference_is_not_touched():
    """Traegt die Schwelle bereits eine Referenz, bleibt die Herkunft stehen.

    Der Rueckfall zielt auf geratene Herkunft, nicht auf kuratierte.
    """
    assert resolve_threshold_provenance(
        _threshold(origin="operator_policy", evidence_refs=[SEED_ID]), {}
    ) == {}


# --- Der Durchlauf ---------------------------------------------------------

def test_both_reference_thresholds_end_up_where_they_belong():
    """Vier Wochen aus dem Seed, acht Wochen als eigene Empfehlung."""
    index = {SEED_ID: _record(
        SEED_ID, "seed_corpus",
        "Die Pflegedienstleitung schlaegt einen Pilotbetrieb von vier Wochen vor.",
    )}
    four = _threshold(value=4.0)
    eight = _threshold(value=8.0)

    resolved = apply_threshold_provenance([four, eight], index)

    assert resolved[0].origin == "document_requirement"
    assert resolved[0].evidence_refs == [SEED_ID]
    # Die acht Wochen sind eine Empfehlung der Analyse und bleiben eine.
    assert resolved[1].origin == "model_proposal"
    assert resolved[1].evidence_refs == []


def test_binding_reports_the_source_kind_alongside_the_id():
    index = {SEED_ID: _record(SEED_ID, "seed_corpus", "Pilotbetrieb: 4 Wochen.")}
    assert bind_threshold(4.0, "weeks", index) == [(SEED_ID, "seed_corpus")]


def test_a_broken_index_entry_is_skipped_not_raised():
    assert bind_threshold(4.0, "weeks", {SEED_ID: "kein-dict"}) == []
