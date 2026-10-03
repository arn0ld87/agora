"""Issue #1713/#1470 — Person und ihre Organisation werden zu einem Agenten.

Bisher liefen eine Person und die Organisation, die sie laut Graph-Relation
vertritt (``REPRESENTS``), als zwei getrennte Agenten.
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
from app.services.prepare_entities import (
    _merge_entity_variants,
    _merge_persons_with_organizations,
)


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


def _represents_edge(target_uuid: str, edge_name: str = "REPRESENTS") -> dict:
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


class TestZugehoerigkeitIstKeineVertretung:
    @pytest.mark.parametrize("edge_name", ["WORKS_FOR", "AFFILIATED_WITH", "works_for"])
    def test_arbeitet_fuer_ersetzt_die_organisation_nicht(self, edge_name: str) -> None:
        """Eine Betriebsrätin, die für die Klinik arbeitet, spricht nicht für
        die Klinik. Nur REPRESENTS belegt Vertretung."""
        org = _entity("Kliniken Hollerau gGmbH", "Organization")
        person = _entity(
            "Anke Wübbena",
            "Person",
            related_edges=[_represents_edge(org.uuid, edge_name)],
        )

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


# ------------------------------------------------------- #1759 (A4)


class TestLeadsBelegtVertretung:
    """Eine LEADS-Kante belegt Vertretung genauso wie REPRESENTS (#1759 A4)."""

    def test_leads_kante_legt_person_und_organisation_zusammen(self) -> None:
        """Exaktbefund aus dem Lauf: Detlef Brunn ist der im Dokument genannte
        Vorsitzende des Betriebsrats Kliniken Hollerau — mit belegter Kante
        bleibt Brunn der Agent, der Betriebsrat belegt keinen eigenen Platz."""
        org = _entity("Betriebsrat Kliniken Hollerau", "Organization")
        brunn = _entity(
            "Detlef Brunn",
            "Person",
            related_edges=[_represents_edge(org.uuid, "LEADS")],
        )

        result = _merge_persons_with_organizations([brunn, org])

        assert [e.uuid for e in result] == [brunn.uuid]
        assert brunn.affiliation == "Betriebsrat Kliniken Hollerau"


class TestEntityVariantenVorDerAuswahl:
    """Doppelbesetzte Persona-Plätze durch Namensvarianten (#1759 A4)."""

    @pytest.fixture(autouse=True)
    def _caplog_an_agora_prepare_entities(self, caplog: pytest.LogCaptureFixture):
        """``setup_logger()`` setzt propagate=False auf agora.*-Loggern; caplog
        hängt am Root-Logger und sähe die Records sonst nicht (Repo-Muster,
        siehe ``test_jobs_enqueue.py``)."""
        import logging

        entity_logger = logging.getLogger("agora.prepare_entities")
        entity_logger.addHandler(caplog.handler)
        original_level = entity_logger.level
        entity_logger.setLevel(logging.DEBUG)
        yield
        entity_logger.removeHandler(caplog.handler)
        entity_logger.setLevel(original_level)

    def test_hebammenverband_und_kreisvertretung_werden_ein_agent(self) -> None:
        kurz = _entity("Hebammenverband", "Organization")
        lang = _entity("Hebammenverband, Kreisvertretung Hollerau", "Organization")

        result = _merge_entity_variants([kurz, lang])

        assert [e.uuid for e in result] == [lang.uuid]
        assert kurz.name in lang.attributes.get("_agora_aliases", [])

    def test_rettungsdienst_flexionsvariante_wird_ein_agent(self) -> None:
        """„Rettungsdienst des Landkreises“ und „Rettungsdienst Landkreis
        Hollerau“ unterscheiden sich nur durch Artikel und Genitiv-s."""
        flexion = _entity("Rettungsdienst des Landkreises", "Organization")
        voll = _entity("Rettungsdienst Landkreis Hollerau", "Organization")

        result = _merge_entity_variants([flexion, voll])

        assert [e.uuid for e in result] == [voll.uuid]

    def test_geschaeftsfuehrung_geht_in_die_organisation_auf(self) -> None:
        """Ein Org-Anhang, der die Organisation eindeutig benennt, ist kein
        eigener Agent („Kliniken Hollerau gGmbH“ vs. deren „Geschäftsführung“)."""
        org = _entity("Kliniken Hollerau gGmbH", "Organization")
        organ = _entity(
            "Geschäftsführung der Kliniken Hollerau gGmbH", "Organization"
        )

        result = _merge_entity_variants([org, organ])

        assert [e.uuid for e in result] == [org.uuid]

    def test_organ_ohne_eindeutigen_bezug_bleibt_eigener_agent(self) -> None:
        """„Geschäftsführung“ pur nennt keine Organisation — ohne eindeutigen
        Bezug wird nicht gemerged (im Zweifel keine Fusion)."""
        org_a = _entity("Kliniken Hollerau gGmbH", "Organization")
        org_b = _entity("Klinikum Südstadt gGmbH", "Organization")
        organ = _entity("Geschäftsführung", "Organization")

        result = _merge_entity_variants([org_a, org_b, organ])

        assert {e.uuid for e in result} == {org_a.uuid, org_b.uuid, organ.uuid}

    def test_attribute_der_zusammengefuehrten_entitaet_bleiben_erhalten(self) -> None:
        kurz = _entity("Hebammenverband", "Organization")
        kurz.attributes = {"stance": "kritisch", "summary_source": "doc-7"}
        kurz.summary = "Interessenvertretung der Hebammen."
        lang = _entity("Hebammenverband, Kreisvertretung Hollerau", "Organization")
        lang.attributes = {"position": "aktiv"}
        lang.summary = ""

        result = _merge_entity_variants([kurz, lang])

        assert len(result) == 1
        survivor = result[0]
        assert survivor.attributes["position"] == "aktiv"
        assert survivor.attributes["stance"] == "kritisch"
        assert survivor.attributes["summary_source"] == "doc-7"
        assert survivor.summary == "Interessenvertretung der Hebammen."

    def test_attribut_konflikt_wird_dokumentiert_und_survivor_behaelt_seinen_wert(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        kurz = _entity("Hebammenverband", "Organization")
        kurz.attributes = {"stance": "kritisch"}
        lang = _entity("Hebammenverband, Kreisvertretung Hollerau", "Organization")
        lang.attributes = {"stance": "aktiv"}

        with caplog.at_level(logging.INFO, logger="agora.prepare_entities"):
            result = _merge_entity_variants([kurz, lang])

        assert len(result) == 1
        assert result[0].attributes["stance"] == "aktiv"
        meldungen = [r.getMessage() for r in caplog.records]
        assert any("stance" in m for m in meldungen)

    def test_person_und_organisation_ohne_kante_werden_nicht_per_name_gefuehrt(
        self
    ) -> None:
        """Dokumentierter Nicht-Griff aus dem Referenzlauf: Der Betriebsrat
        und Detlef Brunn blieben getrennt, weil der Graph keine belegte
        Vertretungs-Kante zwischen ihnen enthält. Eine Namensheuristik ist
        bewusst ausgeschlossen (siehe
        ``TestOrganisationOhneVertreterinBleibtEigenerAgent``)."""
        org = _entity("Betriebsrat Kliniken Hollerau", "Organization")
        brunn = _entity("Detlef Brunn", "Person")

        variants = _merge_entity_variants([brunn, org])
        merged = _merge_persons_with_organizations(variants)

        assert {e.uuid for e in merged} == {brunn.uuid, org.uuid}

    def test_unbeteiligte_personen_bleiben_unveraendert(self) -> None:
        person = _entity("Detlef Brunn", "Person")
        andere = _entity("Mia Weber", "Person")

        result = _merge_entity_variants([person, andere])

        assert {e.uuid for e in result} == {person.uuid, andere.uuid}
