import pytest
from unittest.mock import patch
from flask import Flask
from app.api import llm_bp, runs_bp

@pytest.fixture
def app(monkeypatch):
    # _expected_token() reads os.environ directly — clear it so the auth guard
    # stays in open-mode regardless of what .env provides.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    from app.utils.api_responses import install_api_error_handlers
    install_api_error_handlers(app)
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    app.register_blueprint(runs_bp, url_prefix="/api/runs")
    app.config["TESTING"] = True
    app.config["AGORA_AUTH_TOKEN"] = ""
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
    resp = client.get("/api/llm/providers/ollama_cloud/models")
    assert resp.status_code == 200

def test_get_run_llm_routing(client):
    with patch("app.services.runtime_run_config.RuntimeRunConfig.load_config") as mock_load, patch(
        "app.api.llm_routing._load_invocation_events"
    ) as mock_events:
        from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
        mock_load.return_value = RuntimeLlmRouting(
            global_default=StageLLMRoute(provider_id="o", model="m")
        )
        mock_events.return_value = [{"stage": "report_generation", "success": True}]
        resp = client.get("/api/runs/proj_123/llm-routing")
        assert resp.status_code == 200
        assert "runtime_config" in resp.json["data"]
        assert resp.json["data"]["invocation_events"][0]["stage"] == "report_generation"

def test_patch_stage_llm_routing_locked(client):
    with patch("app.services.runtime_run_config.RuntimeRunConfig.load_stage_snapshot") as mock_snap:
        mock_snap.return_value = {"locked": True}
        resp = client.patch("/api/runs/proj_123/llm-routing/stages/graph_build", json={})
        assert resp.status_code == 409
        assert resp.json["code"] == "stage_already_started"
