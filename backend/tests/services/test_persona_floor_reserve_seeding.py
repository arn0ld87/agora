"""UAT-001 — Der Floor-Aufschlag braucht eine Reserve, sonst fällt der Lauf darunter.

Produktionsbeleg (armserver, Container ``agora``, 2026-10-09, Simulation
``sim_e3bf16659731``)::

    16:10:15 INFO: persona-floor angewendet: generation_pool=9 floor=20
    16:10:18 INFO: Persona-Eligibility (LLM): Entitaet abgelehnt name=Gemeinde Sonnenried type=Municipality
    16:10:20 INFO: Persona-Eligibility (LLM): Entitaet abgelehnt name=Busbetrieb type=PublicTransportOperator
    16:10:52 INFO: Persona-Eligibility: 2 Kandidat(en) abgelehnt, 0 von 2 freien
                  Plaetzen aus der Reserve nachbesetzt (Reserve: 0 Kandidaten)
    16:10:52 INFO: Persona generation complete: 20 Kandidat(en) angetreten,
                  2 abgelehnt, 18 Personas erzeugt.
    16:11:12 INFO: Simulation preparation completed: sim_e3bf16659731, entities=9, profiles=18

Der Aufschlag erzeugte also 20 Plätze, aber keine Nachrücker: die Reserve ist
das, was der ``max_agents``-Cap wegschneidet, und ein Pool von 9 wurde von
keinem Cap beschnitten. Jede Ablehnung fiel damit ersatzlos unter den Floor,
den der Report-Contract verlangt (``MIN_PERSONA_TABLE_ROWS``) — der Bericht
endete ``INCOMPLETE`` ohne Text, nachdem die Pipeline bereits Kosten
verursacht hatte.

Die Ablehnung ist, wie der Beleg zeigt, **nicht** deterministisch pro Entität:
von den sechs Vorkommen der beiden abgelehnten Entitäten im aufgefüllten Pool
wurden nur zwei abgelehnt. Eine Nachbesetzung mit denselben Entitäten hat
deshalb echte Erfolgschancen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import OasisProfileGenerator
from app.services.prepare_service import (
    _apply_persona_floor_to_entities,
    _phase_generate_profiles,
)
from app.services.report_agent import MIN_PERSONA_TABLE_ROWS

import types

import pytest


def _entity(name: str, entity_type: str = "Organization") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=f"{name} im Kontext der Streitfrage.",
        attributes={},
    )


def _pool(size: int) -> list[EntityNode]:
    return [_entity(f"E{i}") for i in range(size)]


def _state() -> types.SimpleNamespace:
    # Bewusst ohne ``simulation_id``: kein Checkpoint, kein Artefakt-Store —
    # geprüft wird allein die Reserve des Generierungsaufrufs.
    return types.SimpleNamespace(
        graph_id="graph_1",
        enable_reddit=False,
        enable_twitter=False,
        profiles_count=0,
    )


class _CapturingGenerator:
    """Fake-Generator, der die Aufruf-Parameter festhält und den Pool 1:1 abbildet."""

    last_kwargs: dict = {}

    def __init__(self, *_args, **_kwargs):
        pass

    def generate_profiles_from_entities(self, **kwargs):
        type(self).last_kwargs = kwargs
        return [object()] * len(kwargs["entities"])

    def save_profiles(self, **_kwargs):
        return None

    def _build_demographic_slots(self, _entities):
        return None


@pytest.fixture()
def capturing_generator(monkeypatch):
    from app.services import prepare_service as ps_mod

    monkeypatch.setattr(ps_mod, "OasisProfileGenerator", _CapturingGenerator)
    _CapturingGenerator.last_kwargs = {}
    return _CapturingGenerator


class TestReserveSeedingOnFloorPadding:
    def test_floor_aufschlag_fuellt_die_reserve(self, capturing_generator, tmp_path):
        """RED ohne den Fix: ``reserve_entities`` bleibt leer (bzw. None).

        Pool 9 < Floor 20 ist genau der Fall, für den der Aufschlag existiert —
        und genau der Fall, in dem der Cap nichts wegschneidet und die Reserve
        damit leer bleibt.
        """
        small_pool = _pool(9)
        filtered = types.SimpleNamespace(entities=list(small_pool))

        _phase_generate_profiles(
            _state(),
            MagicMock(),
            filtered,
            str(tmp_path),
            llm_model=None,
            language="de",
            use_llm_for_profiles=False,
            parallel_profile_count=1,
            persona_floor=MIN_PERSONA_TABLE_ROWS,
        )

        kwargs = capturing_generator.last_kwargs
        assert len(kwargs["entities"]) == MIN_PERSONA_TABLE_ROWS
        reserve = kwargs["reserve_entities"]
        assert reserve, "Der Floor-Aufschlag hat keine Nachrücker bekommen"
        assert {e.uuid for e in reserve} == {e.uuid for e in small_pool}
        # Die persistierte Auswahl (Checkpoint) muss dieselbe Reserve tragen —
        # sonst startet ein Resume mit leerer Reserve in dasselbe Defizit.
        assert {e.uuid for e in filtered.reserve_entities} == {
            e.uuid for e in small_pool
        }

    def test_cap_reserve_bleibt_unangetastet(self, capturing_generator, tmp_path):
        """Gegenprobe: schneidet der Cap etwas weg, bleibt dessen Reserve die Quelle."""
        cut = [_entity("Nachruecker")]
        filtered = types.SimpleNamespace(entities=_pool(9), reserve_entities=cut)

        _phase_generate_profiles(
            _state(),
            MagicMock(),
            filtered,
            str(tmp_path),
            llm_model=None,
            language="de",
            use_llm_for_profiles=False,
            parallel_profile_count=1,
            persona_floor=MIN_PERSONA_TABLE_ROWS,
        )

        assert capturing_generator.last_kwargs["reserve_entities"] is cut

    def test_ohne_aufschlag_keine_reserve(self, capturing_generator, tmp_path):
        """Gegenprobe: ist der Pool groß genug, ändert sich nichts."""
        filtered = types.SimpleNamespace(entities=_pool(24))

        _phase_generate_profiles(
            _state(),
            MagicMock(),
            filtered,
            str(tmp_path),
            llm_model=None,
            language="de",
            use_llm_for_profiles=False,
            parallel_profile_count=1,
            persona_floor=MIN_PERSONA_TABLE_ROWS,
        )

        assert len(capturing_generator.last_kwargs["entities"]) == 24
        assert not capturing_generator.last_kwargs["reserve_entities"]


class TestFloorWirdNachAblehnungenErreicht:
    """Der Produktionsfall als Durchlauf: 9 Entitäten, 2 Ablehnungen, Floor 20."""

    @pytest.fixture()
    def generator(self):
        return OasisProfileGenerator(
            api_key="test", base_url="http://localhost", language="de"
        )

    def test_zwei_ablehnungen_werden_nachbesetzt(self, generator, monkeypatch):
        rejected_once: dict[str, int] = {}
        counter = {"n": 0}

        def fake_llm(**kwargs):
            name = kwargs["entity_name"]
            counter["n"] += 1
            # Nur das erste Vorkommen wird abgelehnt — der Beleg zeigt, dass
            # das Eignungs-Gate pro Aufruf entscheidet, nicht pro Entität.
            if name in ("E0", "E1") and rejected_once.get(name, 0) == 0:
                rejected_once[name] = 1
                return {"ineligible": True, "ineligible_reason": "kein Traeger"}
            return {
                "ineligible": False,
                "display_name": f"{name} {counter['n']}",
                "handle": f"{name.lower()}{counter['n']}",
                "bio": "",
                "persona": f"{name} nimmt teil.",
                "age": 40,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "",
                "voice_register": "neutral-de",
            }

        monkeypatch.setattr(generator, "_generate_profile_with_llm", fake_llm)

        pool = _pool(9)
        padded = _apply_persona_floor_to_entities(
            pool, minimum=MIN_PERSONA_TABLE_ROWS
        )
        assert len(padded) == MIN_PERSONA_TABLE_ROWS

        profiles = generator.generate_profiles_from_entities(
            entities=padded,
            use_llm=True,
            parallel_count=1,
            reserve_entities=list(pool),
        )

        assert len([p for p in profiles if p is not None]) == MIN_PERSONA_TABLE_ROWS

    def test_ohne_reserve_bleibt_das_defizit(self, generator, monkeypatch):
        """Gegenprobe = Produktionsbefund: ohne Reserve bleiben 18 von 20."""

        def fake_llm(**kwargs):
            name = kwargs["entity_name"]
            if name in ("E0", "E1"):
                return {"ineligible": True, "ineligible_reason": "kein Traeger"}
            return {
                "ineligible": False,
                "display_name": f"{name} einmalig",
                "handle": f"{name.lower()}einmalig",
                "bio": "",
                "persona": f"{name} nimmt teil.",
                "age": 40,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "",
                "voice_register": "neutral-de",
            }

        monkeypatch.setattr(generator, "_generate_profile_with_llm", fake_llm)

        pool = _pool(9)
        padded = _apply_persona_floor_to_entities(
            pool, minimum=MIN_PERSONA_TABLE_ROWS
        )

        profiles = generator.generate_profiles_from_entities(
            entities=padded,
            use_llm=True,
            parallel_count=1,
            reserve_entities=[],
        )

        remaining = [p for p in profiles if p is not None]
        assert len(remaining) < MIN_PERSONA_TABLE_ROWS
