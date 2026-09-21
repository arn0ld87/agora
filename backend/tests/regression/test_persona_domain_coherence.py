"""Gruppen werden keine Personen, und Kliniken keine Werkhallen.

Der Referenzlauf ``report_cc2ef45da5e9`` erzeugte aus einem
``HospitalNetwork`` eine einzelne erfundene Person, aus einer
``EmployeeGroup`` eine "Sachbearbeiterin in der Fertigungsplanung" und aus
einem ``PatientAdvisoryCouncil`` einen "Schichtleiter Maschinenbau". Die
Quelle beschrieb einen Klinik-Rollout.

Beide Fehler sind für sich plausibel — und genau das ist das Problem: eine
erfundene Biografie fällt nur auf, wenn man ihr Fach mit der Quelle vergleicht.
"""

from __future__ import annotations

import pytest

from app.services.persona_domain_coherence import (
    _domains_in,
    coherence_findings,
    detect_domain_drift,
    is_collective_entity_type,
)

#: Die Quellenlage des Referenzlaufs.
CLINIC_SOURCE = (
    "Städtischer Klinikverbund Falkenbrück: Rollout von Nexora Triage Assist "
    "in Notaufnahme und Pflege. Betroffen sind Pflegekräfte, der Ärztliche "
    "Dienst und die Patientenaufnahme."
)


# --- Kollektive Entitätstypen -----------------------------------------------


@pytest.mark.parametrize(
    "entity_type",
    [
        "HospitalNetwork",
        "EmployeeGroup",
        "PatientAdvisoryCouncil",
        "WorkingGroup",
        "Organization",
        "Department",
        "Committee",
        "Council",
        "Association",
    ],
)
def test_a_collective_entity_type_is_recognised(entity_type: str):
    """Die Typen aus der Spezifikation, einzeln."""
    assert is_collective_entity_type(entity_type) is True


@pytest.mark.parametrize(
    "entity_type", ["Person", "Student", "Professor", "Expert", "Journalist"]
)
def test_an_individual_entity_type_stays_individual(entity_type: str):
    assert is_collective_entity_type(entity_type) is False


def test_a_compound_ending_in_a_person_stays_individual():
    """"StaffMember" enthält "Staff" — und ist trotzdem ein Mensch.

    Entschieden wird am Grundwort. Ein Bestandteil-Vergleich hätte hier eine
    Einzelperson zum Kollektiv erklärt, also den umgekehrten Fehler erzeugt.
    """
    assert is_collective_entity_type("StaffMember") is False


def test_a_plural_type_is_recognised():
    assert is_collective_entity_type("EmployeeGroups") is True


def test_snake_case_and_spaces_are_read_the_same_way():
    assert is_collective_entity_type("patient_advisory_council") is True
    assert is_collective_entity_type("Patient Advisory Council") is True


def test_an_empty_type_is_not_collective():
    assert is_collective_entity_type("") is False


# --- Domänendrift -----------------------------------------------------------


def test_a_manufacturing_role_in_a_clinic_source_is_drift():
    """Der Fall aus dem Referenzlauf."""
    assert detect_domain_drift(
        "Schichtleiter Maschinenbau in der Produktionsleitung", CLINIC_SOURCE
    ).drifted == ["manufacturing"]


def test_a_clerk_in_production_planning_is_drift():
    assert detect_domain_drift(
        "Sachbearbeiterin in der Fertigungsplanung", CLINIC_SOURCE
    ).drifted == ["manufacturing"]


def test_a_role_from_the_source_domain_is_no_drift():
    result = detect_domain_drift("Pflegekraft in der Nachtschicht", CLINIC_SOURCE)
    assert result.drifted == []
    assert result.unverifiable is False


def test_a_tied_main_domain_no_longer_protects_against_drift_1471():
    """Umgekehrte Erwartung seit #1471 — vorher hieß dieser Test '..._is_no_drift'.

    Alte Annahme: Wer Medizintechnik in der Klinik betreut, trägt zu Recht
    Vokabular aus beiden Fächern, also kein Drift. Das war das alte
    ANY-Overlap-Verhalten, hart in diesem Test fixiert.

    Neue Annahme (#1471): "Instandhaltung" (Fertigung, ein exakter Treffer)
    und "Klinikum" (Gesundheitswesen, ein exakter Treffer) liefern einen
    Gleichstand — keine der beiden Domänen ist die eindeutige Hauptdomäne der
    Persona. Ein Gleichstand schützt nicht mehr: die Persona trägt Fachwörter
    (Fertigung), die die Quelle nicht hergibt, und das wird jetzt gemeldet.
    """
    result = detect_domain_drift(
        "Instandhaltung der Medizintechnik im Klinikum", CLINIC_SOURCE
    )
    assert result.drifted == ["manufacturing"]
    assert result.unverifiable is False


