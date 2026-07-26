"""Terminalisierung synchroner Graph-Fehler nach erfolgreichem Routing-Seed."""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.contracts.llm_routing_contract import ResolvedRoute
from app.models.project import ProjectStatus
from app.services.graph_build import (
    AI_MODEL_REF_GENERATION_FAILURE_MESSAGE,
    AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
)
from app.storage.graph_storage import GraphStorage


PROJECT_ID = "proj_0123456789ab"
SECRET_SENTINEL = "sk-post-seed-secret-must-not-leak"


class _Router:
    def __init__(self, _run_id):
        pass

    def resolve(self, stage_id):
        return ResolvedRoute(
            stage=stage_id,
            provider_id="conn-post-seed",
            model="post-seed-model",
            routing_version=1,
        )

    def lock_stage(self, *_args):
        return None


def _capture_agora_logs(monkeypatch, caplog) -> None:
    """Macht die ``agora.*``-Logger für caplog sichtbar.

    ``get_logger`` setzt ``propagate = False``, deshalb erreicht kein Record den
    Root-Handler, an dem caplog hängt — ohne diesen Schalter wäre jede
    ``SECRET_SENTINEL not in caplog.text``-Zusicherung gegen ein leeres caplog
    trivial wahr. DEBUG-Level, damit auch INFO/DEBUG-Records erfasst werden.
    """
    caplog.set_level(logging.DEBUG)
    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if isinstance(candidate, logging.Logger) and (
            name == "agora" or name.startswith("agora.")
        ):
            monkeypatch.setattr(candidate, "propagate", True)
            monkeypatch.setattr(candidate, "level", logging.DEBUG)


@pytest.fixture
def post_seed_env(monkeypatch, caplog):
    _capture_agora_logs(monkeypatch, caplog)
    storage = MagicMock(spec=GraphStorage)
    app = Flask(__name__)
    app.config.update(
        AGORA_AUTH_TOKEN="",
        AGORA_UPLOAD_RATE_LIMIT_MAX=1000,
        AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS=60,
    )
    app.extensions = {
        "container": AgoraContainer(neo4j_storage=storage),
        "neo4j_storage": storage,
    }
    app.register_blueprint(graph_bp, url_prefix="/api/graph")

    project = SimpleNamespace(
        project_id=PROJECT_ID,
        name="Post-seed project",
        files=[],
        total_text_length=0,
        ontology={"entity_types": [], "edge_types": []},
        analysis_summary=None,
        simulation_requirement=None,
        status=ProjectStatus.ONTOLOGY_GENERATED,
        error=None,
        graph_id=None,
        graph_build_task_id=None,
        chunk_size=500,
        chunk_overlap=50,
        llm_model=None,
        llm_provider=None,
        llm_profile_id=None,
    )
    project_manager = MagicMock()
    project_manager.create_project.return_value = project
    project_manager.get_project.return_value = project
    project_manager.get_extracted_text.return_value = "document"
    project_manager.save_file_to_project.return_value = {
        "original_filename": "document.txt",
        "path": "/tmp/document.txt",
        "size": 8,
    }
    project_manager._get_project_dir.return_value = "/tmp/project"
    run_registry = MagicMock()
    run_registry.create_run.side_effect = lambda **kwargs: {
        "run_id": f"run-{kwargs['run_type']}"
    }
    seed = MagicMock()
    task_manager = MagicMock()
    task_manager.create_task.return_value = "task-post-seed"

    monkeypatch.setattr("app.api.graph_build.ProjectManager", project_manager)
    monkeypatch.setattr("app.services.graph_build.ProjectManager", project_manager)
    monkeypatch.setattr("app.services.graph_build.run_registry", run_registry)
    monkeypatch.setattr("app.services.graph_build.seed_run_stage_routing", seed)
    monkeypatch.setattr("app.services.graph_build.StageModelRouter", _Router)
    monkeypatch.setattr(
        "app.services.graph_build.resolve_route_api_key", lambda *_args: None
    )
    monkeypatch.setattr(
        "app.services.graph_build.LLMClient.from_route", lambda *_args, **_kwargs: MagicMock(model="post-seed-model")
    )
    monkeypatch.setattr("app.services.graph_build.TaskManager", lambda: task_manager)
    monkeypatch.setattr(
        "app.services.graph_build.ArtifactLocator.existing_paths", lambda _paths: {}
    )
    monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery", lambda _ref: None
    )
    monkeypatch.setattr(
        "app.api.graph_build.FileParser.extract_text", lambda _path: "document"
    )
    monkeypatch.setattr(
        "app.api.graph_build.TextProcessor.preprocess_text", lambda text: text
    )
    return SimpleNamespace(
        client=app.test_client(),
        monkeypatch=monkeypatch,
        project=project,
        project_manager=project_manager,
        run_registry=run_registry,
        seed=seed,
        task_manager=task_manager,
    )


def _ref_payload() -> dict[str, str]:
    return {
        "provider_connection_id": "conn-post-seed",
        "model_id": "post-seed-model",
        "source": "explicit",
    }


def _assert_public_error_is_safe(
    response, caplog, capsys, *, status: int, error: str, code: str
):
    captured = capsys.readouterr()
    assert response.status_code == status
    assert response.status_code != 400
    assert response.get_json() == {
        "success": False,
        "error": error,
        "code": code,
    }
    assert SECRET_SENTINEL not in response.get_data(as_text=True)
    # Die Terminalisierung loggt garantiert eine Warnung — ohne diese Prüfung
    # wäre die Sentinel-Zusicherung gegen ein leeres caplog trivial wahr.
    assert caplog.records
    assert SECRET_SENTINEL not in caplog.text
    assert SECRET_SENTINEL not in captured.out
    assert SECRET_SENTINEL not in captured.err


