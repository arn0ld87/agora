"""Tests für entity_alias_resolution.resolve_aliases (Issue #1470, Slice 4.2).

Abgedeckte Szenarien:
  1  BFW-Trio → 1 Cluster (Klammer-Expansion + Token-Teilmenge transitiv)
  2  Vogt-Trio (Dr. Miriam Vogt / Vogt[Person] / Vogt[Executive]) → 1 Cluster
  3  Seifert-Paar (Claudia Seifert / Seifert) → 1 Cluster, kanonisch der Vollname
  4  Zwei verschiedene Vogts + „Vogt" → „Vogt" bleibt getrennt (mehrdeutig)
  5  Person- und Organisations-Entität gleichen Namens werden nicht gemergt
  6  Kein Merge bei nicht-persona-fähigen Klassen (je Klasse getrennt)

Integration (über _phase_read_entities):
  7  Technische Entitäten belegen keinen Cap-Platz
  8  BFW-Varianten → 1 Persona-Kandidat nach Phase 1
"""

from __future__ import annotations

from typing import List


from app.services.entity_alias_resolution import resolve_aliases
from app.services.entity_reader import EntityNode


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------


def _entity(
    name: str,
    entity_type: str = "Organization",
    uuid: str | None = None,
    summary: str = "",
) -> EntityNode:
    return EntityNode(
        uuid=uuid or f"uuid-{name}-{entity_type}",
        name=name,
        labels=["Entity", entity_type],
        summary=summary,
        attributes={},
    )


def _names(entities: List[EntityNode]) -> List[str]:
    return [e.name for e in entities]


# ---------------------------------------------------------------------------
# 1. BFW-Trio
# ---------------------------------------------------------------------------


class TestBFWCluster:
    def test_bfw_trio_bildet_einen_cluster(self) -> None:
        """BFW, BFW Leipzig und Berufsförderungswerk Leipzig (BFW Leipzig)
        sollen zu einer einzigen Entität zusammengefasst werden."""
        entities = [
            _entity("BFW", "Organization"),
            _entity("BFW Leipzig", "Organization"),
            _entity(
                "Berufsförderungswerk Leipzig (BFW Leipzig)", "Organization"
            ),
        ]
        result = resolve_aliases(entities)

        assert len(result) == 1, f"Erwartet 1 Entität, erhalten {len(result)}: {_names(result)}"

    def test_bfw_kanonischer_name_ist_der_laengste(self) -> None:
        entities = [
            _entity("BFW", "Organization"),
            _entity("BFW Leipzig", "Organization"),
            _entity(
                "Berufsförderungswerk Leipzig (BFW Leipzig)", "Organization"
            ),
        ]
        result = resolve_aliases(entities)

        assert result[0].name == "Berufsförderungswerk Leipzig (BFW Leipzig)"

    def test_bfw_aliase_sind_gespeichert(self) -> None:
        entities = [
            _entity("BFW", "Organization"),
            _entity("BFW Leipzig", "Organization"),
            _entity(
                "Berufsförderungswerk Leipzig (BFW Leipzig)", "Organization"
            ),
        ]
        result = resolve_aliases(entities)

        aliases = result[0].attributes.get("_agora_aliases", [])
        assert len(aliases) == 2, f"Erwartet 2 Aliase, erhalten {len(aliases)}"


# ---------------------------------------------------------------------------
# 2. Vogt-Trio
# ---------------------------------------------------------------------------


class TestVogtCluster:
    def test_vogt_trio_bildet_einen_cluster(self) -> None:
        """Dr. Miriam Vogt, Vogt (Person) und Vogt (Executive) sollen zu
        einer Persona zusammengefasst werden."""
        entities = [
            _entity("Dr. Miriam Vogt", "Person"),
            _entity("Vogt", "Person"),
            _entity("Vogt", "Executive", uuid="uuid-Vogt-Executive"),
        ]
        result = resolve_aliases(entities)

        assert len(result) == 1, (
            f"Erwartet 1 Entität, erhalten {len(result)}: {_names(result)}"
        )

    def test_vogt_kanonischer_name_ist_vollname(self) -> None:
        entities = [
            _entity("Dr. Miriam Vogt", "Person"),
            _entity("Vogt", "Person"),
            _entity("Vogt", "Executive", uuid="uuid-Vogt-Executive"),
        ]
        result = resolve_aliases(entities)

        assert result[0].name == "Dr. Miriam Vogt"


# ---------------------------------------------------------------------------
# 3. Seifert-Paar
# ---------------------------------------------------------------------------


class TestSeifertCluster:
    def test_seifert_paar_bildet_einen_cluster(self) -> None:
        entities = [
            _entity("Claudia Seifert", "Employee"),
            _entity("Seifert", "Manager"),
        ]
        result = resolve_aliases(entities)

        assert len(result) == 1, (
            f"Erwartet 1 Entität, erhalten {len(result)}: {_names(result)}"
        )

    def test_seifert_kanonischer_name_ist_vollname(self) -> None:
        entities = [
            _entity("Claudia Seifert", "Employee"),
            _entity("Seifert", "Manager"),
        ]
        result = resolve_aliases(entities)

        assert result[0].name == "Claudia Seifert"