def test_a_healthcare_main_domain_drifts_against_a_pure_education_source():
    """Das Beispiel aus der Spezifikation zu #1471.

    Die Persona hat ihre Hauptdomäne eindeutig im Gesundheitswesen (drei
    exakte Treffer) und berührt Bildung nur als Nebendomäne (ein exakter
    Treffer). Gegenüber einer reinen Bildungsquelle ist das Drift — auch wenn
    die Nebendomäne der Persona zur Quelle passt, schützt das die Persona
    nicht mehr, weil ihre Hauptdomäne fehlt.
    """
    persona_text = (
        "Ärztin für Diagnose und Therapie, betreut zusätzlich die "
        "Patientenaufnahme; hilft gelegentlich in der Schule aus."
    )
    source_text = (
        "Die Schule plant den neuen Lehrplan; das Kollegium bespricht die "
        "Didaktik im Unterricht."
    )

    result = detect_domain_drift(persona_text, source_text)

    assert result.drifted == ["healthcare"]
    assert result.unverifiable is False


def test_a_persona_whose_main_domain_matches_the_source_is_unremarkable():
    """Fachlich passende Persona: eindeutige Hauptdomäne deckt sich mit der Quelle."""
    persona_text = "Pflegekraft mit Schwerpunkt Diagnose und Therapie in der Notaufnahme."

    result = detect_domain_drift(persona_text, CLINIC_SOURCE)

    assert result.drifted == []
    assert result.unverifiable is False


def test_a_neutral_role_is_no_drift():
    """Ohne Fachvokabular gibt es nichts zu beanstanden."""
    result = detect_domain_drift("Mitarbeiterin der Verwaltung", CLINIC_SOURCE)
    assert result.drifted == []
    assert result.unverifiable is False


def test_a_source_without_a_domain_is_unverifiable_not_clean():
    """Eine Quelle ohne erkennbares Fach ist ungeprüft, nicht entwarnt.

    Vorher lieferte ``detect_domain_drift`` hier dieselbe leere Liste wie bei
    einer geprüften, sauberen Quelle — ununterscheidbar. Seit #1471 trägt das
    Ergebnis ``unverifiable=True`` und ist damit nicht mehr versehentlich als
    Entwarnung lesbar.
    """
    result = detect_domain_drift("Schichtleiter Maschinenbau", "Ein Projekt startet.")
    assert result.drifted == []
    assert result.unverifiable is True


def test_a_network_in_the_source_is_not_read_as_manufacturing():
    """"Netzwerk" enthält "werk" — ein kurzer Marker hätte hier zugeschlagen."""
    result = detect_domain_drift("Betreuer im Klinik-Netzwerk", CLINIC_SOURCE)
    assert result.drifted == []
    assert result.unverifiable is False


@pytest.mark.parametrize(
    "text", ["Ladestation", "Arbeitsstation", "Bahnstation am Werkstor"]
)
def test_a_station_compound_is_not_read_as_healthcare(text: str):
    """"station" steckt in Wörtern ohne jeden Klinikbezug.

    Ein Fehlalarm hier ist teuer: war die falsche Domäne die einzige, die die
    Quelle hergab, verliert eine korrekte Persona ihren Beruf.
    """
    assert "healthcare" not in _domains_in(text)


def test_a_manufacturing_persona_keeps_its_profession_next_to_a_station():
    source = "Rollout an den Ladestationen der Werkhalle, Fertigung betroffen."

    result = detect_domain_drift("Anlagenführer in der Montage", source)
    assert result.drifted == []
    assert result.unverifiable is False


# --- Neue Domänen (#1471) ----------------------------------------------------


def test_an_it_security_marker_fires_without_matching_workplace_safety():
    """"Sicherheit" allein ist zu generisch — nur volle Komposita zählen."""
    assert "it/security" in _domains_in(
        "Zuständig für Cyberangriffe und Firewall-Härtung im Rechenzentrum."
    )
    assert "it/security" not in _domains_in(
        "Verantwortlich für Arbeitssicherheit und Unfallverhütung in der Werkhalle."
    )


def test_a_public_sector_marker_fires_without_matching_property_management():
    """"Verwaltung" allein steckt auch in "Hausverwaltung" — nicht gemeint."""
    assert "public-sector" in _domains_in(
        "Die Kommunalverwaltung bearbeitet den Antrag im Bürgeramt."
    )
    assert "public-sector" not in _domains_in(
        "Die Hausverwaltung kümmert sich um die Nebenkostenabrechnung."
    )


