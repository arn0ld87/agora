"""Unit tests for OntologyManager + OntologyMutationService (Issue #11)."""

from __future__ import annotations

import threading
from typing import Any, Dict

import pytest

from app.services.ontology_mutation import (
    OntologyManager,
    OntologyMutationService,
    OntologyPatch,
    default_heuristic_scorer,
    sanitize_entity_type,
)


class StubStorage:
    """Minimal GraphStorage stand-in keeping ontology in memory."""

    def __init__(self) -> None:
        self._ontologies: Dict[str, Dict[str, Any]] = {}
        self.write_count = 0
        self._io_lock = threading.Lock()

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        with self._io_lock:
            return dict(self._ontologies.get(graph_id, {}))

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        with self._io_lock:
            self._ontologies[graph_id] = dict(ontology)
            self.write_count += 1


GRAPH = "0123456789abcdef0123456789abcdef"


# ---------------------------------------------------------------------------
# sanitize_entity_type
# ---------------------------------------------------------------------------


def test_sanitize_entity_type_accepts_well_formed_names():
    assert sanitize_entity_type("Scientist") == "Scientist"
    assert sanitize_entity_type("ClimateActivist") == "ClimateActivist"
    assert sanitize_entity_type("Political Party") == "Political_Party"


def test_sanitize_entity_type_rejects_bad_inputs():
    assert sanitize_entity_type("") is None
    assert sanitize_entity_type("Entity") is None
    assert sanitize_entity_type("   ") is None
    assert sanitize_entity_type(123) is None
    assert sanitize_entity_type("1Leading") is None


# ---------------------------------------------------------------------------
# Heuristic scorer
# ---------------------------------------------------------------------------


def test_default_scorer_rejects_generic_placeholders():
    assert default_heuristic_scorer("Thing", "Foo", "") == 0.0
    assert default_heuristic_scorer("Misc", "Foo", "") == 0.0


def test_default_scorer_rewards_verbatim_match_in_context():
    low = default_heuristic_scorer("Scientist", "Marie Curie", "Random context")
    high = default_heuristic_scorer(
        "Scientist", "Marie Curie", "The scientist Marie Curie won two Nobel prizes."
    )
    assert high > low


# ---------------------------------------------------------------------------
# OntologyManager
# ---------------------------------------------------------------------------


def _patch(conf: float, name: str = "Scientist", sample: str = "Marie Curie") -> OntologyPatch:
    return OntologyPatch(
        graph_id=GRAPH,
        novel_type=name,
        sanitised_type=name,
        sample_entity=sample,
        context="ctx",
        confidence=conf,
        mode="auto",
    )


def test_manager_applies_patch_only_once_per_type():
    storage = StubStorage()
    mgr = OntologyManager(storage)

    mgr.update(GRAPH, _patch(0.9))
    mgr.update(GRAPH, _patch(0.9))

    ontology = storage.get_ontology(GRAPH)
    types = [t["name"] for t in ontology["entity_types"]]
    assert types == ["Scientist"]
    # Second update was a no-op.
    assert storage.write_count == 1


def test_manager_is_thread_safe_under_contention():
    storage = StubStorage()
    mgr = OntologyManager(storage)

    def worker(i: int) -> None:
        mgr.update(GRAPH, _patch(0.9, name=f"Type{i}", sample=f"sample{i}"))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    types = [t["name"] for t in storage.get_ontology(GRAPH)["entity_types"]]
    assert sorted(types) == sorted(f"Type{i}" for i in range(20))


def test_contains_type_handles_mixed_ontology_shapes():
    storage = StubStorage()
    storage.set_ontology(GRAPH, {"entity_types": ["Person", {"name": "Organization"}]})
    mgr = OntologyManager(storage)

    assert mgr.contains_type(GRAPH, "Person")
    assert mgr.contains_type(GRAPH, "Organization")
    assert not mgr.contains_type(GRAPH, "Robot")


# ---------------------------------------------------------------------------
# OntologyMutationService
# ---------------------------------------------------------------------------


def _service(mode: str, *, min_conf: float = 0.6, scorer=None):
    storage = StubStorage()
    manager = OntologyManager(storage)
    svc = OntologyMutationService(
        manager=manager,
        mode=mode,
        min_confidence=min_conf,
        scorer=scorer,
    )
    return svc, storage, manager


def test_disabled_mode_returns_none_and_writes_nothing():
    svc, storage, _ = _service(OntologyMutationService.MODE_DISABLED)

    patch = svc.evaluate(GRAPH, "Scientist", "Marie Curie")

    assert patch is None
    assert storage.write_count == 0


def test_review_only_mode_logs_but_does_not_apply():
    svc, storage, _ = _service(
        OntologyMutationService.MODE_REVIEW_ONLY, scorer=lambda *_: 0.99
    )

    patch = svc.evaluate(GRAPH, "Scientist", "Marie Curie", context="context")

    assert patch is not None
    assert patch.applied is False
    assert storage.write_count == 0
    log = svc.audit_log(GRAPH)
    assert len(log) == 1
    assert log[0]["sanitised_type"] == "Scientist"
    assert log[0]["applied"] is False


def test_auto_mode_applies_when_confidence_clears_threshold():
    svc, storage, _ = _service(
        OntologyMutationService.MODE_AUTO, min_conf=0.5, scorer=lambda *_: 0.9
    )

    patch = svc.evaluate(GRAPH, "Scientist", "Marie Curie")

    assert patch is not None
    assert patch.applied is True
    assert storage.write_count == 1


def test_auto_mode_records_but_does_not_apply_below_threshold():
    svc, storage, _ = _service(
        OntologyMutationService.MODE_AUTO, min_conf=0.9, scorer=lambda *_: 0.4
    )

    patch = svc.evaluate(GRAPH, "Scientist", "Marie Curie")

    assert patch is not None
    assert patch.applied is False
    assert storage.write_count == 0
    assert len(svc.audit_log()) == 1


def test_sanitisation_failure_short_circuits():
    svc, storage, _ = _service(OntologyMutationService.MODE_AUTO)

    assert svc.evaluate(GRAPH, "", "x") is None
    assert svc.evaluate(GRAPH, "Entity", "x") is None
    assert storage.write_count == 0


def test_unknown_mode_raises():
    storage = StubStorage()
    manager = OntologyManager(storage)
    with pytest.raises(ValueError):
        OntologyMutationService(manager=manager, mode="yolo")


def test_audit_log_is_filterable_by_graph():
    svc, _, _ = _service(
        OntologyMutationService.MODE_REVIEW_ONLY, scorer=lambda *_: 0.9
    )

    svc.evaluate(GRAPH, "Scientist", "Marie")
    other = "ffffffffffffffffffffffffffffffff"
    svc.evaluate(other, "Musician", "Bach")

    assert len(svc.audit_log()) == 2
    assert len(svc.audit_log(GRAPH)) == 1
    assert svc.audit_log(GRAPH)[0]["sample_entity"] == "Marie"
