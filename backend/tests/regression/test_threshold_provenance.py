"""Schwellenwerte: einmal je Sachverhalt, mit belegbarer Herkunft.

Der Referenzlauf ``report_cc2ef45da5e9`` exportierte 27 Thresholds. Alle
``heuristic``, alle mit leeren ``evidence_refs`` — auch die, die wörtlich im
Seed-Dokument standen. Mehrere Werte erschienen doppelt (54 % Pflege, 31 %
Nachtschicht, 14 %, 6 %, 38 Fälle, 80 %, 15 Minuten), und derselbe Wert trug
an einer Stelle ``simulation_proposal``, an anderer ``empirical_data``.
"""

from __future__ import annotations

from typing import Any, Dict

from app.contracts.report_v3 import Threshold
from app.services.report_agent.threshold_provenance import (
    bind_threshold_provenance,
    canonical_threshold_key,
    dedup_thresholds,
    normalize_unit,
)


def _threshold(**overrides: Any) -> Threshold:
    payload: Dict[str, Any] = {
        "id": "th_01",
        "label": "Schulungsquote vor Produktivstart",
        "value": 80.0,
        "unit": "percent",
        "purpose": "target",
        "origin": "model_proposal",
    }
    payload.update(overrides)
    return Threshold.model_validate(payload)


def _record(text: str, evidence_id: str) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "source_kind": "seed_corpus", "snippet": text}


SEED = _record(
    "Der Projektplan fordert vor Produktivstart mindestens 80 Prozent "
    "Schulungsquote der unmittelbar betroffenen Beschäftigten.",
    "ev_seed_80",
)


# --- Kanonischer Schlüssel --------------------------------------------------


def test_the_same_number_phrased_differently_shares_a_key():
    left = _threshold(id="th_01", label="Schulungsquote vor Produktivstart")
    right = _threshold(id="th_09", label="Vor Produktivstart: Schulungsquote", unit="%")

    assert canonical_threshold_key(left) == canonical_threshold_key(right)


def test_a_different_metric_keeps_its_own_key():
    left = _threshold(label="Schulungsquote")
    right = _threshold(label="Systemverfügbarkeit")

    assert canonical_threshold_key(left) != canonical_threshold_key(right)


def test_a_different_value_keeps_its_own_key():
    assert canonical_threshold_key(_threshold(value=80.0)) != canonical_threshold_key(
        _threshold(value=54.0)
    )


def test_a_different_purpose_keeps_its_own_key():
    """Ein Zielwert und eine Obergrenze sind zwei Aussagen, kein Duplikat."""
    assert canonical_threshold_key(
        _threshold(purpose="target")
    ) != canonical_threshold_key(_threshold(purpose="limit"))


def test_unit_spellings_are_normalised():
    assert normalize_unit("%") == normalize_unit("Prozent") == "percent"
    assert normalize_unit("Minuten") == "minutes"


# --- Deduplizierung ---------------------------------------------------------


def test_the_same_seed_value_from_two_sections_yields_one_threshold():
    """Das Akzeptanzkriterium aus der Spezifikation."""
    result = dedup_thresholds([
        _threshold(id="th_01"),
        _threshold(id="th_07", label="Vor Produktivstart: Schulungsquote", unit="%"),
    ])

    assert len(result) == 1


def test_merging_unites_the_evidence_of_both_entries():
    result = dedup_thresholds([
        _threshold(id="th_01", evidence_refs=["ev_a"], evidence_status="verified"),
        _threshold(id="th_07", evidence_refs=["ev_b"], evidence_status="verified"),
    ])

    assert result[0].evidence_refs == ["ev_a", "ev_b"]
    assert result[0].evidence_status == "verified"


