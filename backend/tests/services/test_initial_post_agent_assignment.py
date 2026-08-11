"""Issue #1226 — Initial-Posts dürfen nicht auf einen Agenten kollabieren.

``_assign_initial_post_agents`` indizierte die Agenten ausschließlich über
``entity_type.lower()``, verglich dagegen aber den ``poster_type`` aus der
LLM-Event-Config. Welchen Namensraum dieser Wert trägt, entscheidet das Modell
pro Lauf neu: mal Entity-**Typen** (``management``, ``retrainee``), mal
Entity-**Namen** (``betriebsrat``, ``kostenträger``). Im Namensfall sind beide
Namensräume disjunkt, der Direktabgleich kann strukturell nicht greifen, und
jeder Post fällt in den Fallback.

Der Fallback hatte zwei eigene Fehler: er führte den Rotationszähler nicht mit
(alle Posts landeten auf demselben Agenten) und wählte bei Gleichstand im
``influence_weight`` faktisch nach Listenreihenfolge, also nach der Zufälligkeit
der Persona-Generierung.

Beobachtet in ``sim_54c1c2a6a875``: 9 von 9 Seed-Posts auf ``agent_id=1``
(``IHK``). Der Eröffnungsbeitrag des Betriebsrats, der des Kostenträgers und
der der Teilnehmenden mit Migrationsgeschichte wurden alle von der IHK
gepostet — und landeten unverändert so in der Simulationsdatenbank.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.simulation_config_generator import (
    AgentActivityConfig,
    EventConfig,
    SimulationConfigGenerator,
)


def _agent(
    agent_id: int, name: str, entity_type: str, influence: float = 1.0
) -> AgentActivityConfig:
    return AgentActivityConfig(
        agent_id=agent_id,
        entity_uuid=f"uuid-{agent_id}",
        entity_name=name,
        entity_type=entity_type,
        influence_weight=influence,
    )


@pytest.fixture()
def generator():
    with patch("app.services.simulation_config_generator.LLMClient", MagicMock()):
        yield SimulationConfigGenerator()


def _assign(generator, agents, poster_types):
    event_config = EventConfig(
        initial_posts=[
            {"content": f"Beitrag {i}", "poster_type": ptype}
            for i, ptype in enumerate(poster_types)
        ],
        scheduled_events=[],
        hot_topics=[],
        narrative_direction="",
    )
    result = generator._assign_initial_post_agents(event_config, agents)
    return [post["poster_agent_id"] for post in result.initial_posts]


# Die reale Agentenbasis aus sim_54c1c2a6a875: deutschsprachige Entity-Namen,
# Entity-Typen durchweg ausserhalb der OASIS-Campus-Alias-Tabelle, und drei
# Agenten mit identischem influence_weight=3.0.
_DACH_AGENTS = [
    _agent(1, "IHK", "ChamberOfCommerce", influence=3.0),
    _agent(2, "IHK-Prüfungsausschuss", "ChamberExaminer", influence=3.0),
    _agent(3, "Träger", "TrainingProvider", influence=3.0),
    _agent(4, "Geschäftsführung", "Management", influence=2.0),
    _agent(5, "Dozenten", "Lecturer", influence=1.5),
    _agent(6, "Honorarkräfte", "FreelanceInstructor", influence=1.0),
    _agent(7, "Kostenträger", "FundingAgency", influence=2.5),
    _agent(8, "Betriebsrat", "WorksCouncil", influence=1.5),
    _agent(9, "Aufnehmende Betriebe", "HiringCompany", influence=1.0),
]


def test_poster_type_als_entity_name_trifft_den_namensgleichen_agenten(generator):
    """RED ohne den Fix: alle neun IDs sind identisch (der IHK-Agent)."""
    poster_types = [
        "geschäftsführung",
        "dozenten",
        "honorarkräfte",
        "ihk-prüfungsausschuss",
        "kostenträger",
        "betriebsrat",
        "aufnehmende betriebe",
        "träger",
        "ihk",
    ]
    assigned = _assign(generator, _DACH_AGENTS, poster_types)

    assert len(set(assigned)) == len(assigned), (
        f"Seed-Posts kollabieren auf dieselben Agenten: {assigned}"
    )

    by_name = {a.entity_name.lower(): a.agent_id for a in _DACH_AGENTS}
    expected = [by_name[ptype] for ptype in poster_types]
    assert assigned == expected, (
        "Ein poster_type, der einem Entity-Namen entspricht, muss den "
        f"namensgleichen Agenten treffen. erwartet={expected} ist={assigned}"
    )


def test_poster_type_als_entity_typ_behaelt_das_bisherige_verhalten(generator):
    """Der Typfall darf durch den Namens-Index nicht kaputtgehen.

    Zwei Posts desselben Typs bekommen weiterhin zwei verschiedene Agenten —
    die Rotation über ``used_indices`` bleibt erhalten.
    """
    agents = [
        _agent(10, "Umschüler A", "Retrainee"),
        _agent(11, "Umschüler B", "Retrainee"),
        _agent(12, "Dozent A", "Lecturer"),
    ]
    assigned = _assign(generator, agents, ["retrainee", "retrainee", "lecturer"])

    assert assigned == [10, 11, 12], (
        f"Typ-Match mit Rotation liefert nicht die erwartete Folge: {assigned}"
    )


def test_name_match_geht_dem_typ_match_vor(generator):
    """Bei Kollision zwischen Namens- und Typraum gewinnt der Name.

    Der Name ist die spezifischere Angabe: ein Agent heisst genau so, während
    ein Typ eine ganze Gruppe bezeichnet. Ein Modell, das ``Betriebsrat``
    schreibt, meint die Entität und nicht irgendeinen Vertreter des Typs.
    """
    agents = [
        _agent(20, "Betriebsrat", "WorksCouncil"),
        _agent(21, "Irgendwer", "betriebsrat"),
    ]
    assigned = _assign(generator, agents, ["betriebsrat"])

    assert assigned == [20]


def test_fallback_rotiert_statt_alles_auf_eine_stimme_zu_legen(generator):
    """RED ohne den Fix: vier unauflösbare poster_type ergeben 4x denselben Agenten."""
    agents = [
        _agent(30, "Alpha", "Alpha", influence=3.0),
        _agent(31, "Beta", "Beta", influence=3.0),
        _agent(32, "Gamma", "Gamma", influence=2.0),
    ]
    assigned = _assign(
        generator, agents, ["unbekannt-a", "unbekannt-b", "unbekannt-c", "unbekannt-d"]
    )

    assert len(set(assigned)) == 3, (
        f"Fallback verteilt nicht reihum über alle Agenten: {assigned}"
    )
    # Vierter Post wickelt auf den ersten Agenten zurück.
    assert assigned[3] == assigned[0]


def test_fallback_ist_bei_gleichstand_im_influence_weight_deterministisch(generator):
    """Die Auswahl darf nicht an der Reihenfolge der Kandidatenliste hängen.

    In ``sim_54c1c2a6a875`` lagen ``IHK``, ``IHK-Prüfungsausschuss`` und
    ``Träger`` alle bei ``influence_weight=3.0``. Wer davon "der Agent mit dem
    höchsten Einfluss" ist, entschied damit die stabile Sortierreihenfolge der
    Liste — also die Zufälligkeit der Generierungsreihenfolge.
    """
    agents = [
        _agent(40, "Alpha", "Alpha", influence=3.0),
        _agent(41, "Beta", "Beta", influence=3.0),
        _agent(42, "Gamma", "Gamma", influence=3.0),
    ]
    forward = _assign(generator, agents, ["unbekannt"])
    reversed_order = _assign(generator, list(reversed(agents)), ["unbekannt"])

    assert forward == reversed_order == [40], (
        "Bei Gleichstand muss die niedrigste agent_id gewinnen, unabhängig von "
        f"der Listenreihenfolge. forward={forward} reversed={reversed_order}"
    )


def test_distinkte_poster_types_ergeben_distinkte_agenten(generator):
    """Config-Ebene der Assertion, die #1226 auf der persistierten Ebene fordert.

    Die persistierte Variante (``count(distinct user_id)`` über die Seed-Posts)
    braucht zusätzlich die Kollisionsbehandlung im Twitter-Publish-Zweig und
    liegt deshalb in #1245. Hier wird die Vorbedingung geprüft: die Config gibt
    so viele verschiedene Poster vor, wie es verschiedene ``poster_type``-Werte
    gibt.
    """
    poster_types = [a.entity_name.lower() for a in _DACH_AGENTS]
    assigned = _assign(generator, _DACH_AGENTS, poster_types)

    assert len(set(assigned)) == len(set(poster_types))


def test_leere_agentenliste_bleibt_fehlerfrei(generator):
    """Degenerierter Fall: ohne Agenten fällt die Zuordnung auf 0 zurück."""
    assigned = _assign(generator, [], ["irgendwas"])

    assert assigned == [0]
