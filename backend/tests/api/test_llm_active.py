import pytest
from unittest.mock import patch
from flask import Flask
from app.api import llm_bp
from app.contracts.llm_routing_contract import ModelEntry

@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    from app.utils.api_responses import install_api_error_handlers
    install_api_error_handlers(app)
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    app.config["TESTING"] = True
    app.config["AGORA_AUTH_TOKEN"] = ""
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_rejects_non_tool_model(client):
    """Test that PUT /api/llm/active-config rejects models without tool support."""
    fake_models = [
        ModelEntry(
            id="broken-model",
            name="Broken Model",
            provider_id="ollama_cloud",
            source="live",
            refreshed_at=0.0,
            supports_tools=False
        ),
        ModelEntry(
            id="good-model",
            name="Good Model",
            provider_id="ollama_cloud",
            source="live",
            refreshed_at=0.0,
            supports_tools=True
        )
    ]

    with patch("app.api.llm_active._model_catalog.get_models") as mock_get_models, \
         patch("app.api.llm_active.save_active_config") as mock_save, \
         patch("app.api.llm_active.SecretResolver.get_api_key") as mock_key:

        mock_get_models.return_value = fake_models
        mock_key.return_value = "dummy"
        mock_save.return_value = {"provider_id": "ollama_cloud", "model": "good-model"}

        # 1. Reject broken model
        resp = client.put("/api/llm/active-config", json={
            "provider_id": "ollama_cloud",
            "model": "broken-model"
        })
        assert resp.status_code == 422
        assert resp.json["code"] == "unsupported_capability"
        mock_save.assert_not_called()

        # 2. Allow good model
        resp = client.put("/api/llm/active-config", json={
            "provider_id": "ollama_cloud",
            "model": "good-model"
        })
        assert resp.status_code == 200
        assert resp.json["success"] is True
        mock_save.assert_called_once()
        mock_save.reset_mock()

        # 3. Bypass with force=true
        resp = client.put("/api/llm/active-config?force=true", json={
            "provider_id": "ollama_cloud",
            "model": "broken-model"
        })
        assert resp.status_code == 200
        assert resp.json["success"] is True
        mock_save.assert_called_once()

def test_unknown_model_passes_gate(client):
    """Unknown models (not in catalog) pass the gate (fail-safe)."""
    with patch("app.api.llm_active._model_catalog.get_models") as mock_get_models, \
         patch("app.api.llm_active.save_active_config") as mock_save:

        mock_get_models.return_value = []
        mock_save.return_value = {"provider_id": "openai", "model": "some-new-model"}

        resp = client.put("/api/llm/active-config", json={
            "provider_id": "openai",
            "model": "some-new-model"
        })
        assert resp.status_code == 200
        mock_save.assert_called_once()
