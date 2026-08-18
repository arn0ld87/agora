"""Numerisches Entailment: ein anderer Zahlenwert ist noch kein Widerspruch.

Aus dem Referenzlauf ``report_cc2ef45da5e9``. Der Trust-Layer entfernte den
Satz

    "Die Schulungsquote der Pflege-Nachtschicht liegt bei 31 Prozent, während
     der Projektplan mindestens 80 Prozent der unmittelbar betroffenen
     Beschäftigten vor Produktivstart fordert."

als ``prose_fact_contradicted``. Die beiden Zahlen widersprechen sich aber
nicht: 31 % ist ein gemessener Ist-Wert einer Teilgruppe, 80 % eine
Mindestanforderung an eine größere Grundgesamtheit. Ein Widerspruch entsteht
erst, wenn *dieselbe* Kennzahl über *dieselbe* Gruppe mit *derselben*
Faktenart unterschiedliche Werte trägt.

Der zweite Befund dieser Datei ist die Gegenprobe: echte Widersprüche wurden
gar nicht erkannt, weil die Bezugsgruppe ausschließlich rechts der Zahl
gesucht wurde. Deutsch stellt sie regelmäßig ins Vorfeld ("Die Verwaltung
erreichte 91 Prozent") — dort fand sie niemand, und der Fakt entstand nie.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.evidence_entailment import (
    BoundKind,
    EntailmentVerdict,
    FactModality,
    classify_evidence,
    extract_numeric_facts,
)


def _snippet(text: str) -> Dict[str, Any]:
    return {"snippet": text, "source_kind": "seed_corpus"}


# --- Faktenextraktion: die Bezugsgruppe steht auch links --------------------


def test_a_subject_in_the_vorfeld_still_produces_a_fact():
    """"Die Verwaltung erreichte 91 Prozent." trägt seine Gruppe links.

    Ohne Vorfeld-Auswertung entstand hier gar kein ``NumericFact``: rechts der
    Zahl steht nur der Satzpunkt. Damit konnte weder ein Beleg noch ein
    Widerspruch gefunden werden — die Zahl war für den Trust-Layer unsichtbar.
    """
    facts = extract_numeric_facts("Die Verwaltung erreichte 91 Prozent.")

    assert len(facts) == 1
    assert facts[0].value == 91.0
    assert "verwaltung" in facts[0].subject.lower()


def test_a_trailing_noun_still_wins_over_the_vorfeld():
    """Steht rechts der Zahl eine Bezugsgruppe, bleibt sie maßgeblich."""
    facts = extract_numeric_facts("Im Ärztlichen Dienst sind 83 Prozent der Pflegekräfte geschult.")

    assert facts
    assert "pflegekräfte" in facts[0].subject.lower()


# --- Faktenart: Ist-Wert, Zielwert, Mindest-/Höchstwert ---------------------


def test_a_minimum_requirement_is_recognised_as_a_lower_bound():
    facts = extract_numeric_facts(
        "Der Projektplan fordert mindestens 80 Prozent der Beschäftigten geschult."
    )

    assert facts
    assert facts[0].bound is BoundKind.AT_LEAST
    assert facts[0].modality is FactModality.NORMATIVE


def test_a_measured_share_is_an_exact_actual_value():
    facts = extract_numeric_facts("Aktuell sind 31 Prozent der Beschäftigten geschult.")

    assert facts
    assert facts[0].bound is BoundKind.EXACT
    assert facts[0].modality is FactModality.FACTUAL


# --- Der Kernfall: kein Widerspruch ----------------------------------------


def test_actual_value_does_not_contradict_minimum_requirement():
    """31 % Ist gegen 80 % Mindestanforderung — dieselbe Gruppe, kein Widerspruch.

    Der Ist-Wert unterschreitet die Anforderung. Genau das *sagt* der Satz
    aus; die Quelle widerlegt ihn nicht, sie nennt den Zielwert.
    """
    result = classify_evidence(
        "Aktuell sind 31 Prozent der Beschäftigten geschult.",
        _snippet(
            "Der Projektplan fordert mindestens 80 Prozent der Beschäftigten "
            "geschult vor Produktivstart."
        ),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED


def test_actual_subgroup_value_does_not_contradict_global_target():
    """Der Satz aus dem Referenzlauf, wörtlich."""
    result = classify_evidence(
        "Die Schulungsquote der Pflege-Nachtschicht liegt bei 31 Prozent, während "
        "der Projektplan mindestens 80 Prozent der unmittelbar betroffenen "
        "Beschäftigten vor Produktivstart fordert.",
        _snippet(
            "Der Projektplan fordert vor Produktivstart mindestens 80 Prozent der "
            "unmittelbar betroffenen Beschäftigten geschult."
        ),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED


def test_a_subgroup_actual_does_not_contradict_a_wider_population_actual():
    """31 % der Nachtschicht gegen 54 % der Pflege — verschachtelte Gruppen.

    Die Nachtschicht ist eine Teilmenge der Pflege. Beide Werte können
    gleichzeitig zutreffen; die Teilgruppe darf vom Mittelwert abweichen.
    """
    result = classify_evidence(
        "In der Pflege-Nachtschicht sind 31 Prozent der Beschäftigten geschult.",
        _snippet("In der Pflege sind 54 Prozent der Beschäftigten geschult."),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED
    assert "scope_mismatch" in result.checks


def test_different_subject_same_number_is_not_a_contradiction():
    result = classify_evidence(
        "Die Pflege erreichte 54 Prozent Zustimmung.",
        _snippet("Die Verwaltung erreichte 54 Prozent Zustimmung."),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED


def test_a_target_is_not_contradicted_by_a_different_target():
    """Zwei Zielwerte für verschiedene Zeitpunkte sind kein Widerspruch."""
    result = classify_evidence(
        "Bis zum Produktivstart sollen 80 Prozent der Beschäftigten geschult sein.",
        _snippet("Im ersten Quartal sollen 40 Prozent der Beschäftigten geschult sein."),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED


# --- Gegenprobe: echte Widersprüche bleiben Widersprüche --------------------


def test_a_real_value_mismatch_is_still_contradicted():
    """Der Gegenbeweis aus der Spezifikation: 91 % gegen 42 %, gleiche Gruppe."""
    result = classify_evidence(
        "Die Verwaltung erreichte 42 Prozent.",
        _snippet("Die Verwaltung erreichte 91 Prozent."),
    )

    assert result.verdict is EntailmentVerdict.CONTRADICTED
    assert "value_mismatch" in result.checks


def test_an_actual_below_a_maximum_is_not_contradicted():
    """Eine Obergrenze wird erst durch Überschreiten widerlegt."""
    result = classify_evidence(
        "Der manuelle Fallback dauerte höchstens 15 Minuten.",
        _snippet("Im Test dauerte der manuelle Fallback 9 Minuten."),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED
    assert "bound_satisfied" in result.checks


def test_a_measurement_above_the_stated_maximum_is_a_contradiction():
    """Eine gerissene Grenze ist ein Widerspruch, kein Formatunterschied.

    Solange "höchstens" zugleich als Zielmarker galt, war jede Schranke gegen
    jeden gemessenen Wert "nicht vergleichbar" — und ein tatsächlich
    überschrittener Grenzwert verschwand als ``INSUFFICIENT``.
    """
    result = classify_evidence(
        "Der manuelle Fallback dauerte höchstens 15 Minuten.",
        _snippet("Im Test dauerte der manuelle Fallback 22 Minuten."),
    )

    assert result.verdict is EntailmentVerdict.CONTRADICTED


def test_a_requirement_is_not_contradicted_by_a_measurement_below_it():
    """Eine unerfüllte Forderung ist keine widerlegte Behauptung.

    Das ist der Unterschied, den :class:`FactModality` trägt: "der Projektplan
    *fordert* mindestens 80 Prozent" behauptet nichts über die Wirklichkeit.
    """
    result = classify_evidence(
        "Aktuell sind 31 Prozent der Beschäftigten geschult.",
        _snippet(
            "Der Projektplan fordert mindestens 80 Prozent der Beschäftigten "
            "als geschult."
        ),
    )

    assert result.verdict is not EntailmentVerdict.CONTRADICTED
    assert "fact_type_mismatch" in result.checks


def test_a_source_that_names_its_origin_does_not_dodge_a_contradiction():
    """Eine Quellenangabe ist kein Populationsunterschied.

    "Laut Betriebsrat" links der Zahl machte den Scope beider Sätze
    verschieden — und damit einen echten 31-gegen-54-Widerspruch über
    dieselbe Gruppe unsichtbar.
    """
    result = classify_evidence(
        "In der Pflege sind 31 Prozent der Beschäftigten geschult.",
        _snippet(
            "Laut Betriebsrat sind in der Pflege 54 Prozent der Beschäftigten "
            "geschult."
        ),
    )

    assert result.verdict is EntailmentVerdict.CONTRADICTED
