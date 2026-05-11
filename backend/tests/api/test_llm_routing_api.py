import pytest
from unittest.mock import patch
from flask import Flask
from app.api import llm_bp, runs_bp

@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    app.register_blueprint(runs_bp, url_prefix="/api/runs")
    app.config["TESTING"] = True
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_list_providers(client):
    with patch("app.api.llm_providers.provider_registry.get_providers") as mock_get:
        mock_get.return_value = []
        resp = client.get("/api/llm/providers")
        assert resp.status_code == 200
        assert resp.json["success"] is True

@patch("app.api.llm_providers.model_catalog.get_models")
def test_list_provider_models(mock_get_models, client):
    mock_get_models.return_value = []
    resp = client.get("/api/llm/providers/ollama_local/models")
    assert resp.status_code == 200

def test_get_run_llm_routing(client):
    with (
        patch("app.api.llm_routing.run_registry.get_run", return_value={"status": "processing"}),
        patch("app.services.runtime_run_config.RuntimeRunConfig.load_config") as mock_load,
    ):
        from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
        mock_load.return_value = RuntimeLlmRouting(
            default_route=StageLLMRoute(provider_id="o", model="m")
        )
        resp = client.get("/api/runs/run_abcdef012345/llm-routing")
        assert resp.status_code == 200
        assert "runtime_config" in resp.json["data"]

def test_patch_stage_llm_routing_locked(client):
    with (
        patch("app.api.llm_routing.run_registry.get_run", return_value={"status": "processing"}),
        patch("app.services.runtime_run_config.RuntimeRunConfig.load_stage_snapshot") as mock_snap,
    ):
        mock_snap.return_value = {"locked": True}
        resp = client.patch("/api/runs/run_abcdef012345/llm-routing/stages/graph_build", json={})
        assert resp.status_code == 409
        assert resp.json["code"] == "stage_already_started"


def test_get_run_llm_routing_rejects_entity_id(client):
    resp = client.get("/api/runs/proj_abcdef012345/llm-routing")
    assert resp.status_code == 400


def test_get_run_llm_routing_requires_existing_run(client):
    with patch("app.api.llm_routing.run_registry.get_run", return_value=None):
        resp = client.get("/api/runs/run_abcdef012345/llm-routing")
    assert resp.status_code == 404
