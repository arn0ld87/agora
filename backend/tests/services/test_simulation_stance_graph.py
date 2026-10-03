"""Issue #1759 (A6): Stance aus dem Graph ableiten und gegen Startposts prüfen.

Referenzlauf: Ein Agent mit ``opposing`` bekam einen Pro-Startpost, weil die
Stance aus einem LLM-Batch ohne Graph-Kanten kam und Startposts nur nach Typ
zugeordnet wurden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.pipeline_degradation_contract import DegradationKind
from app.services.degradation_collector import DegradationCollector
from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import (
    AgentActivityConfig,
    EventConfig,
    SimulationConfigGenerator,
)
from app.services.simulation_stance_graph import (
    align_initial_posts_with_stance,
    derive_graph_stance,
    graph_edge_facts,
    resolve_stance,
    warn_unrepresented_positions,
)

TOPIC_TYPES = frozenset({"Measure"})
TOPIC_UUID = "topic-1"


def _entity(
    name: str,
    edges: Optional[List[Dict[str, Any]]] = None,
    *,
    uuid: Optional[str] = None,
    entity_type: str = "Organization",
    topic_label: str = "Measure",
) -> EntityNode:
    return EntityNode(
        uuid=uuid or f"uuid-{name}",
        name=name,
        labels=["Entity", entity_type],
        summary="",
        attributes={},
        related_edges=edges or [],
        related_nodes=[
            {
                "uuid": TOPIC_UUID,
                "name": "Pflichtquote",
                "labels": ["Entity", topic_label],
                "summary": "",
            }
        ],
    )


def _edge(edge_name: str, fact: str, *, direction: str = "outgoing") -> Dict[str, Any]:
    key = "target_node_uuid" if direction == "outgoing" else "source_node_uuid"
    return {"direction": direction, "edge_name": edge_name, "fact": fact, key: TOPIC_UUID}


class TestDeriveGraphStance:
    def test_supportive_fact_on_topic_edge_derives_supportive(self):
        entity = _entity("Gewerkschaft", [_edge("BACKS", "Die Gewerkschaft unterstützt die Pflichtquote.")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance == "supportive"

    def test_opposing_fact_on_topic_edge_derives_opposing(self):
        entity = _entity("IHK", [_edge("TAKES_POSITION", "Die IHK lehnt die Pflichtquote ab.")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance == "opposing"

    def test_polarity_is_not_guessed_from_the_edge_name_alone(self):
        # Der Kantenname SUPPORTS allein ist keine Aussage über die Polarität,
        # wenn der fact das Gegenteil sagt: gemischt -> uneindeutig.
        entity = _entity("X", [_edge("SUPPORTS", "X lehnt die Pflichtquote ab.")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance is None

    def test_edge_name_with_evaluative_stem_counts_relative_to_the_topic(self):
        entity = _entity("Verband", [_edge("OPPOSES", "Verband und Pflichtquote.")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance == "opposing"

    def test_neutral_edge_without_evaluation_is_ambiguous(self):
        entity = _entity("Presse", [_edge("COMMENTS_ON", "Die Presse berichtet über die Pflichtquote.")])
        derivation = derive_graph_stance(entity, TOPIC_TYPES)
        assert derivation.stance is None
        assert derivation.topic_edge_count == 1

    def test_negation_makes_the_polarity_ambiguous(self):
        entity = _entity("Y", [_edge("RELATES_TO", "Y unterstützt die Pflichtquote nicht.")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance is None

    def test_contradicting_topic_edges_are_ambiguous(self):
        entity = _entity(
            "Z",
            [
                _edge("A", "Z unterstützt die Pflichtquote."),
                _edge("B", "Z lehnt die Pflichtquote ab."),
            ],
        )
        assert derive_graph_stance(entity, TOPIC_TYPES).stance is None

    def test_agreeing_topic_edges_derive_the_shared_stance(self):
        entity = _entity(
            "Z",
            [_edge("A", "Z lehnt die Pflichtquote ab."), _edge("B", "Z kritisiert die Pflichtquote.")],
        )
        assert derive_graph_stance(entity, TOPIC_TYPES).stance == "opposing"

    def test_incoming_edge_from_topic_does_not_define_the_stance(self):
        entity = _entity("W", [_edge("OPPOSES", "Pflichtquote lehnt W ab.", direction="incoming")])
        assert derive_graph_stance(entity, TOPIC_TYPES).stance is None

    def test_edge_to_a_non_topic_node_is_ignored(self):
        entity = _entity("V", [_edge("SUPPORTS", "V unterstützt die Pflichtquote.")], topic_label="Organization")
        derivation = derive_graph_stance(entity, TOPIC_TYPES)
        assert derivation.stance is None
        assert derivation.topic_edge_count == 0

    def test_without_topic_types_nothing_is_derived(self):
        entity = _entity("IHK", [_edge("OPPOSES", "Die IHK lehnt die Pflichtquote ab.")])
        assert derive_graph_stance(entity, frozenset()).stance is None


class TestResolveStance:
    def test_graph_stance_overrides_llm_stance(self):
        entity = _entity("IHK", [_edge("TAKES_POSITION", "Die IHK lehnt die Pflichtquote ab.")])
        assert resolve_stance(entity, "supportive", TOPIC_TYPES) == "opposing"

    def test_ambiguous_polarity_keeps_llm_stance_and_logs(self):
        entity = _entity("Presse", [_edge("COMMENTS_ON", "Die Presse berichtet.")])
        with patch("app.services.simulation_stance_graph.logger") as log:
            stance = resolve_stance(entity, "observer", TOPIC_TYPES)
        assert stance == "observer"
        assert log.info.call_count == 1
        assert "uneindeutig" in log.info.call_args.args[0]
        assert log.info.call_args.args[1] == "Presse"

    def test_without_topic_type_llm_stance_is_unchanged(self):
        entity = _entity("IHK", [_edge("OPPOSES", "Die IHK lehnt die Pflichtquote ab.")])
        assert resolve_stance(entity, "supportive", frozenset()) == "supportive"

    def test_entity_without_topic_edge_keeps_llm_stance(self):
        assert resolve_stance(_entity("Solo"), "opposing", TOPIC_TYPES) == "opposing"


class TestGraphEdgeFacts:
    def test_topic_edges_come_first_and_carry_the_topic_name(self):
        other = {"direction": "outgoing", "edge_name": "WORKS_FOR", "fact": "x", "target_node_uuid": "o"}
        entity = _entity("IHK", [other, _edge("OPPOSES", "Die IHK lehnt ab.")])
        facts = graph_edge_facts(entity, TOPIC_TYPES)
        assert facts[0]["topic"] == "Pflichtquote"
        assert facts[0]["edge_name"] == "OPPOSES"
        assert "topic" not in facts[1]


def _agent(
    agent_id: int,
    name: str,
    stance: str,
    *,
    entity_type: str = "Organization",
    influence: float = 1.0,
    uuid: Optional[str] = None,
) -> AgentActivityConfig:
    return AgentActivityConfig(
        agent_id=agent_id,
        entity_uuid=uuid or f"uuid-{name}",
        entity_name=name,
        entity_type=entity_type,
        stance=stance,
        influence_weight=influence,
    )


class TestInitialPostAlignment:
    def test_post_against_sender_stance_is_moved_to_a_matching_agent(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Gewerkschaft", "supportive")]
        event = EventConfig(
            initial_posts=[
                {"content": "Pro-Post", "poster_type": "Organization", "poster_agent_id": 0, "stance": "supportive"}
            ]
        )
        warnings = align_initial_posts_with_stance(event, agents, TOPIC_TYPES)
        assert event.initial_posts[0]["poster_agent_id"] == 1
        assert warnings == []

    def test_matching_post_is_left_alone(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Gewerkschaft", "supportive")]
        event = EventConfig(
            initial_posts=[
                {"content": "Contra", "poster_type": "Organization", "poster_agent_id": 0, "stance": "opposing"}
            ]
        )
        align_initial_posts_with_stance(event, agents, TOPIC_TYPES)
        assert event.initial_posts[0]["poster_agent_id"] == 0

    def test_post_without_declared_stance_is_not_checked(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Gewerkschaft", "supportive")]
        event = EventConfig(
            initial_posts=[{"content": "?", "poster_type": "Organization", "poster_agent_id": 0}]
        )
        align_initial_posts_with_stance(event, agents, TOPIC_TYPES)
        assert event.initial_posts[0]["poster_agent_id"] == 0

    def test_neutral_sender_is_not_a_conflict(self):
        agents = [_agent(0, "Presse", "observer"), _agent(1, "Gewerkschaft", "supportive")]
        event = EventConfig(
            initial_posts=[
                {"content": "Pro", "poster_type": "MediaOutlet", "poster_agent_id": 0, "stance": "supportive"}
            ]
        )
        align_initial_posts_with_stance(event, agents, TOPIC_TYPES)
        assert event.initial_posts[0]["poster_agent_id"] == 0

    def test_same_type_candidate_is_preferred_over_higher_influence(self):
        agents = [
            _agent(0, "IHK", "opposing", entity_type="Organization"),
            _agent(1, "Medien", "supportive", entity_type="MediaOutlet", influence=3.0),
            _agent(2, "Gewerkschaft", "supportive", entity_type="Organization", influence=1.0),
        ]
        event = EventConfig(
            initial_posts=[
                {"content": "Pro", "poster_type": "Organization", "poster_agent_id": 0, "stance": "supportive"}
            ]
        )
        align_initial_posts_with_stance(event, agents, TOPIC_TYPES)
        assert event.initial_posts[0]["poster_agent_id"] == 2

    def test_unresolvable_conflict_is_visible_and_recorded(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Verband", "opposing")]
        event = EventConfig(
            initial_posts=[
                {"content": "Pro", "poster_type": "Organization", "poster_agent_id": 0, "stance": "supportive"}
            ]
        )
        collector = DegradationCollector()
        warnings = align_initial_posts_with_stance(event, agents, TOPIC_TYPES, collector)
        assert event.initial_posts[0]["poster_agent_id"] == 0
        assert len(warnings) == 1
        kinds = [e.kind for e in collector.report().events]
        assert kinds == [DegradationKind.INITIAL_POST_STANCE_CONFLICT]

    def test_without_topic_types_posts_are_untouched(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Gewerkschaft", "supportive")]
        event = EventConfig(
            initial_posts=[
                {"content": "Pro", "poster_type": "Organization", "poster_agent_id": 0, "stance": "supportive"}
            ]
        )
        assert align_initial_posts_with_stance(event, agents, frozenset()) == []
        assert event.initial_posts[0]["poster_agent_id"] == 0


class TestUnrepresentedPositions:
    def _entities(self) -> List[EntityNode]:
        return [
            _entity("IHK", [_edge("X", "Die IHK lehnt die Pflichtquote ab.")]),
            _entity("Gewerkschaft", [_edge("Y", "Die Gewerkschaft unterstützt die Pflichtquote.")]),
        ]

    def test_position_held_by_no_agent_is_warned_and_recorded(self):
        agents = [_agent(0, "IHK", "neutral"), _agent(1, "Gewerkschaft", "supportive")]
        collector = DegradationCollector()
        warnings = warn_unrepresented_positions(self._entities(), agents, TOPIC_TYPES, collector)
        assert len(warnings) == 1
        assert "opposing" in warnings[0]
        events = collector.report().events
        assert [e.kind for e in events] == [DegradationKind.STANCE_POSITION_UNREPRESENTED]

    def test_synthetic_skeptic_does_not_mask_a_missing_graph_position(self):
        agents = [
            _agent(0, "IHK", "neutral"),
            _agent(1, "Gewerkschaft", "supportive"),
            _agent(2, "Skeptiker 2", "opposing", uuid="synthetic-skeptic-2"),
        ]
        warnings = warn_unrepresented_positions(self._entities(), agents, TOPIC_TYPES)
        assert len(warnings) == 1

    def test_all_positions_represented_is_silent(self):
        agents = [_agent(0, "IHK", "opposing"), _agent(1, "Gewerkschaft", "supportive")]
        assert warn_unrepresented_positions(self._entities(), agents, TOPIC_TYPES) == []

    def test_without_topic_types_nothing_is_warned(self):
        agents = [_agent(0, "IHK", "neutral")]
        assert warn_unrepresented_positions(self._entities(), agents, frozenset()) == []


@pytest.fixture()
def generator():
    with patch("app.services.simulation_config_generator.LLMClient", MagicMock()):
        yield SimulationConfigGenerator(api_key="k", base_url="http://localhost")


def _llm_batch(stances: Dict[int, str]) -> Dict[str, Any]:
    return {"agent_configs": [{"agent_id": i, "stance": s} for i, s in stances.items()]}


class TestBatchIntegration:
    def test_topic_edge_overrides_llm_stance_in_the_batch(self, generator):
        generator._contested_topic_types = TOPIC_TYPES
        entities = [_entity("IHK", [_edge("TAKES_POSITION", "Die IHK lehnt die Pflichtquote ab.")])]
        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch({0: "supportive"})) as call:
            configs = generator._generate_agent_configs_batch("ctx", entities, 0, "Frage")
        assert configs[0].stance == "opposing"
        assert "graph_edges" in call.call_args.args[0]
        assert "lehnt die Pflichtquote ab" in call.call_args.args[0]

    def test_ambiguous_edge_keeps_llm_stance_in_the_batch(self, generator):
        generator._contested_topic_types = TOPIC_TYPES
        entities = [_entity("Presse", [_edge("COMMENTS_ON", "Die Presse berichtet.")])]
        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch({0: "observer"})):
            configs = generator._generate_agent_configs_batch("ctx", entities, 0, "Frage")
        assert configs[0].stance == "observer"

    def test_without_topic_type_batch_behaves_as_before(self, generator):
        entities = [_entity("IHK", [_edge("OPPOSES", "Die IHK lehnt die Pflichtquote ab.")])]
        with patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch({0: "supportive"})) as call:
            configs = generator._generate_agent_configs_batch("ctx", entities, 0, "Frage")
        assert configs[0].stance == "supportive"
        assert "graph_edges" not in call.call_args.args[0]


class TestGenerateConfigIntegration:
    def _run(self, generator, topic_types, posts, degradations=None):
        entities = [
            _entity("IHK", [_edge("TAKES_POSITION", "Die IHK lehnt die Pflichtquote ab.")], uuid="u-ihk"),
            _entity("Gewerkschaft", [_edge("BACKS", "Die Gewerkschaft unterstützt die Pflichtquote.")], uuid="u-gew"),
        ]
        batch = _llm_batch({0: "supportive", 1: "opposing"})  # beide gegen den Graph
        with (
            patch.object(generator, "_build_context", return_value="ctx"),
            patch.object(generator, "_generate_time_config", return_value={}),
            patch.object(generator, "_generate_event_config", return_value={"initial_posts": posts}),
            patch.object(generator, "_call_llm_with_retry", return_value=batch),
        ):
            return generator.generate_config(
                simulation_id="s",
                project_id="p",
                graph_id="g",
                simulation_requirement="Frage",
                document_text="Doc",
                entities=entities,
                contested_topic_types=topic_types,
                degradations=degradations,
            )

    def test_start_post_never_runs_against_the_stance_of_its_sender(self, generator):
        # Typ-Zuordnung allein legt beide Posts auf den falschen Absender
        # (Pro-Post -> IHK/opposing, Contra-Post -> Gewerkschaft/supportive).
        posts = [
            {"content": "Pro", "poster_type": "ihk", "stance": "supportive"},
            {"content": "Contra", "poster_type": "gewerkschaft", "stance": "opposing"},
        ]
        params = self._run(generator, TOPIC_TYPES, posts)
        assert len(params.event_config.initial_posts) == 2
        stance_by_id = {a.agent_id: a.stance for a in params.agent_configs}
        for post in params.event_config.initial_posts:
            assert stance_by_id[post["poster_agent_id"]] == post["stance"]

    def test_graph_stance_wins_over_contradicting_llm_stance(self, generator):
        params = self._run(generator, TOPIC_TYPES, [])
        by_name = {a.entity_name: a.stance for a in params.agent_configs}
        assert by_name["IHK"] == "opposing"
        assert by_name["Gewerkschaft"] == "supportive"

    def test_without_topic_type_llm_stances_and_posts_stay_as_generated(self, generator):
        posts = [{"content": "Pro", "poster_type": "ihk", "stance": "supportive"}]
        params = self._run(generator, frozenset(), posts)
        by_name = {a.entity_name: a.stance for a in params.agent_configs}
        assert by_name["IHK"] == "supportive"
        assert by_name["Gewerkschaft"] == "opposing"
        assert params.event_config.initial_posts[0]["poster_agent_id"] == 0
        assert "Stance check" not in params.generation_reasoning

    def test_unresolvable_conflict_surfaces_in_reasoning_and_collector(self, generator):
        # Nur Gegner im Pool: ein Pro-Post hat keinen passenden Absender.
        entities = [_entity("IHK", [_edge("T", "Die IHK lehnt die Pflichtquote ab.")], uuid="u-ihk")]
        collector = DegradationCollector()
        with (
            patch.object(generator, "_build_context", return_value="ctx"),
            patch.object(generator, "_generate_time_config", return_value={}),
            patch.object(
                generator,
                "_generate_event_config",
                return_value={"initial_posts": [{"content": "Pro", "poster_type": "ihk", "stance": "supportive"}]},
            ),
            patch.object(generator, "_call_llm_with_retry", return_value=_llm_batch({0: "opposing"})),
        ):
            params = generator.generate_config(
                simulation_id="s",
                project_id="p",
                graph_id="g",
                simulation_requirement="Frage",
                document_text="Doc",
                entities=entities,
                contested_topic_types=TOPIC_TYPES,
                degradations=collector,
            )
        assert "Stance check" in params.generation_reasoning
        kinds = {e.kind for e in collector.report().events}
        assert DegradationKind.INITIAL_POST_STANCE_CONFLICT in kinds


class TestTopicTypeResolutionAndSchema:
    def test_topic_types_come_from_the_project_ontology(self):
        from app.services.simulation_stance_graph import resolve_contested_topic_types

        project = MagicMock()
        project.ontology = {"entity_types": [{"name": "Measure", "kind": "contested_topic"}]}
        with patch("app.models.project.ProjectManager.get_project", return_value=project):
            assert resolve_contested_topic_types("p") == frozenset({"Measure"})

    def test_missing_project_or_read_error_means_no_topic_type(self):
        from app.services.simulation_stance_graph import resolve_contested_topic_types

        with patch("app.models.project.ProjectManager.get_project", return_value=None):
            assert resolve_contested_topic_types("p") == frozenset()
        with patch("app.models.project.ProjectManager.get_project", side_effect=OSError("boom")):
            assert resolve_contested_topic_types("p") == frozenset()

    def test_initial_post_schema_reads_free_text_stance_and_never_fails(self):
        from app.services.simulation_config_schemas import InitialPostSchema

        assert InitialPostSchema(content="c", poster_type="t", stance="Supportive").stance == "supportive"
        assert InitialPostSchema(content="c", poster_type="t", stance="strongly opposing").stance == "opposing"
        assert InitialPostSchema(content="c", poster_type="t", stance="???").stance is None
        assert InitialPostSchema(content="c", poster_type="t").stance is None

    def test_assignment_keeps_the_declared_post_stance(self, generator):
        agents = [_agent(0, "IHK", "opposing")]
        event = EventConfig(initial_posts=[{"content": "c", "poster_type": "ihk", "stance": "opposing"}])
        result = generator._assign_initial_post_agents(event, agents)
        assert result.initial_posts[0]["stance"] == "opposing"
