"""Issue #1759 (B1): Der Ontologie-Generator trägt ``kind``/``actor_capable`` durch."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.contracts.ontology_type_contract import contested_topic_type_names
from app.services.ontology_generator import (
    ONTOLOGY_SYSTEM_PROMPT,
    OntologyDefinition,
    OntologyEntityType,
    OntologyGenerator,
)


def _generator() -> OntologyGenerator:
    return OntologyGenerator(llm_client=MagicMock())


def _result(*entity_types: dict) -> dict:
    return {
        "entity_types": [dict(e) for e in entity_types],
        "edge_types": [],
        "analysis_summary": "",
    }


class TestSchema:
    def test_entity_type_without_metadata_stays_valid(self):
        entity = OntologyEntityType(name="Union", description="Gewerkschaft")
        assert entity.kind == "entity"
        assert entity.actor_capable is True

    def test_entity_type_accepts_contested_topic(self):
        entity = OntologyEntityType(
            name="Measure", description="Streitgegenstand", kind="contested_topic"
        )
        assert entity.kind == "contested_topic"
        assert entity.actor_capable is False

    def test_json_schema_exposes_the_fields_to_the_llm(self):
        props = OntologyDefinition.model_json_schema()["$defs"]["OntologyEntityType"][
            "properties"
        ]
        assert "kind" in props
        assert "actor_capable" in props

    def test_extra_llm_fields_do_not_break_parsing(self):
        entity = OntologyEntityType(name="X", description="d", surplus="ignored")  # type: ignore[call-arg]
        assert entity.name == "X"

    def test_prompt_lets_the_generator_declare_the_topic_type(self):
        assert "contested_topic" in ONTOLOGY_SYSTEM_PROMPT


class TestPersistedShape:
    def test_legacy_ontology_gets_explicit_defaults_and_no_topic(self):
        processed = _generator()._validate_and_process(
            _result({"name": "Union", "description": "d"}, {"name": "Person", "description": "d"})
        )
        union = next(e for e in processed["entity_types"] if e["name"] == "Union")
        assert union["kind"] == "entity"
        assert union["actor_capable"] is True
        assert contested_topic_type_names(processed) == frozenset()

    def test_declared_topic_is_persisted_and_readable(self):
        processed = _generator()._validate_and_process(
            _result(
                {"name": "Measure", "description": "d", "kind": "contested_topic"},
                {"name": "Union", "description": "d"},
            )
        )
        measure = next(e for e in processed["entity_types"] if e["name"] == "Measure")
        assert measure["kind"] == "contested_topic"
        assert measure["actor_capable"] is False
        assert contested_topic_type_names(processed) == frozenset({"Measure"})

    def test_unknown_kind_falls_back_to_entity(self):
        processed = _generator()._validate_and_process(
            _result({"name": "Odd", "description": "d", "kind": "topic-ish"})
        )
        odd = next(e for e in processed["entity_types"] if e["name"] == "Odd")
        assert odd["kind"] == "entity"
        assert contested_topic_type_names(processed) == frozenset()

    def test_non_actor_entity_keeps_declared_flag(self):
        processed = _generator()._validate_and_process(
            _result({"name": "Site", "description": "d", "actor_capable": False})
        )
        site = next(e for e in processed["entity_types"] if e["name"] == "Site")
        assert site["actor_capable"] is False

    def test_added_fallback_types_carry_explicit_metadata(self):
        processed = _generator()._validate_and_process(_result({"name": "Union", "description": "d"}))
        for name in ("Person", "Organization"):
            fallback = next(e for e in processed["entity_types"] if e["name"] == name)
            assert fallback["kind"] == "entity"
            assert fallback["actor_capable"] is True


class TestTopicTypeSurvivesCapAndIsMandatory:
    """Issue #1759 (B1): Kuerzen schneidet den Topic-Typ nie ab; ohne Topic-Typ Degradation."""

    def test_topic_type_at_the_end_survives_the_cap(self, monkeypatch):
        from app.config import Config

        monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 6)
        types = [{"name": f"Type{i}", "description": "d"} for i in range(8)]
        types.append({"name": "Measure", "description": "d", "kind": "contested_topic"})
        processed = _generator()._validate_and_process(_result(*types))

        names = [e["name"] for e in processed["entity_types"]]
        assert len(names) == 6
        assert "Measure" in names
        assert names[-2:] == ["Person", "Organization"]

    def test_topic_type_survives_the_final_cap_with_existing_fallbacks(self, monkeypatch):
        from app.config import Config

        monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 5)
        types = [{"name": f"Type{i}", "description": "d"} for i in range(7)]
        types.append({"name": "Measure", "description": "d", "kind": "contested_topic"})
        types += [{"name": "Person", "description": "d"}, {"name": "Organization", "description": "d"}]
        processed = _generator()._validate_and_process(_result(*types))

        names = [e["name"] for e in processed["entity_types"]]
        assert len(names) == 5
        assert "Measure" in names
        assert names[-2:] == ["Person", "Organization"]

    def test_missing_topic_type_is_a_visible_degradation(self):
        from app.contracts.pipeline_degradation_contract import DegradationKind

        generator = _generator()
        generator._validate_and_process(_result({"name": "Union", "description": "d"}))

        kinds = [event.kind for event in generator.degradations.report().events]
        assert kinds == [DegradationKind.ONTOLOGY_TOPIC_TYPE_MISSING]

    def test_declared_topic_type_is_not_degraded(self):
        generator = _generator()
        generator._validate_and_process(
            _result({"name": "Measure", "description": "d", "kind": "contested_topic"})
        )
        assert not generator.degradations

    def test_prompt_makes_the_topic_type_mandatory(self):
        assert "MUST declare exactly one type" in ONTOLOGY_SYSTEM_PROMPT

    def test_completion_message_names_the_missing_topic_type(self):
        from app.services.graph_build import _ontology_completion_message

        generator = _generator()
        assert _ontology_completion_message(generator) == "Ontology generation completed"
        generator._validate_and_process(_result({"name": "Union", "description": "d"}))
        assert "Streitgegenstand" in _ontology_completion_message(generator)
