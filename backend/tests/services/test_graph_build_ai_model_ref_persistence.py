"""AiModelRef überlebt den Ontology-Run und bindet den Resume-Build (#900).

Auf dem ``ai_model_ref``-Pfad bleiben ``llm_model``/``llm_provider``/
``llm_profile_id`` bewusst leer. Ohne persistierte Referenz verlöre ein
wiederaufgenommener Graph-Build (neuer Tab, verlorene Session) jede Modell- und
Connection-Bindung.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.contracts.ai_provider_contract import AiModelRef
from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.services.graph_build import GraphBuildService


PROJECT_ID = "proj_0123456789ab"
CONNECTION_ID = "conn-persisted"
MODEL_ID = "persisted-model"


def _ref() -> AiModelRef:
    return AiModelRef(
        provider_connection_id=CONNECTION_ID,
        model_id=MODEL_ID,
        source="explicit",
    )


class _Router:
    def __init__(self, _run_id):
        pass

    def resolve(self, stage_id):
        return ResolvedRoute(
            stage=stage_id,
            provider_id=CONNECTION_ID,
            model=MODEL_ID,
            routing_version=1,
        )

    def lock_stage(self, *_args):
        return None


@pytest.fixture
def service_env(monkeypatch):
    project = SimpleNamespace(
        project_id=PROJECT_ID,
        name="Persistence project",
        status=ProjectStatus.CREATED,
        graph_id=None,
        graph_build_task_id=None,
        error=None,
        chunk_size=500,
        chunk_overlap=50,
        ontology={"entity_types": [], "edge_types": []},
        analysis_summary=None,
        llm_model=None,
        llm_provider=None,
        llm_profile_id=None,
        ai_model_ref=None,
    )
    save_project = MagicMock()
    seed = MagicMock()
    run_registry = MagicMock()
    run_registry.create_run.side_effect = lambda **kwargs: {
        "run_id": f"run-{kwargs['run_type']}"
    }
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-persisted"

    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_project", lambda _id: project
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.get_extracted_text", lambda _id: "text"
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager._get_project_dir",
        lambda _id: "/tmp/project",
    )
    monkeypatch.setattr(
        "app.services.graph_build.ProjectManager.save_project", save_project
    )
    monkeypatch.setattr("app.services.graph_build.run_registry", run_registry)
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr(
        "app.services.graph_build.LLMClient.from_route",
        lambda *_args, **_kwargs: MagicMock(model=MODEL_ID),
    )
    monkeypatch.setattr(
        "app.services.graph_build.resolve_route_api_key", lambda *_args: None
    )
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {}
    )
    monkeypatch.setattr("app.services.graph_build.NERExtractor", lambda **_kwargs: None)
    monkeypatch.setattr("app.jobs.enqueue", MagicMock())

    generator = MagicMock()
    generator.generate.return_value = {
        "entity_types": ["Person"],
        "edge_types": ["knows"],
        "analysis_summary": "summary",
    }
    monkeypatch.setattr(
        "app.services.graph_build.OntologyGenerator", lambda **_kwargs: generator
    )

    return SimpleNamespace(project=project, seed=seed, save_project=save_project)


def test_generate_ontology_persists_canonical_ai_model_ref(service_env):
    GraphBuildService.generate_ontology(
        project_id=PROJECT_ID,
        simulation_requirement="Analyse the document.",
        document_texts=["document"],
        ai_model_ref=_ref(),
    )

    assert service_env.project.status == ProjectStatus.ONTOLOGY_GENERATED
    assert service_env.project.ai_model_ref == {
        "provider_connection_id": CONNECTION_ID,
        "model_id": MODEL_ID,
        "source": "explicit",
        "capability_filter": None,
        "fallback_reason": None,
    }
    # Legacy-Felder bleiben leer — genau deshalb braucht es das neue Feld.
    assert service_env.project.llm_model is None
    assert service_env.project.llm_provider is None
    assert service_env.project.llm_profile_id is None


def test_generate_ontology_without_ref_leaves_field_empty(service_env):
    GraphBuildService.generate_ontology(
        project_id=PROJECT_ID,
        simulation_requirement="Analyse the document.",
        document_texts=["document"],
        llm_model_override="legacy-model",
    )

    assert service_env.project.ai_model_ref is None
    assert service_env.project.llm_model == "legacy-model"


def test_build_graph_resumes_with_persisted_ai_model_ref(service_env):
    service_env.project.status = ProjectStatus.ONTOLOGY_GENERATED
    service_env.project.ai_model_ref = _ref().model_dump(mode="json")

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Resumed graph",
        container=MagicMock(),
    )

    seeded = service_env.seed.call_args.kwargs["ai_model_ref"]
    assert seeded == _ref()
    assert service_env.seed.call_args.kwargs["llm_model_override"] is None
    assert service_env.seed.call_args.kwargs["llm_profile_id"] is None


def test_build_graph_request_route_wins_over_persisted_ref(service_env):
    service_env.project.status = ProjectStatus.ONTOLOGY_GENERATED
    service_env.project.ai_model_ref = _ref().model_dump(mode="json")

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Explicit legacy graph",
        llm_model_override="request-model",
        container=MagicMock(),
    )

    assert service_env.seed.call_args.kwargs["ai_model_ref"] is None
    assert service_env.seed.call_args.kwargs["llm_model_override"] == "request-model"


def test_build_graph_ignores_corrupt_persisted_ref(service_env):
    service_env.project.status = ProjectStatus.ONTOLOGY_GENERATED
    service_env.project.ai_model_ref = {"provider_connection_id": ""}

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Corrupt ref graph",
        container=MagicMock(),
    )

    assert service_env.seed.call_args.kwargs["ai_model_ref"] is None
