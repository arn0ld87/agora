from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.services.graph_build import GraphBuildService
from app.services.llm_runtime import RuntimeLlmConfig


PROJECT_ID = "proj_0123456789ab"


def test_generate_ontology_profile_routes_document_ingest_and_ontology_stage(monkeypatch):
    """Ein reines Profil muss beide Ontologie-Stages kanonisch routen."""
    project = MagicMock(project_id=PROJECT_ID)
    seed = MagicMock()
    route_client = MagicMock()

    class Router:
        def __init__(self, _run_id):
            pass

        def resolve(self, stage_id):
            return ResolvedRoute(
                stage=stage_id,
                provider_id="openai",
                model="gpt-4.1-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=1,
            )

        def lock_stage(self, *_args):
            return None

    generator = MagicMock()
    generator.generate.return_value = {
        "entity_types": [],
        "edge_types": [],
        "analysis_summary": "ok",
    }
    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run_ontology_profile"},
    )
    monkeypatch.setattr("app.services.graph_build.run_registry.update_run", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", Router)
    monkeypatch.setattr("app.services.graph_build.resolve_route_api_key", lambda *_a: None)
    monkeypatch.setattr("app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: route_client)
    monkeypatch.setattr("app.services.graph_build.OntologyGenerator", lambda **_k: generator)
    monkeypatch.setattr(
        "app.utils.llm_client.build_client_from_profile",
        lambda *_a, **_k: pytest.fail("legacy profile client must not be constructed"),
    )

    GraphBuildService.generate_ontology(
        project_id=PROJECT_ID,
        simulation_requirement="Analyse the document.",
        document_texts=["document"],
        llm_profile_id="profile-openai",
    )

    assert seed.call_args_list == [
        call(
            "run_ontology_profile",
            "document_ingest",
            llm_model_override=None,
            llm_runtime=None,
            llm_profile_id="profile-openai",
        ),
        call(
            "run_ontology_profile",
            "ontology_generation",
            llm_model_override=None,
            llm_runtime=None,
            llm_profile_id="profile-openai",
        ),
    ]


@pytest.mark.parametrize(
    ("model_override", "runtime", "submitted_profile", "expected_profile"),
    [
        (
            "gpt-5-mini",
            RuntimeLlmConfig(provider="openai", api_key="request-key"),
            "profile-submitted",
            "profile-submitted",
        ),
        (None, None, "profile-submitted", "profile-submitted"),
        (None, None, None, "profile-project"),
    ],
    ids=("explicit-route", "submitted-profile", "project-profile"),
)
def test_build_graph_forwards_route_precedence_and_persists_submitted_profile(
    monkeypatch,
    model_override,
    runtime,
    submitted_profile,
    expected_profile,
):
    """Explizite Route, Request-Profil und Projekt-Profil bleiben priorisiert."""
    project = MagicMock()
    project.project_id = PROJECT_ID
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    project.chunk_size = 500
    project.chunk_overlap = 50
    project.ontology = {"entity_types": [], "edge_types": []}
    project.llm_profile_id = "profile-project"
    seed = MagicMock()

    class Router:
        def __init__(self, _run_id):
            pass

        def resolve(self, stage_id):
            return ResolvedRoute(
                stage=stage_id,
                provider_id="openai",
                model=model_override or "gpt-4.1-mini",
                routing_version=1,
            )

        def lock_stage(self, *_args):
            return None

    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-123"
    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_project", lambda _id: project)
    monkeypatch.setattr("app.services.graph_build.ProjectManager.get_extracted_text", lambda _id: "text")
    monkeypatch.setattr("app.services.graph_build.ProjectManager.save_project", lambda _project: None)
    monkeypatch.setattr("app.services.graph_build.ProjectManager._get_project_dir", lambda _id: "/tmp/project")
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.run_registry.create_run",
        lambda **_kwargs: {"run_id": "run_graph_profile"},
    )
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", Router)
    monkeypatch.setattr("app.services.graph_build.resolve_route_api_key", lambda *_a: None)
    monkeypatch.setattr("app.services.graph_build.LLMClient.from_route", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.NERExtractor", lambda **_k: MagicMock())
    monkeypatch.setattr("app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {})
    monkeypatch.setattr("app.jobs.enqueue", lambda *_a, **_k: None)

    GraphBuildService.build_graph(
        project_id=PROJECT_ID,
        graph_name="Contract graph",
        llm_model_override=model_override,
        llm_runtime=runtime,
        llm_profile_id=submitted_profile,
        container=MagicMock(),
    )

    assert seed.call_args.kwargs["llm_profile_id"] == expected_profile
    if submitted_profile is not None:
        assert project.llm_profile_id == submitted_profile
