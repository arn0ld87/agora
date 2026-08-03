"""Degradierungs-Verdrahtung im **produktiven** Build-Pfad (Issue #1029).

``tests/services/test_degradation_wiring.py`` sichert die vier Ebenen unter
``GraphBuilderService._build_graph_worker`` ab. Dieser Worker ist aber nicht
der Pfad, den der Endpunkt ``POST /api/graph/build`` nimmt: der ruft
``GraphBuildService.build_graph``, und dessen ``build_task``-Closure ruft
``add_text_batches`` selbst auf und schreibt sein eigenes Task-Ergebnis.

Die erste Fassung von Bündel B hat genau diesen Pfad übersehen — Slice 14 und
15 waren in Produktion wirkungslos, obwohl vier Ebenen Tests grün waren. Das
ist dieselbe Fehlerklasse wie #961, #966 und #985: der Fix saß am falschen
Codepfad. Diese Datei nagelt deshalb den Pfad fest, den die API tatsächlich
nimmt.

Der Fake-Builder spiegelt die Signatur von ``add_text_batches`` **explizit**
statt über ``**kwargs``: fällt ein Argument im Produktionscode weg, bricht der
Test mit ``TypeError`` statt still zu bestehen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.models.project import ProjectStatus
from app.models.task import TaskStatus
from app.services.graph_build import GraphBuildService
from app.services.graph_builder import GraphBuilderService

PROJECT_ID = "proj_ba5eba11c0de"


class _FakeBuilder:
    """Minimaler Builder mit der echten Qualitätsbewertung.

    ``assess_graph_quality_from_counts`` wird nicht nachgebaut, sondern direkt
    aus ``GraphBuilderService`` übernommen — sonst würde der Test eine
    Attrappe prüfen statt der Schwellenlogik, die in Produktion läuft.
    """

    assess_graph_quality_from_counts = (
        GraphBuilderService.assess_graph_quality_from_counts
    )

    def __init__(self, *, node_count: int, edge_count: int, batch_effect=None):
        self.node_count = node_count
        self.edge_count = edge_count
        self._batch_effect = batch_effect
        self.completed_graph_ids: list[str] = []

    def create_graph(self, name: str) -> str:
        return "graph-1029"

    def set_ontology(self, graph_id, ontology) -> None:
        return None

    def add_text_batches(
        self,
        graph_id,
        chunks,
        batch_size,
        progress_callback,
        ner_extractor,
        degradations,
        extraction_tally,
    ):
        if self._batch_effect is not None:
            self._batch_effect(degradations, extraction_tally)

    def get_graph_data(self, graph_id):
        return {"node_count": self.node_count, "edge_count": self.edge_count}

    def mark_graph_completed(self, graph_id) -> None:
        self.completed_graph_ids.append(graph_id)


class _Router:
    def __init__(self, _run_id):
        pass

    def resolve(self, stage_id):
        return ResolvedRoute(
            stage=stage_id,
            provider_id="openai",
            model="gpt-4.1-mini",
            routing_version=1,
        )

    def lock_stage(self, *_args):
        return None


def _run_build(monkeypatch, builder: _FakeBuilder) -> dict:
    """Führt ``build_graph`` synchron aus und gibt das Task-Ergebnis zurück."""
    project = MagicMock()
    project.project_id = PROJECT_ID
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    project.chunk_size = 500
    project.chunk_overlap = 50
    project.ontology = {"entity_types": [], "edge_types": []}
    project.llm_profile_id = None
    project.ai_model_ref = None

    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-1029"

    container = MagicMock()
    container.graph_builder.return_value = builder

    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_extracted_text", lambda _id: "text")
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.services.graph_build.ProjectManager._get_project_dir", lambda _id: "/tmp/project")
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run_1029"},
    )
    monkeypatch.setattr("app.services.graph_build.run_registry.update_run", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr("app.services.graph_build.resolve_route_api_key", lambda *_a: None)
    monkeypatch.setattr("app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.NERExtractor", lambda **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {})
    monkeypatch.setattr("app.services.graph_build.TextProcessor.split_text", lambda *_a, **_k: ["c1", "c2"])
    # Der Task läuft synchron statt über die Queue — sonst prüft der Test nur,
    # dass etwas eingereiht wurde, nicht was es tut.
    monkeypatch.setattr("app.jobs.enqueue", lambda _name, fn: fn())

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Degradation graph",
        container=container,
    )

    completed = [
        c
        for c in task_manager.update_task.call_args_list
        if c.kwargs.get("status") == TaskStatus.COMPLETED
    ]
    assert completed, "Der produktive Build-Pfad hat den Task nie abgeschlossen"
    return completed[-1].kwargs["result"]


def test_production_build_path_reports_embedding_and_graph_degradations(monkeypatch):
    """Embedding-Ausfall und kantenloser Graph landen im Task-Ergebnis."""

    def effect(degradations, extraction_tally):
        degradations.record(
            kind=DegradationKind.EMBEDDING_UNAVAILABLE,
            severity=DegradationSeverity.WARNING,
            detail="Embedding-Dienst nicht erreichbar.",
            context={"affected_texts": 12},
        )
        extraction_tally.record_chunk(entity_count=1, relation_count=0)
        extraction_tally.record_chunk(entity_count=0, relation_count=0)

    result = _run_build(
        monkeypatch,
        _FakeBuilder(node_count=2, edge_count=0, batch_effect=effect),
    )

    report = result["degradations"]
    kinds = {event["kind"] for event in report["events"]}
    assert DegradationKind.EMBEDDING_UNAVAILABLE.value in kinds
    assert DegradationKind.GRAPH_BELOW_THRESHOLD.value in kinds
    assert any(
        event["severity"] == DegradationSeverity.BLOCKING.value
        for event in report["events"]
    ), "Ein Graph ohne eine einzige Beziehung muss blockierend gemeldet werden"


def test_production_build_path_reports_empty_on_healthy_graph(monkeypatch):
    """Ein gesunder Lauf trägt den Schlüssel — mit leerer Befundliste."""
    result = _run_build(
        monkeypatch,
        _FakeBuilder(node_count=25, edge_count=40),
    )

    assert result["degradations"] == {"schema_version": 1, "events": []}


def test_production_build_path_passes_collector_to_add_text_batches(monkeypatch):
    """Ohne durchgereichten Collector bliebe der ganze Mechanismus wirkungslos.

    Der Fake nimmt ``degradations``/``extraction_tally`` als Pflichtargumente
    entgegen; ein Aufruf ohne sie scheitert hier mit ``TypeError``.
    """
    seen: dict[str, object] = {}

    def effect(degradations, extraction_tally):
        seen["degradations"] = degradations
        seen["tally"] = extraction_tally

    _run_build(
        monkeypatch,
        _FakeBuilder(node_count=25, edge_count=40, batch_effect=effect),
    )

    assert seen["degradations"] is not None
    assert seen["tally"] is not None


@pytest.mark.parametrize(
    ("node_count", "edge_count", "expect_blocking"),
    [(0, 0, True), (2, 0, True), (2, 1, False), (25, 40, False)],
    ids=("empty", "no-relations", "minimal", "healthy"),
)
def test_production_build_path_blocking_threshold(
    monkeypatch, node_count, edge_count, expect_blocking
):
    """Nur fehlende Beziehungen blockieren; dünne Graphen bleiben nutzbar."""
    result = _run_build(monkeypatch, _FakeBuilder(node_count=node_count, edge_count=edge_count))

    blocking = [
        event
        for event in result["degradations"]["events"]
        if event["severity"] == DegradationSeverity.BLOCKING.value
    ]
    assert bool(blocking) is expect_blocking