def test_a_retail_marker_fires_without_matching_a_bare_cash_desk():
    """"Kasse" allein wäre zu generisch — nur volle Komposita zählen."""
    assert "retail" in _domains_in(
        "Leitet die Filialleitung und plant die Sortimentsplanung für den Einzelhandel."
    )
    assert "retail" not in _domains_in(
        "Zahlt an der Kasse und wartet auf die Quittung."
    )


def test_a_media_marker_fires_without_matching_a_chemical_reaction():
    """"Redaktion" und "Reaktion" unterscheiden sich um ein "d" — keine Kollision."""
    assert "media" in _domains_in(
        "Die Redaktionsleitung verantwortet die Berichterstattung und Pressemitteilungen."
    )
    assert "media" not in _domains_in("Die chemische Reaktion verläuft exotherm.")


def test_a_legal_marker_fires_without_matching_spelling_conventions():
    """"Recht" allein steckt auch in "Rechtschreibung" — nicht gemeint."""
    assert "legal" in _domains_in(
        "Die Rechtsabteilung der Anwaltskanzlei übernimmt die Prozessvertretung."
    )
    assert "legal" not in _domains_in(
        "Die Rechtschreibung wird regelmäßig überprüft."
    )


def test_a_legal_marker_does_not_fire_on_a_commander_or_a_federal_chancellery():
    """"mandant" steckt in "Kommandant", "kanzlei" in "Bundeskanzlei".

    Beides sind reale DACH-Berufs- beziehungsweise Behördenbezeichnungen
    ohne juristischen Bezug. Griffe der Marker dort, meldete
    ``detect_domain_drift`` einen `legal`-Drift, und der produktive
    Aufrufer setzt bei Drift ``profession=None`` — ein Kommandant verlöre
    also seinen Beruf. Deshalb tragen beide Marker nur ihre eindeutige
    Langform (Codex-Finding, PR #1540).
    """
    assert "legal" not in _domains_in(
        "Der Kommandant der Einheit koordiniert den Einsatz."
    )
    assert "legal" not in _domains_in(
        "Die Kommandantin leitet die Übung."
    )
    assert "legal" not in _domains_in(
        "Die Bundeskanzlei koordiniert die Geschäfte der Verwaltung."
    )
    # Die Langformen greifen weiterhin.
    assert "legal" in _domains_in("Die Mandantschaft wird umfassend beraten.")
    assert "legal" in _domains_in("Die Anwaltskanzlei vertritt den Fall.")


def test_an_energy_marker_fires_without_matching_a_delivery_driver():
    """"Kraft" allein steckt auch in "Kraftfahrer" — nicht gemeint."""
    assert "energy" in _domains_in(
        "Der Netzbetreiber treibt den Netzausbau für die Energiewende voran."
    )
    assert "energy" not in _domains_in(
        "Der Kraftfahrer liefert die Pakete pünktlich aus."
    )


# --- Zusammengefasste Befunde -----------------------------------------------


def test_a_hospital_network_materialised_as_a_person_is_reported():
    """Das Akzeptanzkriterium aus der Spezifikation."""
    findings = coherence_findings(
        entity_type="HospitalNetwork",
        entity_name="Städtischer Klinikverbund Falkenbrück",
        persona_kind="individual",
        profession="Pflegedienstleitung",
        persona_text="Leitet die Pflege im Klinikum.",
        source_text=CLINIC_SOURCE,
    )

    assert [finding["kind"] for finding in findings] == [
        "collective_materialised_as_individual"
    ]


def test_a_collective_kind_on_a_collective_type_is_clean():
    assert (
        coherence_findings(
            entity_type="HospitalNetwork",
            entity_name="Städtischer Klinikverbund Falkenbrück",
            persona_kind="collective",
            source_text=CLINIC_SOURCE,
        )
        == []
    )


def test_both_findings_can_appear_at_once():
    findings = coherence_findings(
        entity_type="PatientAdvisoryCouncil",
        entity_name="Patientenbeirat",
        persona_kind="individual",
        profession="Schichtleiter Maschinenbau",
        persona_text="Verantwortet die Produktionsleitung.",
        source_text=CLINIC_SOURCE,
    )

    assert {finding["kind"] for finding in findings} == {
        "collective_materialised_as_individual",
        "domain_drift",
    }


def test_a_coherent_individual_persona_produces_no_findings():
    assert (
        coherence_findings(
            entity_type="Person",
            entity_name="Dr. Marlene Krug",
            persona_kind="individual",
            profession="Oberärztin der Notaufnahme",
            persona_text="Arbeitet seit acht Jahren in der Notaufnahme.",
            source_text=CLINIC_SOURCE,
        )
        == []
    )