def test_two_unbacked_origins_in_conflict_fall_back_to_the_weaker_claim():
    """Der Referenzfall: derselbe Wert einmal als Messung, einmal als Vorschlag.

    Keine der beiden Angaben ist belegt. Die lautere zu übernehmen, hieße eine
    Herkunft zu behaupten, die niemand geprüft hat — der Contract sagt es
    selbst: "Im Zweifel model_proposal".
    """
    result = dedup_thresholds([
        _threshold(id="th_01", origin="empirical_data"),
        _threshold(id="th_07", origin="simulation_proposal"),
    ])

    assert result[0].origin == "simulation_proposal"


def test_a_backed_origin_survives_the_merge():
    result = dedup_thresholds([
        _threshold(
            id="th_01",
            origin="document_requirement",
            evidence_refs=["ev_seed_80"],
            evidence_status="verified",
        ),
        _threshold(id="th_07", origin="model_proposal"),
    ])

    assert result[0].origin == "document_requirement"


def test_dedup_keeps_the_order_of_first_appearance():
    result = dedup_thresholds([
        _threshold(id="th_01", label="Schulungsquote", value=80.0),
        _threshold(id="th_02", label="Fallbackdauer", value=15.0, unit="minutes"),
        _threshold(id="th_03", label="Schulungsquote", value=80.0),
    ])

    assert [item.label for item in result] == ["Schulungsquote", "Fallbackdauer"]


# --- Provenance -------------------------------------------------------------


def test_a_documented_seed_value_does_not_stay_heuristic():
    """Das zweite Akzeptanzkriterium aus der Spezifikation."""
    result = bind_threshold_provenance([_threshold()], [SEED])

    assert result[0].evidence_refs == ["ev_seed_80"]
    assert result[0].evidence_status == "verified"


def test_a_value_no_source_mentions_stays_untouched():
    result = bind_threshold_provenance(
        [_threshold(label="Systemverfügbarkeit", value=99.9)], [SEED]
    )

    assert result[0].evidence_refs == []
    assert result[0].evidence_status == "heuristic"


def test_a_matching_number_on_an_unrelated_topic_is_not_bound():
    """Gegenprobe: dieselbe Zahl, anderes Thema, kein Beleg."""
    noise = _record("An 80 Prozent der Standorte gibt es eine Kantine.", "ev_canteen")

    result = bind_threshold_provenance([_threshold()], [noise])

    assert result[0].evidence_refs == []


def test_an_already_bound_threshold_is_left_alone():
    result = bind_threshold_provenance(
        [_threshold(evidence_refs=["ev_model"], evidence_status="derived")], [SEED]
    )

    assert result[0].evidence_refs == ["ev_model"]
    assert result[0].evidence_status == "derived"


def test_a_percent_value_is_not_bound_to_an_absolute_one():
    absolute = _record("Es wurden 80 Schulungen durchgeführt zur Schulungsquote.", "ev_abs")

    result = bind_threshold_provenance([_threshold()], [absolute])

    assert result[0].evidence_refs == []


def test_an_empty_pool_changes_nothing():
    assert bind_threshold_provenance([_threshold()], []) == [_threshold()]


def test_an_inferred_record_cannot_verify_a_threshold():
    """Eine Modellableitung belegt nichts.

    Sonst entstünde ``origin="model_proposal"`` mit
    ``evidence_status="verified"``: eine Zahl, die sich selbst als belegt
    ausweist, weil das Modell sie zweimal genannt hat.
    """
    inferred = {
        "evidence_id": "ev_inferred",
        "source_kind": "inferred",
        "snippet": "Vermutlich sind mindestens 80 Prozent Schulungsquote nötig.",
    }

    result = bind_threshold_provenance([_threshold()], [inferred])

    assert result[0].evidence_refs == []
    assert result[0].evidence_status == "heuristic"


def test_a_web_source_cannot_verify_a_threshold():
    web = {
        "evidence_id": "ev_web",
        "source_kind": "web_source",
        "snippet": "Branchenblogs nennen 80 Prozent Schulungsquote als üblich.",
    }

    assert bind_threshold_provenance([_threshold()], [web])[0].evidence_refs == []
