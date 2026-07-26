"""Model-Discovery muss vor Graph-Side-Effects abgeschlossen sein (#897)."""

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
from app.contracts.ai_provider_contract import AiModel, ProviderConnection
from app.services.graph_build import (
    AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
    AiModelRefRoutingInputError,
)
from app.models.project import ProjectStatus
from app.services.llm_routing_seed import prevalidate_ai_model_ref_with_discovery
from app.services.provider_connections.adapters import ProviderProbeResult
from app.storage.graph_storage import GraphStorage


PROJECT_ID = "proj_0123456789ab"
CONNECTION_ID = "conn-discovery"
MODEL_ID = "selected-model"
SECRET_SENTINEL = "sk-discovery-secret-must-not-leak"


def _capture_agora_logs(monkeypatch, caplog) -> None:
    """Macht die ``agora.*``-Logger für caplog sichtbar.

    ``get_logger`` setzt ``propagate = False``; ohne diesen Schalter erreicht
    kein Record den Root-Handler von caplog und jede
    ``SECRET_SENTINEL not in caplog.text``-Prüfung wäre trivial wahr.
    """
    caplog.set_level(logging.DEBUG)
    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if isinstance(candidate, logging.Logger) and (
            name == "agora" or name.startswith("agora.")
        ):
            monkeypatch.setattr(candidate, "propagate", True)
            monkeypatch.setattr(candidate, "level", logging.DEBUG)


@pytest.fixture
def discovery_env(monkeypatch, caplog):
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
        name="Discovery project",
        files=[],
        total_text_length=0,
        ontology={"entity_types": [], "edge_types": []},
        analysis_summary=None,
        simulation_requirement=None,
        llm_model=None,
        graph_build_task_id=None,
        graph_id=None,
        status=None,
        error=None,
    )
    project_manager = MagicMock()
    project_manager.create_project.return_value = project
    project_manager.get_project.return_value = project
    project_manager.save_file_to_project.return_value = {
        "original_filename": "document.txt",
        "path": "/tmp/document.txt",
        "size": 8,
    }
    ontology_service = MagicMock(return_value=project)
    build_service = MagicMock(return_value=("task-1", "run-1"))
    monkeypatch.setattr("app.api.graph_build.ProjectManager", project_manager)
    monkeypatch.setattr(
        "app.api.graph_build.GraphBuildService.generate_ontology", ontology_service
    )
    monkeypatch.setattr(
        "app.api.graph_build.GraphBuildService.build_graph", build_service
    )
    monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery",
        prevalidate_ai_model_ref_with_discovery,
    )
    monkeypatch.setattr(
        "app.api.graph_build.FileParser.extract_text", lambda _path: "document"
    )
    monkeypatch.setattr(
        "app.api.graph_build.TextProcessor.preprocess_text", lambda text: text
    )

    connection = ProviderConnection(
        id=CONNECTION_ID,
        provider_kind="openai_compatible",
        display_name="Discovery gateway",
        transport="http",
        auth_mode="api_key",
        base_url="https://gateway.example/v1",
        secret_ref="configured-secret-ref",
        enabled=True,
    )
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    probe_service = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        lambda: MagicMock(),
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionService",
        lambda **_kwargs: probe_service,
    )
    return SimpleNamespace(
        client=app.test_client(),
        connection=connection,
        probe_service=probe_service,
        project_manager=project_manager,
        ontology_service=ontology_service,
        build_service=build_service,
        monkeypatch=monkeypatch,
        project=project,
    )


