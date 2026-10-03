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
