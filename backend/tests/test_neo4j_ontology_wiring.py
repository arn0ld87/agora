"""Tests for the Neo4jStorage <-> OntologyMutationService wiring (Issue #11 Phase 2).

These exercise the late-bind hook directly — no Neo4j driver required. We
build a real OntologyMutationService against an in-memory StubStorage, plug
it into a hollow Neo4jStorage instance, then drive the
``_evaluate_ontology_mutations`` helper.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.ontology_mutation import OntologyManager, OntologyMutationService
from app.storage.neo4j_storage import Neo4jStorage


GRAPH = "0123456789abcdef0123456789abcdef"


class _StubOntoStorage:
    """Minimal in-memory GraphStorage replacement for OntologyManager."""

    def __init__(self) -> None:
        self._ontologies: Dict[str, Dict[str, Any]] = {}

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        return dict(self._ontologies.get(graph_id, {}))

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        self._ontologies[graph_id] = dict(ontology)


def _hollow_storage() -> Neo4jStorage:
    """Build a Neo4jStorage instance without touching the network."""
    inst = object.__new__(Neo4jStorage)
    inst._ontology_mutation_service = None
    return inst


def _make_service(mode: str) -> OntologyMutationService:
    onto_storage = _StubOntoStorage()
    onto_storage.set_ontology(GRAPH, {"entity_types": ["Scientist"]})
    manager = OntologyManager(storage=onto_storage)
    return OntologyMutationService(manager=manager, mode=mode, min_confidence=0.0)


def test_setter_late_binds_service():
    storage = _hollow_storage()
    assert storage._ontology_mutation_service is None
    service = _make_service("review_only")
    storage.set_ontology_mutation_service(service)
    assert storage._ontology_mutation_service is service


def test_no_service_is_noop():
    storage = _hollow_storage()
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": []},
        [{"name": "Greta", "type": "Activist"}],
        "Greta drove the protest at the conference.",
    )
    # Nothing to assert structurally — the call must just not raise.


def test_disabled_mode_is_noop():
    storage = _hollow_storage()
    service = _make_service("disabled")
    storage.set_ontology_mutation_service(service)
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": ["Scientist"]},
        [{"name": "Greta", "type": "Activist"}],
        "Greta drove the protest.",
    )
    assert service.audit_log() == []


def test_review_only_records_novel_type():
    storage = _hollow_storage()
    service = _make_service("review_only")
    storage.set_ontology_mutation_service(service)
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": ["Scientist"]},
        [
            {"name": "Greta", "type": "Activist"},
            {"name": "Marie Curie", "type": "Scientist"},  # known -> ignored
        ],
        "Greta marched while Marie Curie kept lecturing.",
    )
    log = service.audit_log()
    assert len(log) == 1
    assert log[0]["sanitised_type"] == "Activist"
    assert log[0]["sample_entity"] == "Greta"
    assert log[0]["mode"] == "review_only"


def test_known_types_are_skipped():
    storage = _hollow_storage()
    service = _make_service("review_only")
    storage.set_ontology_mutation_service(service)
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": ["Scientist"]},
        [{"name": "Marie Curie", "type": "Scientist"}],
        "context",
    )
    assert service.audit_log() == []


def test_dict_entity_types_in_ontology_are_handled():
    """Ontologies sometimes carry entity_types as [{name: ..., desc: ...}]."""
    storage = _hollow_storage()
    service = _make_service("review_only")
    storage.set_ontology_mutation_service(service)
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": [{"name": "Scientist", "description": "Researchers"}]},
        [{"name": "Marie Curie", "type": "Scientist"}],
        "context",
    )
    assert service.audit_log() == []


def test_duplicate_novel_types_in_chunk_dedup():
    storage = _hollow_storage()
    service = _make_service("review_only")
    storage.set_ontology_mutation_service(service)
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": []},
        [
            {"name": "Greta", "type": "Activist"},
            {"name": "Luisa", "type": "Activist"},  # same type — should not record twice
        ],
        "context",
    )
    log = service.audit_log()
    assert len(log) == 1
    assert log[0]["sample_entity"] == "Greta"


def test_service_exception_is_swallowed_not_raised():
    """A misbehaving service must not break ingestion."""

    class BoomService:
        mode = "review_only"

        def evaluate_batch(self, *_args, **_kwargs):
            raise RuntimeError("scorer exploded")

    storage = _hollow_storage()
    storage.set_ontology_mutation_service(BoomService())
    storage._evaluate_ontology_mutations(
        GRAPH,
        {"entity_types": []},
        [{"name": "Greta", "type": "Activist"}],
        "context",
    )
    # No assert needed — call must just not propagate the RuntimeError.
