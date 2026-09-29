"""Issue #1713/#1470 — Person und ihre Organisation werden zu einem Agenten.

Bisher liefen eine Person und die Organisation, die sie laut Graph-Relation
vertritt (z. B. ``WORKS_FOR``, ``REPRESENTS``), als zwei getrennte Agenten.
Das erzeugte in der Role-Leakage-Erkennung die Folgemeldung
``unmatched_self_reference``, sobald die Person-Persona im Simulationstext
„wir, <Organisation>" schrieb, ohne dass irgendeine Persona diese
Organisation als eigene Rolle trug.

Regel (Maintainer-Entscheidung, Issue #1713):

- Vertritt genau eine Person die Organisation, bleibt die Person der Agent;
  die Organisation wird nicht zusätzlich geführt. Die Person trägt die
  Organisation als ``affiliation``.
- Vertreten mehrere Personen dieselbe Organisation (kollektiver Akteur)
  oder keine, bleibt die Organisation ein eigener Agent.
- Eine Zusammenlegung wird immer sichtbar protokolliert (Degradation +
  strukturiertes Log), nie still.
"""

from __future__ import annotations

import pytest

from app.contracts.pipeline_degradation_contract import DegradationKind
from app.services.degradation_collector import DegradationCollector
from app.services.entity_reader import EntityNode
from app.services.prepare_entities import _merge_persons_with_organizations


def _entity(
    name: str,
    entity_type: str,
    *,
    uuid: str | None = None,
    related_edges: list[dict] | None = None,
) -> EntityNode:
    return EntityNode(
        uuid=uuid or f"uuid-{name}-{entity_type}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
        related_edges=related_edges or [],
    )


def _represents_edge(target_uuid: str, edge_name: str = "WORKS_FOR") -> dict:
    return {
        "direction": "outgoing",
        "edge_name": edge_name,
        "fact": "",
        "target_node_uuid": target_uuid,
    }


class TestEinePersonVertrittEineOrganisation:
    def test_organisation_wird_zum_agenten_der_person(self) -> None:
        org = _entity("Berufsförderungswerk Leipzig", "Organization")
        person = _entity(
            "Miriam Vogt",
            "Official",
            related_edges=[_represents_edge(org.uuid)],
        )

        result = _merge_persons_with_organizations([person, org])

        assert [e.uuid for e in result] == [person.uuid]
        assert person.affiliation == "Berufsförderungswerk Leipzig"

    def test_protokolliert_die_zusammenlegung_als_degradation(self) -> None:
        org = _entity("BFW Leipzig", "Organization")
        person = _entity(
            "Miriam Vogt",
            "Official",
            related_edges=[_represents_edge(org.uuid, "REPRESENTS")],
        )
        degradations = DegradationCollector()

        _merge_persons_with_organizations([person, org], degradations=degradations)

        report = degradations.report()
        kinds = [event.kind for event in report.events]
        assert DegradationKind.PERSON_REPRESENTS_ORGANIZATION_MERGED in kinds


class TestOrganisationOhneVertreterinBleibtEigenerAgent:
    def test_keine_relation_keine_zusammenlegung(self) -> None:
        org = _entity("Stadtverwaltung Leipzig", "Organization")
        person = _entity("Jens Weber", "Official", related_edges=[])

        result = _merge_persons_with_organizations([person, org])

        assert {e.uuid for e in result} == {person.uuid, org.uuid}
        assert person.affiliation is None

    def test_aehnlicher_name_ohne_relation_loest_keine_zusammenlegung_aus(self) -> None:
        """Reine Namensähnlichkeit ist keine belegte Graph-Relation — die
        Zusammenlegung darf sich nicht auf eine Namensheuristik stützen."""
        org = _entity("Berufsförderungswerk Leipzig", "Organization")
        person = _entity("Berufsförderungswerk Leipzig e.V.", "Official", related_edges=[])

        result = _merge_persons_with_organizations([person, org])

        assert {e.uuid for e in result} == {person.uuid, org.uuid}
        assert person.affiliation is None


class TestOrganisationMitZweiVertreternBleibtKollektiverAkteur:
    def test_beide_personen_tragen_affiliation_organisation_bleibt(self) -> None:
        org = _entity("Betriebsrat Nordharz", "Organization")
        person_a = _entity(
            "Anna Muster",
            "Official",
            related_edges=[_represents_edge(org.uuid)],
        )
        person_b = _entity(
            "Ben Muster",
            "Official",
            related_edges=[_represents_edge(org.uuid, "REPRESENTS")],
        )

        result = _merge_persons_with_organizations([person_a, person_b, org])

        assert {e.uuid for e in result} == {person_a.uuid, person_b.uuid, org.uuid}
        assert person_a.affiliation == "Betriebsrat Nordharz"
        assert person_b.affiliation == "Betriebsrat Nordharz"


class TestUnbeteiligteEntitaetenBleibenUnveraendert:
    def test_ohne_person_organisation_kandidaten_unveraendert(self) -> None:
        entities = [_entity("Digitaler Zwilling", "Concept")]

        result = _merge_persons_with_organizations(entities)

        assert result == entities

    def test_leere_liste(self) -> None:
        assert _merge_persons_with_organizations([]) == []

    @pytest.mark.parametrize("edge_name", ["studies_at", "reports_on", "supports"])
    def test_nicht_repraesentierende_relationstypen_loesen_keinen_merge_aus(
        self, edge_name: str
    ) -> None:
        org = _entity("Universität Leipzig", "University")
        person = _entity(
            "Jens Weber",
            "Student",
            related_edges=[_represents_edge(org.uuid, edge_name)],
        )

        result = _merge_persons_with_organizations([person, org])

        assert {e.uuid for e in result} == {person.uuid, org.uuid}
        assert person.affiliation is None
