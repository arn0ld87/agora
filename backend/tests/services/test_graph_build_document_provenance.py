"""Dokument-Provenance im produktiven Build-Pfad (Issue #1152 Slice 1, Teil B).

Nutzt denselben Ansatz wie ``test_graph_build_degradation_wiring.py``: der
``build_task``-Closure aus ``GraphBuildService.build_graph`` wird synchron
über ``app.jobs.enqueue`` ausgeführt, statt eine Nachbildung zu testen — das
ist genau der Pfad, den ``POST /api/graph/build`` in Produktion nimmt.

Spec:
- Ohne Manifest-Sidecar (``ProjectManager.get_document_manifest`` → ``None``,
  der Normalfall für Altprojekte) nimmt der Build unverändert den
  ``TextProcessor.split_text``-Pfad; ``add_text_batches`` bekommt
  ``document_ids=None``/``chunk_ids=None`` (ADR-0013 §3: kein Backfill).
- Mit Manifest-Sidecar chunkt der Build über
  ``split_text_into_chunks_with_documents`` und reicht die Dokument-Provenance
  parallel zu den Chunk-Texten an ``add_text_batches`` durch.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.contracts.document_manifest_contract import DocumentManifest, DocumentManifestEntry
from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.services.graph_build import GraphBuildService
from app.services.graph_builder import GraphBuilderService

PROJECT_ID = "proj_doc_provenance"


class _FakeBuilder:
    assess_graph_quality_from_counts = (
        GraphBuilderService.assess_graph_quality_from_counts
    )

    def __init__(self):
        self.add_text_batches_calls: list[dict] = []

    def create_graph(self, name: str) -> str:
        return "graph-1152"

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
        document_ids,
        chunk_ids,
    ):
        self.add_text_batches_calls.append(
            {
                "chunks": list(chunks),
                "document_ids": document_ids,
                "chunk_ids": chunk_ids,
            }
        )

    def get_graph_data(self, graph_id):
        return {"node_count": 25, "edge_count": 40}

    def mark_graph_completed(self, graph_id) -> None:
        return None


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


def _run_build(monkeypatch, builder: _FakeBuilder, *, manifest: DocumentManifest | None) -> _FakeBuilder:
    """Führt ``build_graph`` synchron aus und gibt den Fake-Builder zurück."""
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
    task_manager.create_task.return_value = "task-1152"

    container = MagicMock()
    container.graph_builder.return_value = builder

    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_extracted_text",
        lambda _id: "Erster Satz. " * 5 + "Zweiter Satz. " * 5,
    )
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.services.graph_build.ProjectManager._get_project_dir", lambda _id: "/tmp/project")
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_document_manifest", lambda _id: manifest
    )
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run_1152"},
    )
    monkeypatch.setattr("app.services.graph_build.run_registry.update_run", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr("app.services.graph_build.resolve_route_api_key", lambda *_a: None)
    monkeypatch.setattr("app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.NERExtractor", lambda **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {})
    monkeypatch.setattr(
        "app.services.graph_build.TextProcessor.split_text", lambda *_a, **_k: ["legacy-chunk-1", "legacy-chunk-2"]
    )
    # Der Task läuft synchron statt über die Queue — sonst prüft der Test nur,
    # dass etwas eingereiht wurde, nicht was es tut.
    monkeypatch.setattr("app.jobs.enqueue", lambda _name, fn: fn())

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Provenance graph",
        container=container,
    )

    return builder


def test_graph_build_without_sidecar_takes_the_legacy_path(monkeypatch):
    """Kein Manifest-Sidecar → unveränderter TextProcessor.split_text-Pfad.

    ``add_text_batches`` bekommt die Legacy-Chunks aus dem gemockten
    ``TextProcessor.split_text`` und ``document_ids``/``chunk_ids`` bleiben
    ``None`` — ADR-0013 §3 verbietet ein Backfill für Altprojekte.
    """
    builder = _run_build(monkeypatch, _FakeBuilder(), manifest=None)

    assert len(builder.add_text_batches_calls) == 1
    call = builder.add_text_batches_calls[0]
    assert call["chunks"] == ["legacy-chunk-1", "legacy-chunk-2"]
    assert call["document_ids"] is None
    assert call["chunk_ids"] is None


def test_graph_build_with_sidecar_forwards_document_provenance(monkeypatch):
    """Manifest-Sidecar vorhanden → dokument-verankerter Chunk-Pfad.

    Die Chunk-Texte kommen aus ``split_text_into_chunks_with_documents``
    statt aus dem gemockten Legacy-``TextProcessor.split_text`` (der in
    diesem Fall unbenutzt bleiben muss), und jeder Chunk trägt seine
    Dokument-Provenance parallel zur Chunk-Liste.
    """
    manifest = DocumentManifest(
        documents=[
            DocumentManifestEntry(
                document_id="report", filename="report.pdf", start_offset=0, end_offset=68
            )
        ]
    )

    builder = _run_build(monkeypatch, _FakeBuilder(), manifest=manifest)

    assert len(builder.add_text_batches_calls) == 1
    call = builder.add_text_batches_calls[0]

    assert call["chunks"] != ["legacy-chunk-1", "legacy-chunk-2"], (
        "Mit Manifest darf der Legacy-Chunk-Pfad nicht greifen"
    )
    assert call["document_ids"] is not None
    assert call["chunk_ids"] is not None
    assert len(call["document_ids"]) == len(call["chunks"])
    assert len(call["chunk_ids"]) == len(call["chunks"])
    assert all(doc_id == "report" for doc_id in call["document_ids"])
    assert call["chunk_ids"] == list(range(len(call["chunk_ids"])))
