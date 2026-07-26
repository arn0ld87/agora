"""AiModelRef-Vertrag der beiden Graph-Erzeugungsendpunkte (#897)."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import graph_bp
from app.container import AgoraContainer
from app.storage.graph_storage import GraphStorage


PROJECT_ID = "proj_0123456789ab"
CONNECTION_ID = "conn-minimax"
MODEL_ID = "MiniMax-M3"
SECRET_SENTINEL = "sk-test-secret-must-not-leak"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "")
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
    return app.test_client()


@pytest.fixture
def graph_route_env(monkeypatch):
    observed: dict[str, object] = {
        "events": [],
        "prevalidated_ref": None,
        "ontology_kwargs": None,
        "build_kwargs": None,
    }
    project = SimpleNamespace(
        project_id=PROJECT_ID,
        name="Route project",
        files=[],
        total_text_length=0,
        ontology={"entity_types": [], "edge_types": []},
        analysis_summary="ok",
        simulation_requirement=None,
        llm_model=None,
        llm_provider=None,
        llm_profile_id=None,
        graph_build_task_id=None,
        graph_id=None,
    )
    project_manager = MagicMock()

    def create_project(*, name):
        observed["events"].append("create_project")
        project.name = name
        return project

    project_manager.create_project.side_effect = create_project
    project_manager.get_project.return_value = project
    project_manager.save_file_to_project.return_value = {
        "original_filename": "document.txt",
        "path": "/tmp/document.txt",
        "size": 13,
    }

    file_parser = MagicMock()
    file_parser.extract_text.return_value = "document body"
    text_processor = MagicMock()
    text_processor.preprocess_text.return_value = "document body"

    def generate_ontology(**kwargs):
        observed["events"].append("generate_ontology")
        observed["ontology_kwargs"] = kwargs
        return project

    def build_graph(**kwargs):
        observed["events"].append("build_graph")
        observed["build_kwargs"] = kwargs
        return "task_graph_1", "run_graph_1"

    def prevalidate(ai_model_ref):
        observed["events"].append("prevalidate")
        observed["prevalidated_ref"] = ai_model_ref
        return MagicMock(name="ValidatedProviderConnection")

    monkeypatch.setattr("app.api.graph_build.ProjectManager", project_manager)
    monkeypatch.setattr("app.api.graph_build.FileParser", file_parser)
    monkeypatch.setattr("app.api.graph_build.TextProcessor", text_processor)
    monkeypatch.setattr(
        "app.api.graph_build.GraphBuildService.generate_ontology", generate_ontology
    )
    monkeypatch.setattr("app.api.graph_build.GraphBuildService.build_graph", build_graph)
    monkeypatch.setattr(
        "app.services.llm_routing_seed.prevalidate_ai_model_ref_with_discovery",
        prevalidate,
    )
    monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery",
        prevalidate,
    )
    return SimpleNamespace(
        observed=observed,
        project=project,
        project_manager=project_manager,
        monkeypatch=monkeypatch,
    )


def _ref_payload(connection_id: str = CONNECTION_ID) -> dict[str, str]:
    return {
        "provider_connection_id": connection_id,
        "model_id": MODEL_ID,
        "source": "explicit",
    }


def _post_ontology(client, *, ai_model_ref=None, **extra):
    data = {
        "simulation_requirement": "Discuss climate policy.",
        "files": (io.BytesIO(b"document body"), "document.txt"),
        "ai_model_ref": json.dumps(ai_model_ref or _ref_payload()),
        **extra,
    }
    return client.post(
        "/api/graph/ontology/generate", data=data, content_type="multipart/form-data"
    )


def _post_build(client, *, ai_model_ref=None, **extra):
    return client.post(
        "/api/graph/build",
        json={"project_id": PROJECT_ID, "ai_model_ref": ai_model_ref or _ref_payload(), **extra},
    )


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
def test_valid_ai_model_ref_is_prevalidated_and_forwarded(
    client, graph_route_env, endpoint
):
    response = (
        _post_ontology(client) if endpoint == "ontology" else _post_build(client)
    )

    assert response.status_code == 200, response.get_json()
    prevalidated = graph_route_env.observed["prevalidated_ref"]
    assert prevalidated.provider_connection_id == CONNECTION_ID
    assert prevalidated.model_id == MODEL_ID
    kwargs = graph_route_env.observed[f"{endpoint}_kwargs"]
    forwarded = kwargs["ai_model_ref"]
    assert forwarded.provider_connection_id == CONNECTION_ID
    assert forwarded.model_id == MODEL_ID
    assert kwargs["llm_model_override"] is None
    assert kwargs["llm_profile_id"] is None
    assert graph_route_env.observed["events"][0] == "prevalidate"


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
@pytest.mark.parametrize(
    ("legacy_field", "ontology_value", "build_value"),
    [
        ("llm_model", "gpt-4o-mini", "gpt-4o-mini"),
        ("llm_profile_id", "profile-legacy", "profile-legacy"),
        (
            "llm_provider",
            json.dumps({"provider": "openai"}),
            {"provider": "openai"},
        ),
        (
            "llm_runtime",
            json.dumps({"provider": "openai"}),
            {"provider": "openai"},
        ),
    ],
)
def test_ai_model_ref_conflicts_with_every_legacy_route_field(
    client,
    graph_route_env,
    endpoint,
    legacy_field,
    ontology_value,
    build_value,
):
    response = (
        _post_ontology(client, **{legacy_field: ontology_value})
        if endpoint == "ontology"
        else _post_build(client, **{legacy_field: build_value})
    )

    assert response.status_code == 400
    assert "ai_model_ref" in response.get_data(as_text=True)
    assert graph_route_env.observed["ontology_kwargs"] is None
    assert graph_route_env.observed["build_kwargs"] is None
    graph_route_env.project_manager.create_project.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
@pytest.mark.parametrize(
    ("legacy_field", "ontology_value", "build_value"),
    [
        ("llm_model", "", ""),
        ("llm_profile_id", "", ""),
        ("llm_provider", "{}", {}),
        ("llm_runtime", "{}", {}),
    ],
)
def test_ai_model_ref_conflicts_with_present_but_empty_legacy_field(
    client, graph_route_env, endpoint, legacy_field, ontology_value, build_value
):
    response = (
        _post_ontology(client, **{legacy_field: ontology_value})
        if endpoint == "ontology"
        else _post_build(client, **{legacy_field: build_value})
    )

    assert response.status_code == 400
    assert "ai_model_ref" in response.get_data(as_text=True)
    assert graph_route_env.observed["ontology_kwargs"] is None
    assert graph_route_env.observed["build_kwargs"] is None
    graph_route_env.project_manager.create_project.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
def test_malformed_ai_model_ref_returns_400_without_side_effect_or_input_echo(
    client, graph_route_env, endpoint
):
    if endpoint == "ontology":
        response = _post_ontology(client, ai_model_ref={"model_id": SECRET_SENTINEL})
    else:
        response = _post_build(client, ai_model_ref={"model_id": SECRET_SENTINEL})

    assert response.status_code == 400
    assert "ai_model_ref" in response.get_data(as_text=True)
    assert SECRET_SENTINEL not in response.get_data(as_text=True)
    assert graph_route_env.observed["ontology_kwargs"] is None
    assert graph_route_env.observed["build_kwargs"] is None
    graph_route_env.project_manager.create_project.assert_not_called()
    assert graph_route_env.project.graph_build_task_id is None
    assert graph_route_env.project.graph_id is None


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
def test_unknown_connection_returns_400_without_orphan_side_effects_or_secret_leak(
    client, graph_route_env, endpoint
):
    def reject_unknown_connection(_ref):
        raise ValueError("ProviderConnection 'conn-missing' nicht gefunden")

    graph_route_env.monkeypatch.setattr(
        "app.services.llm_routing_seed.prevalidate_ai_model_ref_with_discovery",
        reject_unknown_connection,
    )
    graph_route_env.monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery",
        reject_unknown_connection,
    )

    response = (
        _post_ontology(client, ai_model_ref=_ref_payload("conn-missing"))
        if endpoint == "ontology"
        else _post_build(client, ai_model_ref=_ref_payload("conn-missing"))
    )

    assert response.status_code == 400
    assert "ProviderConnection" in response.get_data(as_text=True)
    assert SECRET_SENTINEL not in response.get_data(as_text=True)
    assert graph_route_env.observed["ontology_kwargs"] is None
    assert graph_route_env.observed["build_kwargs"] is None
    assert graph_route_env.project.graph_build_task_id is None
    assert graph_route_env.project.graph_id is None
