"""Issue #1779 Schritt 3 — Regel-Defaults der Agentenkonfiguration.

``_generate_agent_config_by_rule`` greift, wenn die Batch-Antwort des Modells
einen Agenten nicht enthält oder der Batch ausfällt. Die Regel darf keine Haltung
erfinden: ohne Graph-Kante gilt ``neutral`` (nur Medien ``observer``), die
Graph-Haltung gilt vor der Regel, und der Rückfall steht sichtbar im Ergebnis
(Degradation ``agent_config_rule_fallback``, ``config_source="rule_fallback"``),
nie als stiller Default.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.services.degradation_collector import DegradationCollector
from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import SimulationConfigGenerator

STATEMENT = "Der Kreistag beschließt, den Kreißsaal zu schließen."
TOPIC_TYPES = frozenset({"Measure"})
TOPIC_UUID = "topic-1"
AFFECTED_TYPES = ["Person", "HealthcareProviderGroup", "Hospital", "PoliticalGroup", "CommunityGroup"]


@pytest.fixture()
def generator():
    with patch("app.services.simulation_config_generator.LLMClient", MagicMock()):
        yield SimulationConfigGenerator(api_key="k", base_url="http://localhost")


def _entity(
    name: str = "Betriebsrat",
    entity_type: str = "Person",
    edges: Optional[List[Dict[str, Any]]] = None,
) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
        related_edges=edges or [],
        related_nodes=[
            {"uuid": TOPIC_UUID, "name": "Schließung", "labels": ["Entity", "Measure"], "summary": ""}
        ],
    )


def _edge(fact: str) -> Dict[str, Any]:
    return {
        "direction": "outgoing",
        "edge_name": "TAKES_POSITION",
        "fact": fact,
        "target_node_uuid": TOPIC_UUID,
    }


@pytest.mark.parametrize("entity_type", AFFECTED_TYPES)
def test_rule_fallback_never_uses_observer_for_affected_types(generator, entity_type) -> None:
    cfg = generator._generate_agent_config_by_rule(_entity(entity_type=entity_type), STATEMENT)

    assert cfg["stance"] == "neutral"
    assert cfg["stance"] != "observer"
    assert cfg["sentiment_bias"] == 0.0


@pytest.mark.parametrize(
    "entity_type", ["University", "GovernmentAgency", "NGO", "Professor", "Student", "Alumni", "Unbekannt"]
)
def test_rule_fallback_invents_no_position_for_any_rule_branch(generator, entity_type) -> None:
    cfg = generator._generate_agent_config_by_rule(_entity(entity_type=entity_type))

    assert cfg["stance"] == "neutral"
    assert cfg["sentiment_bias"] == 0.0


def test_rule_fallback_observer_is_reserved_for_media(generator) -> None:
    cfg = generator._generate_agent_config_by_rule(_entity("Kurier", "MediaOutlet"), STATEMENT)

    assert cfg["stance"] == "observer"


@pytest.mark.parametrize(
    ("fact", "stance", "sign"),
    [
        ("Der Betriebsrat lehnt die Schließung ab.", "opposing", -1),
        ("Der Betriebsrat unterstützt die Schließung.", "supportive", 1),
    ],
)
def test_rule_fallback_takes_the_graph_stance_first(generator, fact, stance, sign) -> None:
    generator._contested_topic_types = TOPIC_TYPES

    cfg = generator._generate_agent_config_by_rule(_entity(edges=[_edge(fact)]), STATEMENT)

    assert cfg["stance"] == stance
    assert cfg["sentiment_bias"] * sign > 0


@pytest.mark.parametrize(
    ("fact", "stance"),
    [
        ("Der Betriebsrat lehnt die Schließung ab.", "opposing"),
        ("Der Betriebsrat unterstützt die Schließung.", "supportive"),
    ],
)
def test_rule_fallback_sign_matches_stance(generator, fact, stance) -> None:
    from app.services.simulation_config_agents import _align_sentiment_sign

    generator._contested_topic_types = TOPIC_TYPES

    cfg = generator._generate_agent_config_by_rule(_entity(edges=[_edge(fact)]), STATEMENT)

    # Das Vorzeichen ist bereits abgeglichen: eine weitere Korrektur ändert nichts.
    assert _align_sentiment_sign(cfg["stance"], cfg["sentiment_bias"]) == cfg["sentiment_bias"]
    assert cfg["stance"] == stance


def test_rule_fallback_without_contested_question_keeps_the_previous_bias(generator) -> None:
    generator._contested_topic_types = TOPIC_TYPES

    cfg = generator._generate_agent_config_by_rule(
        _entity(edges=[_edge("Der Betriebsrat lehnt die Schließung ab.")])
    )

    assert cfg["sentiment_bias"] == 0.0


def _llm_batch(*agent_ids: int) -> Dict[str, Any]:
    return {
        "agent_configs": [
            {"agent_id": i, "stance": "supportive", "sentiment_bias": 0.4, "actor_class": "individual"}
            for i in agent_ids
        ]
    }


class TestRuleFallbackIsVisible:
    def test_missing_llm_entry_marks_the_agent_and_records_a_degradation(self, generator) -> None:
        collector = DegradationCollector()
        generator._degradations = collector
        entities = [_entity("A"), _entity("B"), _entity("C")]

        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch(0, 2)):
            configs = generator._generate_agent_configs_batch("ctx", entities, 0, "Frage")

        assert [c.config_source for c in configs] == ["llm", "rule_fallback", "llm"]
        events = collector.report().events
        assert [e.kind for e in events] == [DegradationKind.AGENT_CONFIG_RULE_FALLBACK]
        assert events[0].severity is DegradationSeverity.WARNING
        assert events[0].occurrences == 1
        assert "B" in events[0].detail

    def test_failed_batch_marks_every_agent(self, generator) -> None:
        collector = DegradationCollector()
        generator._degradations = collector
        entities = [_entity("A"), _entity("B")]

        with patch.object(generator, "_call_llm_with_retry", side_effect=RuntimeError("llm down")):
            configs = generator._generate_agent_configs_batch("ctx", entities, 0, "Frage")

        assert {c.config_source for c in configs} == {"rule_fallback"}
        assert {c.stance for c in configs} == {"neutral"}
        assert [e.kind for e in collector.report().events] == [
            DegradationKind.AGENT_CONFIG_RULE_FALLBACK,
            DegradationKind.AGENT_CONFIG_RULE_FALLBACK,
        ]

    def test_complete_llm_answer_records_nothing(self, generator) -> None:
        collector = DegradationCollector()
        generator._degradations = collector

        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch(0, 1)):
            configs = generator._generate_agent_configs_batch(
                "ctx", [_entity("A"), _entity("B")], 0, "Frage"
            )

        assert {c.config_source for c in configs} == {"llm"}
        assert not collector

    def test_without_a_collector_the_marker_still_stands(self, generator) -> None:
        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch()):
            configs = generator._generate_agent_configs_batch("ctx", [_entity("A")], 0, "Frage")

        assert configs[0].config_source == "rule_fallback"

    def test_rule_fallback_with_graph_stance_and_contested_question_aligns_the_sign(
        self, generator
    ) -> None:
        generator._contested_topic_types = TOPIC_TYPES
        entities = [_entity("A", edges=[_edge("A lehnt die Schließung ab.")])]

        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch()):
            configs = generator._generate_agent_configs_batch(
                "ctx", entities, 0, "Frage", contested_statement=STATEMENT
            )

        assert configs[0].config_source == "rule_fallback"
        assert configs[0].stance == "opposing"
        assert configs[0].sentiment_bias < 0

    def test_generate_config_surfaces_the_fallback_in_reasoning_and_collector(self, generator) -> None:
        collector = DegradationCollector()
        entities = [_entity("A"), _entity("B")]
        with (
            patch.object(generator, "_build_context", return_value="ctx"),
            patch.object(generator, "_generate_time_config", return_value={}),
            patch.object(generator, "_generate_event_config", return_value={"initial_posts": []}),
            patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch(0)),
        ):
            params = generator.generate_config(
                simulation_id="s",
                project_id="p",
                graph_id="g",
                simulation_requirement="Frage",
                document_text="Doc",
                entities=entities,
                contested_topic_types=frozenset(),
                degradations=collector,
            )

        sources = {a.entity_name: a.config_source for a in params.agent_configs}
        assert sources["A"] == "llm"
        assert sources["B"] == "rule_fallback"
        assert "Regel-Fallback" in params.generation_reasoning
        assert [e.kind for e in collector.report().events] == [
            DegradationKind.AGENT_CONFIG_RULE_FALLBACK
        ]
