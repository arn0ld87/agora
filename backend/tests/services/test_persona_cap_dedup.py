"""Issue #1177 — das Persona-Capping verdrängt keine echten Gruppen mehr.

Das `max_agents`-Capping schnitt die Kandidatenliste stumpf ab
(`entities[:max_agents]`), mit der Begründung, der Reader sortiere nach
Grad/Wichtigkeit. Diese Annahme stimmt nicht — weder `filter_defined_entities`
noch der Neo4j-Lesepfad enthalten ein `ORDER BY`. Die Auswahl von 30 aus 102
war damit die unsortierte Rückgabereihenfolge der Query, also willkürlich.

Zwei Folgen, beide im Issue belegt:

1. Mehrfachnennungen derselben Stakeholdergruppe belegten die begrenzten
   Plätze und verdrängten tatsächlich verschiedene Gruppen.
2. Eine überrepräsentierte Gruppe konnte alle Plätze belegen; kleine, aber
   fachlich wichtige Gruppen (`Betriebsrat`, `Honorarkraft`) fielen komplett
   heraus.

**Was diese Tests nicht zusichern:** welcher *einzelne* Vertreter eines Typs
gewinnt. Das bleibt willkürlich, solange der Reader nicht sortiert — eine
Sortierung nach Grad oder Zentralität wäre der nächste Schritt und braucht
eine Änderung im Lesepfad. Zugesichert wird, dass jeder Typ vertreten ist,
solange Plätze reichen.
"""

from __future__ import annotations

import pytest

from app.services.entity_reader import EntityNode
from app.services.prepare_service import (
    _cap_entities_across_types,
    _dedupe_entities,
    _entity_identity_key,
)


def _entity(name: str, entity_type: str = "Stakeholder") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}-{entity_type}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
    )


class TestDedupe:
    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("Betriebsrat", "betriebsrat"),
            ("Betriebsrat", "  Betriebsrat  "),
            ("Junge Familien", "junge   familien"),
        ],
    )
    def test_schreibvarianten_zaehlen_als_eine_gruppe(
        self, first: str, second: str
    ) -> None:
        """Die Ontologie liefert denselben Stakeholder mehrfach in leicht
        abweichender Schreibweise. Roh verglichen belegt jede Variante einen
        eigenen Persona-Platz."""
        unique, removed = _dedupe_entities([_entity(first), _entity(second)])

        assert [e.name for e in unique] == [first], "erste Nennung soll gewinnen"
        assert removed == 1

    def test_gleicher_name_unter_verschiedenen_typen_bleibt_getrennt(self) -> None:
        """Der Bildungsträger als ``Traeger`` und als ``Kostentraeger`` sind
        zwei Rollen — der Typfehler selbst (zweiter Befund in #1177) wird hier
        nicht behoben, aber er darf auch nicht stillschweigend
        wegdedupliziert werden."""
        unique, removed = _dedupe_entities(
            [_entity("Träger", "Traeger"), _entity("Träger", "Kostentraeger")]
        )

        assert len(unique) == 2
        assert removed == 0

    def test_ohne_dubletten_bleibt_die_liste_unveraendert(self) -> None:
        entities = [_entity("Betriebsrat"), _entity("Honorarkraft")]

        unique, removed = _dedupe_entities(entities)

        assert [e.name for e in unique] == ["Betriebsrat", "Honorarkraft"]
        assert removed == 0

    def test_der_schluessel_beruecksichtigt_fehlende_angaben(self) -> None:
        """Ein Knoten ohne eigenen Typ darf nicht crashen — er fällt auf
        ``entity`` zurück."""
        node = EntityNode(uuid="u", name="Ohne Typ", labels=["Entity"], summary="", attributes={})

        assert _entity_identity_key(node) == ("ohne typ", "entity")


class TestCapAcrossTypes:
    def test_eine_ueberrepraesentierte_gruppe_belegt_nicht_alle_plaetze(self) -> None:
        """Der gemeldete Defekt: acht getrennte Stakeholdergruppen, aber die
        erste füllt das Limit allein."""
        entities = [_entity(f"Azubi {i}", "Umschueler") for i in range(10)]
        entities += [_entity("Betriebsrat", "Betriebsrat")]
        entities += [_entity("Honorarkraft", "Honorarkraft")]

        selected = _cap_entities_across_types(entities, 3)

        types = {e.get_entity_type() for e in selected}
        assert types == {"Umschueler", "Betriebsrat", "Honorarkraft"}, (
            f"Kleine Gruppen wurden verdraengt: {types}"
        )

    def test_das_limit_wird_eingehalten(self) -> None:
        entities = [_entity(f"E{i}", f"Typ{i % 4}") for i in range(20)]

        assert len(_cap_entities_across_types(entities, 7)) == 7

    def test_ueberzaehlige_plaetze_gehen_reihum_weiter(self) -> None:
        """Sind mehr Plätze als Typen da, bekommt jeder Typ einen zweiten
        Vertreter, bevor ein dritter vergeben wird."""
        entities = [
            _entity("A1", "A"),
            _entity("A2", "A"),
            _entity("A3", "A"),
            _entity("B1", "B"),
            _entity("B2", "B"),
        ]

        selected = [e.name for e in _cap_entities_across_types(entities, 4)]

        assert selected == ["A1", "B1", "A2", "B2"]

    def test_ein_typ_mit_wenigen_vertretern_blockiert_nicht(self) -> None:
        """Ist ein Typ erschöpft, füllen die übrigen die restlichen Plätze."""
        entities = [_entity("A1", "A"), _entity("B1", "B"), _entity("B2", "B"), _entity("B3", "B")]

        selected = [e.name for e in _cap_entities_across_types(entities, 4)]

        assert sorted(selected) == ["A1", "B1", "B2", "B3"]

    def test_unter_dem_limit_bleibt_alles_erhalten(self) -> None:
        entities = [_entity("A1", "A"), _entity("B1", "B")]

        assert len(_cap_entities_across_types(entities, 10)) == 2

    def test_die_reihenfolge_innerhalb_eines_typs_bleibt_erhalten(self) -> None:
        """Die Quelle ist unsortiert; die Funktion sortiert nicht um, sie
        verteilt nur. Sonst wäre unklar, was sich beim Wechsel zu einem
        sortierenden Reader ändert."""
        entities = [_entity(f"A{i}", "A") for i in range(5)]

        selected = [e.name for e in _cap_entities_across_types(entities, 3)]

        assert selected == ["A0", "A1", "A2"]

    @pytest.mark.parametrize("limit", [0, -1])
    def test_ein_unsinniges_limit_laesst_die_liste_unangetastet(self, limit: int) -> None:
        entities = [_entity("A1", "A")]

        assert _cap_entities_across_types(entities, limit) == entities
