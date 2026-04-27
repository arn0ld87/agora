"""Tests for ontology generation post-processing."""

from app.config import Config
from app.services.ontology_generator import OntologyGenerator


def _entity(name: str):
    return {
        "name": name,
        "description": f"{name} description",
        "attributes": [],
        "examples": [],
    }


def _edge(index: int):
    return {
        "name": f"REL_{index}",
        "description": "relationship",
        "source_targets": [],
        "attributes": [],
    }


def test_validate_process_uses_configured_entity_cap(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 12)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 12)
    result = {
        "entity_types": [_entity(f"Type{i}") for i in range(14)],
        "edge_types": [_edge(i) for i in range(3)],
    }

    processed = OntologyGenerator()._validate_and_process(result)

    assert len(processed["entity_types"]) == 12
    assert processed["entity_types"][-2]["name"] == "Person"
    assert processed["entity_types"][-1]["name"] == "Organization"


def test_validate_process_preserves_existing_fallbacks_when_trimming(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 6)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 12)
    result = {
        "entity_types": (
            [_entity(f"Type{i}") for i in range(8)]
            + [_entity("Person"), _entity("Organization")]
        ),
        "edge_types": [],
    }

    processed = OntologyGenerator()._validate_and_process(result)

    names = [entity["name"] for entity in processed["entity_types"]]
    assert len(names) == 6
    assert names[-2:] == ["Person", "Organization"]


def test_validate_process_uses_configured_edge_cap(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 16)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_EDGE_TYPES", 4)
    result = {
        "entity_types": [_entity("Person"), _entity("Organization")],
        "edge_types": [_edge(i) for i in range(8)],
    }

    processed = OntologyGenerator()._validate_and_process(result)

    assert len(processed["edge_types"]) == 4


def test_build_user_message_uses_configured_entity_range(monkeypatch):
    monkeypatch.setattr(Config, "ONTOLOGY_MIN_ENTITY_TYPES", 7)
    monkeypatch.setattr(Config, "ONTOLOGY_MAX_ENTITY_TYPES", 13)

    message = OntologyGenerator()._build_user_message(["text"], "simulate", None)

    assert "between 7 and 13 entity types" in message
