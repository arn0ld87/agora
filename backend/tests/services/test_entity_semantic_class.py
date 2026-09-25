"""Tests für entity_semantic_class.classify_entity (Issue #1470, Slice 4.3).

Abgedeckte Szenarien:
  - Technische Artefakte mit uneindeutigem Typ (TechnologyProvider / Organization)
    → TECHNOLOGY, kein LLM-Aufruf
  - Echter Firmenname mit Rechtsformendung (GmbH, AG, SE …) → ORGANIZATION
  - Person- und Executive-Typen → PERSON
  - Kollektive Typen → POPULATION
  - Location-Typen → LOCATION
  - Concept-Typen → CONCEPT
  - Unbekannte Typen → OTHER (konservativ)
"""

from __future__ import annotations

import pytest

from app.contracts.entity_semantic_class_contract import SemanticEntityClass
from app.services.entity_semantic_class import classify_entity


class TestTechnicalEntities:
    """Technische Artefakte dürfen keinen Persona-Pool-Platz belegen."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            # Kernfälle aus dem Issue
            ("Vektordatenbank", "TechnologyProvider"),
            ("Vektordatenbank", "Organization"),
            ("zentrale Authentifizierung", "TechnologyProvider"),
            ("zentrale Authentifizierung", "Organization"),
            ("RAG-Architektur", "TechnologyProvider"),
            ("RAG-Architektur", "Organization"),
            # Weitere technische Namen
            ("KI-Plattform", "Organization"),
            ("Microservices-Infrastruktur", "Organization"),
            ("REST-API", "Organization"),
            ("LLM-Pipeline", "TechnologyProvider"),
            # Explizit technischer Typ
            ("Agentensystem", "Software"),
            ("LernPlattform", "Platform"),
            ("DataWarehouse", "Database"),
        ],
    )
    def test_technische_entitaet_wird_als_technology_klassifiziert(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.TECHNOLOGY, (
            f"'{name}' (Typ: {entity_type!r}) sollte TECHNOLOGY sein, ist aber {result!r}"
        )


class TestOrganizationEntities:
    """Echte Firmennamen mit Rechtsformendung bleiben ORGANIZATION."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            ("Nexora GmbH", "Organization"),
            ("SAP SE", "Company"),
            ("Datenbank-Consult GmbH", "Organization"),
            ("Plattform AG", "Organization"),
            # Kein technischer Kopf nach Rechtsformendung
            ("System Solutions AG", "Organization"),
            # BFW-Varianten
            ("BFW", "Organization"),
            ("BFW Leipzig", "Organization"),
            ("Berufsförderungswerk Leipzig", "Organization"),
            # Provider-Typ (ohne tech. Namen)
            ("Agora Solutions", "TechnologyProvider"),
        ],
    )
    def test_echter_firmenname_bleibt_organization(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.ORGANIZATION, (
            f"'{name}' (Typ: {entity_type!r}) sollte ORGANIZATION sein, ist aber {result!r}"
        )


class TestPersonEntities:
    """Person- und Executive-Typen → PERSON."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            ("Dr. Miriam Vogt", "Person"),
            ("Vogt", "Person"),
            ("Vogt", "Executive"),
            ("Claudia Seifert", "Employee"),
            ("Seifert", "Manager"),
            ("Max Mustermann", "Director"),
            ("Anna Beispiel", "ExecutiveDirector"),
        ],
    )
    def test_person_typen_werden_als_person_klassifiziert(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.PERSON, (
            f"'{name}' (Typ: {entity_type!r}) sollte PERSON sein, ist aber {result!r}"
        )


class TestPopulationEntities:
    """Kollektive Typen → POPULATION."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            ("Betriebsrat", "EmployeeGroup"),
            ("Auszubildende", "TraineeGroup"),
            ("Pflegepersonal", "WorkerGroup"),
            ("Ausschuss", "Committee"),
        ],
    )
    def test_kollektive_typen_werden_als_population_klassifiziert(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.POPULATION, (
            f"'{name}' (Typ: {entity_type!r}) sollte POPULATION sein, ist aber {result!r}"
        )


class TestLocationEntities:
    """Geografische Entitäten → LOCATION."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            ("Deutschland", "Country"),
            ("Leipzig", "City"),
            ("Sachsen", "Region"),
        ],
    )
    def test_geografische_typen_werden_als_location_klassifiziert(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.LOCATION, (
            f"'{name}' (Typ: {entity_type!r}) sollte LOCATION sein, ist aber {result!r}"
        )


class TestConceptEntities:
    """Abstrakte Konzepte → CONCEPT."""

    @pytest.mark.parametrize(
        ("name", "entity_type"),
        [
            ("Datenschutz", "Topic"),
            ("Bildungsqualität", "Concept"),
            ("ISO 27001", "Standard"),
            ("DSGVO", "Regulation"),
        ],
    )
    def test_konzept_typen_werden_als_concept_klassifiziert(
        self, name: str, entity_type: str
    ) -> None:
        result = classify_entity(name, entity_type)
        assert result == SemanticEntityClass.CONCEPT, (
            f"'{name}' (Typ: {entity_type!r}) sollte CONCEPT sein, ist aber {result!r}"
        )


class TestUnknownTypes:
    """Unbekannte Typen → OTHER (konservativ erlaubt)."""

    def test_unbekannter_typ_ohne_tech_namen_wird_other(self) -> None:
        result = classify_entity("Agora Werkstatt", "CustomEntity")
        assert result == SemanticEntityClass.OTHER

    def test_leerer_typ_mit_harmlosem_namen_wird_other(self) -> None:
        result = classify_entity("Max Mustermann", "")
        # Ohne Typ kein Person-Kopf → OTHER (konservativ)
        assert result == SemanticEntityClass.OTHER


@pytest.mark.parametrize(
    ("name", "entity_type"),
    [("Stadt Magdeburg", "Stadt"), ("Land Sachsen-Anhalt", "Land")],
)
def test_verwaltungen_mit_ortstyp_bleiben_persona_faehig(name, entity_type):
    """Lead-Review #1470: „Stadt"/„Land" als Typ bezeichnen oft den Akteur."""
    assert classify_entity(name, entity_type) is not SemanticEntityClass.LOCATION
