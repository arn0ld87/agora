"""Service-Vertrag für AiModelRef an allen Graph-Stage-Seeds (#897)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.contracts.ai_provider_contract import AiModelRef
from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.services.graph_build import GraphBuildService


PROJECT_ID = "proj_0123456789ab"
MODEL_ID = "shared-model-id"


class _Router:
    connection_id = ""

    def __init__(self, _run_id):
        pass

    def resolve(self, stage_id):
        return ResolvedRoute(
            stage=stage_id,
            provider_id=self.connection_id,
            model=MODEL_ID,
            routing_version=1,
        )

    def lock_stage(self, *_args):
        return None


def _ref(connection_id: str) -> AiModelRef:
    return AiModelRef(
        provider_connection_id=connection_id,
        model_id=MODEL_ID,
        source="explicit",
    )


@pytest.mark.parametrize("connection_id", ["conn-alpha", "conn-beta"])
def test_ontology_forwards_exact_ref_to_both_stage_seeds(monkeypatch, connection_id):
    project = MagicMock(project_id=PROJECT_ID)
    seed = MagicMock()
    generator = MagicMock()
    generator.generate.return_value = {
        "entity_types": [],
        "edge_types": [],
        "analysis_summary": "ok",
    }
    _Router.connection_id = connection_id
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_project", lambda _id: project
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.save_project", lambda _project: None
    )
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run-ontology-ref"},
    )
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.update_run", lambda *_a, **_k: None
    )
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr(
        "app.services.graph_build.resolve_route_api_key", lambda *_a: None
    )
    monkeypatch.setattr(
        "app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock()
    )
    monkeypatch.setattr(
        "app.services.graph_build.OntologyGenerator", lambda **_k: generator
    )
    selected_ref = _ref(connection_id)

    GraphBuildService.generate_ontology(
        project_id=PROJECT_ID,
        simulation_requirement="Analyse the document.",
        document_texts=["document"],
        ai_model_ref=selected_ref,
    )

    expected_kwargs = {
        "llm_model_override": None,
        "llm_runtime": None,
        "llm_profile_id": None,
        "ai_model_ref": selected_ref,
    }
    assert seed.call_args_list == [
        call("run-ontology-ref", "document_ingest", **expected_kwargs),
        call("run-ontology-ref", "ontology_generation", **expected_kwargs),
    ]


@pytest.mark.parametrize("connection_id", ["conn-alpha", "conn-beta"])
def test_graph_build_forwards_exact_ref_to_graph_stage_seed(monkeypatch, connection_id):
    project = MagicMock()
    project.project_id = PROJECT_ID
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    project.chunk_size = 500
    project.chunk_overlap = 50
    project.ontology = {"entity_types": [], "edge_types": []}
    project.llm_profile_id = "legacy-profile"
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-ref"
    seed = MagicMock()
    _Router.connection_id = connection_id
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_project", lambda _id: project
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_extracted_text", lambda _id: "text"
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.save_project", lambda _project: None
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager._get_project_dir", lambda _id: "/tmp/project"
    )
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run-graph-ref"},
    )
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr(
        "app.services.graph_build.resolve_route_api_key", lambda *_a: None
    )
    monkeypatch.setattr(
        "app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock()
    )
    monkeypatch.setattr(
        "app.services.graph_build.NERExtractor", lambda **_k: MagicMock()
    )
    monkeypatch.setattr(
        "app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {}
    )
    monkeypatch.setattr("app.jobs.enqueue", lambda *_a, **_k: None)
    selected_ref = _ref(connection_id)

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Contract graph",
        container=MagicMock(),
        ai_model_ref=selected_ref,
    )

    seed.assert_called_once_with(
        "run-graph-ref",
        "graph_build",
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        ai_model_ref=selected_ref,
    )