def _post(env, endpoint):
    ref = {
        "provider_connection_id": CONNECTION_ID,
        "model_id": MODEL_ID,
        "source": "explicit",
    }
    if endpoint == "ontology":
        return env.client.post(
            "/api/graph/ontology/generate",
            data={
                "simulation_requirement": "Analyse the document.",
                "files": (io.BytesIO(b"document"), "document.txt"),
                "ai_model_ref": json.dumps(ref),
            },
            content_type="multipart/form-data",
        )
    return env.client.post(
        "/api/graph/build", json={"project_id": PROJECT_ID, "ai_model_ref": ref}
    )


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
@pytest.mark.parametrize("failure", ["model_mismatch", "discovery_failure"])
def test_full_model_discovery_rejects_before_any_graph_side_effect(
    discovery_env, caplog, endpoint, failure
):
    if failure == "model_mismatch":
        discovery_env.probe_service.probe.return_value = ProviderProbeResult(
            status="available",
            status_message=None,
            models=(
                AiModel(
                    provider_connection_id=CONNECTION_ID,
                    model_id="other-model",
                    display_name="other-model",
                    source="live",
                    status="available",
                    local_or_cloud="cloud",
                ),
            ),
        )
    else:
        discovery_env.probe_service.probe.return_value = ProviderProbeResult(
            status="invalid_credentials",
            status_message=f"credentials rejected: {SECRET_SENTINEL}",
        )

    response = _post(discovery_env, endpoint)

    assert response.status_code == 400
    discovery_env.probe_service.probe.assert_called_once_with(discovery_env.connection)
    assert SECRET_SENTINEL not in response.get_data(as_text=True)
    assert SECRET_SENTINEL not in caplog.text
    discovery_env.project_manager.create_project.assert_not_called()
    discovery_env.project_manager.get_project.assert_not_called()
    discovery_env.ontology_service.assert_not_called()
    discovery_env.build_service.assert_not_called()


@pytest.mark.parametrize("endpoint", ["ontology", "build"])
def test_seed_race_secret_is_not_exposed_in_response_or_logs(
    discovery_env, caplog, endpoint
):
    # Der Boundary-Typ entscheidet über die 400-Klassifizierung; ein generischer
    # ValueError wäre ein semantischer Fehler und dürfte hier nicht landen.
    race_error = AiModelRefRoutingInputError(
        f"route changed concurrently: {SECRET_SENTINEL}"
    )
    discovery_env.monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery", lambda _ref: None
    )
    service = (
        discovery_env.ontology_service
        if endpoint == "ontology"
        else discovery_env.build_service
    )
    service.side_effect = race_error

    response = _post(discovery_env, endpoint)

    assert SECRET_SENTINEL in str(service.side_effect)
    assert response.status_code == 400
    assert SECRET_SENTINEL not in response.get_data(as_text=True)
    assert SECRET_SENTINEL not in caplog.text


def test_ontology_seed_race_overwrites_divergent_terminal_error(discovery_env):
    """Terminalisiert der Service mit abweichendem Fehlertext, korrigiert der
    API-Layer Status und Meldung auf den kanonischen Endzustand."""
    race_error = AiModelRefRoutingInputError("route changed concurrently")
    discovery_env.monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery", lambda _ref: None
    )

    def fail_after_terminalizing_project(**_kwargs):
        discovery_env.project.status = ProjectStatus.FAILED
        discovery_env.project.error = "routing failed"
        raise race_error

    discovery_env.ontology_service.side_effect = fail_after_terminalizing_project

    response = _post(discovery_env, "ontology")

    assert response.status_code == 400
    assert discovery_env.project.status == ProjectStatus.FAILED
    assert discovery_env.project.error == AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    # Ein save_project stammt aus dem Upload-Pfad vor dem Service-Aufruf, das
    # zweite ist die Korrektur des abweichenden Endzustands.
    assert discovery_env.project_manager.save_project.call_count == 2


def test_ontology_seed_race_is_idempotent_when_service_already_terminalized(
    discovery_env,
):
    """Hat der Service bereits exakt den kanonischen Endzustand gesetzt, darf
    der API-Layer kein zweites Mal speichern (Idempotenz-Bedingung)."""
    race_error = AiModelRefRoutingInputError("route changed concurrently")
    discovery_env.monkeypatch.setattr(
        "app.api.graph_build.prevalidate_ai_model_ref_with_discovery", lambda _ref: None
    )

    def fail_after_terminalizing_project(**_kwargs):
        discovery_env.project.status = ProjectStatus.FAILED
        discovery_env.project.error = AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
        raise race_error

    discovery_env.ontology_service.side_effect = fail_after_terminalizing_project

    response = _post(discovery_env, "ontology")

    assert response.status_code == 400
    assert discovery_env.project.status == ProjectStatus.FAILED
    assert discovery_env.project.error == AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    # Nur der Upload-Pfad speichert; der API-Layer schreibt nicht erneut.
    assert discovery_env.project_manager.save_project.call_count == 1
    discovery_env.project_manager.delete_project.assert_not_called()