def test_ontology_post_seed_generation_failure_terminalizes_run_and_project(
    post_seed_env, caplog, capsys
):
    failure = ValueError(f"generator failed with {SECRET_SENTINEL}")
    generator = MagicMock()
    generator.generate.side_effect = failure
    post_seed_env.monkeypatch.setattr(
        "app.services.graph_build.OntologyGenerator", lambda **_kwargs: generator
    )

    response = post_seed_env.client.post(
        "/api/graph/ontology/generate",
        data={
            "simulation_requirement": "Analyse the document.",
            "files": (io.BytesIO(b"document"), "document.txt"),
            "ai_model_ref": json.dumps(_ref_payload()),
        },
        content_type="multipart/form-data",
    )

    assert SECRET_SENTINEL in str(generator.generate.side_effect)
    _assert_public_error_is_safe(
        response,
        caplog,
        capsys,
        status=500,
        error="internal server error",
        code="internal_error",
    )
    assert post_seed_env.seed.call_count == 2
    assert post_seed_env.project.status == ProjectStatus.FAILED
    # Generierungsfehler tragen bewusst *nicht* die Routing-Meldung: das
    # Routing war erfolgreich, gescheitert ist die Ontology-Generierung.
    assert post_seed_env.project.error == AI_MODEL_REF_GENERATION_FAILURE_MESSAGE
    post_seed_env.project_manager.delete_project.assert_not_called()
    failed_run = post_seed_env.run_registry.update_run.call_args
    assert failed_run.args == ("run-ontology_generate",)
    assert failed_run.kwargs["status"] == "failed"


def test_graph_post_seed_enqueue_failure_terminalizes_run_task_and_project(
    post_seed_env, caplog, capsys
):
    failure = RuntimeError(f"enqueue failed with {SECRET_SENTINEL}")

    def fail_enqueue(*_args, **_kwargs):
        raise failure

    post_seed_env.monkeypatch.setattr("app.jobs.enqueue", fail_enqueue)

    response = post_seed_env.client.post(
        "/api/graph/build",
        json={"project_id": PROJECT_ID, "ai_model_ref": _ref_payload()},
    )

    assert SECRET_SENTINEL in str(failure)
    _assert_public_error_is_safe(
        response,
        caplog,
        capsys,
        status=500,
        error="internal server error",
        code="internal_error",
    )
    post_seed_env.seed.assert_called_once()
    assert post_seed_env.project.status == ProjectStatus.FAILED
    assert post_seed_env.project.error == AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    post_seed_env.task_manager.fail_task.assert_called_once_with(
        "task-post-seed", AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    )
    failed_run = post_seed_env.run_registry.update_run.call_args
    assert failed_run.args == ("run-graph_build",)
    assert failed_run.kwargs["status"] == "failed"


def test_graph_create_task_failure_terminalizes_pending_run_without_task(
    post_seed_env, caplog, capsys
):
    failure = RuntimeError(f"task storage failed with {SECRET_SENTINEL}")
    post_seed_env.task_manager.create_task.side_effect = failure

    response = post_seed_env.client.post(
        "/api/graph/build",
        json={"project_id": PROJECT_ID, "ai_model_ref": _ref_payload()},
    )

    assert SECRET_SENTINEL in str(failure)
    _assert_public_error_is_safe(
        response,
        caplog,
        capsys,
        status=500,
        error="internal server error",
        code="internal_error",
    )
    post_seed_env.run_registry.create_run.assert_called_once()
    assert post_seed_env.run_registry.create_run.call_args.kwargs["status"] == "pending"
    post_seed_env.seed.assert_not_called()
    post_seed_env.task_manager.fail_task.assert_not_called()
    assert post_seed_env.project.status == ProjectStatus.FAILED
    assert post_seed_env.project.error == AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    assert post_seed_env.project.graph_build_task_id is None
    failed_run = post_seed_env.run_registry.update_run.call_args
    assert failed_run.args == ("run-graph_build",)
    assert failed_run.kwargs["status"] == "failed"
    assert SECRET_SENTINEL not in str(failed_run)


def test_graph_post_seed_timeout_preserves_gateway_timeout_and_terminalizes_states(
    post_seed_env, caplog, capsys
):
    failure = TimeoutError(f"enqueue timed out with {SECRET_SENTINEL}")

    def fail_enqueue(*_args, **_kwargs):
        raise failure

    post_seed_env.monkeypatch.setattr("app.jobs.enqueue", fail_enqueue)

    response = post_seed_env.client.post(
        "/api/graph/build",
        json={"project_id": PROJECT_ID, "ai_model_ref": _ref_payload()},
    )

    assert SECRET_SENTINEL in str(failure)
    _assert_public_error_is_safe(
        response,
        caplog,
        capsys,
        status=504,
        error="request timed out",
        code="timeout",
    )
    assert post_seed_env.project.status == ProjectStatus.FAILED
    assert post_seed_env.project.error == AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    post_seed_env.task_manager.fail_task.assert_called_once_with(
        "task-post-seed", AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    )
    failed_run = post_seed_env.run_registry.update_run.call_args
    assert failed_run.args == ("run-graph_build",)
    assert failed_run.kwargs["status"] == "failed"
    assert SECRET_SENTINEL not in str(failed_run)