# ---------------------------------------------------------------------------
# 4. Mehrdeutige Nachnamen bleiben getrennt
# ---------------------------------------------------------------------------


class TestMehrdeutigerNachname:
    def test_zwei_verschiedene_vogts_und_kurzname_bleiben_getrennt(self) -> None:
        """„Vogt" (Nachname allein) bleibt eine eigene Entität, wenn zwei
        Personen diesen Nachnamen tragen — sonst Zuordnungsfehler."""
        entities = [
            _entity("Miriam Vogt", "Person", uuid="uuid-miriam"),
            _entity("Thomas Vogt", "Person", uuid="uuid-thomas"),
            _entity("Vogt", "Person", uuid="uuid-vogt-alone"),
        ]
        result = resolve_aliases(entities)

        # Miriam und Thomas sind unterschiedliche Personen; „Vogt" ist mehrdeutig
        assert len(result) == 3, (
            f"Erwartet 3 Entitäten (mehrdeutig), erhalten {len(result)}: {_names(result)}"
        )


# ---------------------------------------------------------------------------
# 5. Kein Merge über Klassen hinweg
# ---------------------------------------------------------------------------


class TestKeinMergeUeberKlassen:
    def test_person_und_organisation_gleichen_namens_bleiben_getrennt(
        self,
    ) -> None:
        """Eine Person „Meier" und eine Organisation „Meier GmbH" dürfen
        trotz ähnlichem Namen nicht zusammengefasst werden — sie gehören
        verschiedenen semantischen Klassen an."""
        entities = [
            _entity("Meier", "Person"),
            _entity("Meier GmbH", "Organization"),
        ]
        result = resolve_aliases(entities)

        assert len(result) == 2, (
            f"Erwartet 2 Entitäten (verschiedene Klassen), erhalten {len(result)}"
        )

    def test_person_executive_gleicher_name_werden_gemergt(self) -> None:
        """Person und Executive gehören beide zur Klasse PERSON — gleicher
        normierter Name → ein Cluster."""
        entities = [
            _entity("Schmidt", "Person"),
            _entity("Schmidt", "Executive", uuid="uuid-Schmidt-Exec"),
        ]
        result = resolve_aliases(entities)

        assert len(result) == 1, (
            f"Erwartet 1 Entität (Person+Executive gleicher Name), erhalten {len(result)}"
        )


# ---------------------------------------------------------------------------
# 6. Leere Liste
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_leere_liste_bleibt_leer(self) -> None:
        assert resolve_aliases([]) == []

    def test_einzelne_entitaet_wird_unveraendert_zurueckgegeben(self) -> None:
        e = _entity("Mustermann", "Person")
        result = resolve_aliases([e])
        assert len(result) == 1
        assert result[0].name == "Mustermann"

    def test_aliases_erhalten_summary_der_zusammengefuehrten_entitaet(
        self,
    ) -> None:
        """Summaries der Alias-Entitäten sollen nicht verloren gehen."""
        entities = [
            _entity("Claudia Seifert", "Employee", summary="Teamleiterin"),
            _entity("Seifert", "Manager", summary="Bereichsverantwortliche"),
        ]
        result = resolve_aliases(entities)

        alias_summaries = result[0].attributes.get("_agora_alias_summaries", [])
        assert len(alias_summaries) >= 1, (
            "Summary des Alias-Eintrags soll erhalten bleiben"
        )

    def test_mehrdeutige_kurzform_bei_organisationen_bleibt_getrennt(
        self,
    ) -> None:
        """„BFW" wäre ein Alias zu mehr als einer Organisation
        → mehrdeutig → getrennt lassen."""
        entities = [
            _entity("BFW", "Organization"),
            _entity("BFW Leipzig", "Organization"),
            _entity("BFW München", "Organization"),
        ]
        # „BFW" ist Teilmenge von BEIDEN längeren → mehrdeutig → bleibt separat
        result = resolve_aliases(entities)

        # BFW Leipzig und BFW München haben keinen gemeinsamen Alias → getrennt
        # BFW hat zwei Superset-Kandidaten → nicht gemergt
        assert len(result) == 3, (
            f"Erwartet 3 Entitäten (mehrdeutige Kurzform), erhalten {len(result)}: "
            f"{_names(result)}"
        )


# ---------------------------------------------------------------------------
# Integration über _phase_read_entities (Lead-Review)
# ---------------------------------------------------------------------------


