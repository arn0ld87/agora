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
    ) == ["manufacturing"]


def test_a_clerk_in_production_planning_is_drift():
    assert detect_domain_drift(
        "Sachbearbeiterin in der Fertigungsplanung", CLINIC_SOURCE
    ) == ["manufacturing"]


def test_a_role_from_the_source_domain_is_no_drift():
    assert detect_domain_drift("Pflegekraft in der Nachtschicht", CLINIC_SOURCE) == []


def test_a_persona_spanning_both_domains_is_no_drift():
    """Eine Schnittstelle ist kein Drift.

    Wer Medizintechnik in der Klinik betreut, trägt zu Recht Vokabular aus
    beiden Fächern.
    """
    assert (
        detect_domain_drift(
            "Instandhaltung der Medizintechnik im Klinikum", CLINIC_SOURCE
        )
        == []
    )


def test_a_neutral_role_is_no_drift():
    """Ohne Fachvokabular gibt es nichts zu beanstanden."""
    assert detect_domain_drift("Mitarbeiterin der Verwaltung", CLINIC_SOURCE) == []


def test_a_source_without_a_domain_cannot_accuse_anyone():
    assert detect_domain_drift("Schichtleiter Maschinenbau", "Ein Projekt startet.") == []


def test_a_network_in_the_source_is_not_read_as_manufacturing():
    """"Netzwerk" enthält "werk" — ein kurzer Marker hätte hier zugeschlagen."""
    assert detect_domain_drift("Betreuer im Klinik-Netzwerk", CLINIC_SOURCE) == []


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