def test_phase_read_entities_loest_aliase_auf_und_haelt_technik_aus_dem_cap(monkeypatch):
    """Abnahme #1470: ein BFW-Akteur, ein Vogt, Technik ohne LLM-Call raus."""
    import types
    from unittest.mock import MagicMock

    from app.services import prepare_service as ps_mod
    from app.services.entity_reader import EntityNode, FilteredEntities

    def node(name: str, entity_type: str) -> EntityNode:
        return EntityNode(
            uuid=f"uuid-{name}", name=name, labels=["Entity", entity_type],
            summary="", attributes={},
        )

    pool = [
        node("BFW", "Organization"),
        node("BFW Leipzig", "Organization"),
        node("Berufsförderungswerk Leipzig (BFW Leipzig)", "Organization"),
        node("Dr. Miriam Vogt", "Person"),
        node("Vogt", "Person"),
        node("Vogt", "Executive"),
        node("Vektordatenbank", "TechnologyProvider"),
        node("RAG-Architektur", "Organization"),
        node("zentrale Authentifizierung", "Organization"),
        node("Pflegekräfte", "EmployeeGroup"),
    ]
    reader = MagicMock()
    reader.filter_defined_entities.return_value = FilteredEntities(
        entities=list(pool),
        entity_types={"Organization", "Person", "Executive", "TechnologyProvider", "EmployeeGroup"},
        total_count=len(pool),
        filtered_count=len(pool),
    )
    monkeypatch.setattr(ps_mod, "EntityReader", lambda _storage: reader)

    state = types.SimpleNamespace(graph_id="graph_1", entities_count=0, entity_types=[])
    result = ps_mod._phase_read_entities(
        state, storage=MagicMock(), defined_entity_types=None, max_agents=3,
    )

    names = sorted(e.name for e in result.entities)
    assert names == sorted([
        "Berufsförderungswerk Leipzig (BFW Leipzig)",
        "Dr. Miriam Vogt",
        "Pflegekräfte",
    ])


# ---------------------------------------------------------------------------
# Codex-Review PR #1606
# ---------------------------------------------------------------------------


def _node(name: str, entity_type: str, **extra):
    from app.services.entity_reader import EntityNode

    return EntityNode(
        uuid=f"uuid-{name}-{entity_type}", name=name, labels=["Entity", entity_type],
        summary="", attributes={}, **extra,
    )


def test_merge_behaelt_den_graph_kontext_der_aliase():
    """P1: Fakten, die nur am Alias hängen, gehen nicht verloren."""
    from app.services.entity_alias_resolution import resolve_aliases

    full = _node(
        "Dr. Miriam Vogt", "Person",
        related_edges=[{"edge_name": "LEITET", "fact": "Vogt leitet das Projekt"}],
        related_nodes=[{"uuid": "uuid-projekt", "name": "Projekt"}],
    )
    alias = _node(
        "Vogt", "Executive",
        related_edges=[
            {"edge_name": "LEITET", "fact": "Vogt leitet das Projekt"},
            {"edge_name": "LEHNT_AB", "fact": "Vogt lehnt den Vollstart ab"},
        ],
        related_nodes=[
            {"uuid": "uuid-Dr. Miriam Vogt-Person", "name": "Dr. Miriam Vogt"},
            {"uuid": "uuid-klinik", "name": "Klinik"},
        ],
    )
    [merged] = resolve_aliases([full, alias])

    facts = [edge["fact"] for edge in merged.related_edges]
    assert facts == ["Vogt leitet das Projekt", "Vogt lehnt den Vollstart ab"]
    assert [node["uuid"] for node in merged.related_nodes] == ["uuid-projekt", "uuid-klinik"]


def test_ausgabe_folgt_der_ersten_nennung_nicht_der_klasse():
    """P2: Der Cap vergibt Plätze nach erster Nennung."""
    from app.services.entity_alias_resolution import resolve_aliases

    entities = [
        _node("Dr. Miriam Vogt", "Person"),
        _node("Nexora GmbH", "Organization"),
        _node("Vogt", "Executive"),
        _node("Thomas Brandt", "Person"),
    ]
    assert [e.name for e in resolve_aliases(entities)] == [
        "Dr. Miriam Vogt", "Nexora GmbH", "Thomas Brandt",
    ]


def test_vorschau_zaehlt_aliase_nur_einmal(monkeypatch):
    """P2: Vorschau und Laufpfad liefern dieselbe Personazahl."""
    import types
    from unittest.mock import MagicMock

    from app.api import simulation_prepare as mod
    from app.services.entity_reader import FilteredEntities

    pool = [
        _node("BFW", "Organization"),
        _node("BFW Leipzig", "Organization"),
        _node("Berufsförderungswerk Leipzig (BFW Leipzig)", "Organization"),
        _node("Dr. Miriam Vogt", "Person"),
    ]
    reader = MagicMock()
    reader.filter_defined_entities.return_value = FilteredEntities(
        entities=list(pool), entity_types={"Organization", "Person"},
        total_count=len(pool), filtered_count=len(pool),
    )
    monkeypatch.setattr(mod, "EntityReader", lambda _storage: reader)
    state = types.SimpleNamespace(graph_id="graph_1", entities_count=0, entity_types=[])
    inputs = types.SimpleNamespace(entity_types=None, max_agents=None)

    mod._preview_entity_counts(state, MagicMock(), inputs)

    assert state.entities_count == 2
