"""Filter und Sortierung für /api/simulation/available-models.

Why: User-Bericht 2026-05-16 — Dashboard-Modellauswahl listet halluzinierte
Ollama-Presets (z. B. ``qwen2.5:32b`` ohne lokalen Install) und die echten
Ollama-Tags erscheinen in zufälliger Reihenfolge.

- Ollama-Models werden alphabetisch sortiert
- LLM_MODEL_PRESETS mit ``kind="ollama"`` werden gegen Ollama-Tags gefiltert
- Cloud-Presets (``kind="cloud"``) bleiben unverändert
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from app.api import simulation_bp
from app.config import Config


@pytest.fixture
def app(monkeypatch):
    # Auth-Guard auf open-mode für Test
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    flask_app = Flask(__name__)
    from app.utils.api_responses import install_api_error_handlers

    install_api_error_handlers(flask_app)
    flask_app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    flask_app.config["TESTING"] = True
    flask_app.config["AGORA_AUTH_TOKEN"] = ""
    # Minimal-Extensions für get_available_models (neo4j_storage darf None sein)
    flask_app.extensions["neo4j_storage"] = None
    flask_app.extensions["neo4j_storage_error"] = None
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _fake_ollama_tags(*names):
    return {"models": [{"name": n, "details": {"family": "test"}} for n in names]}


def test_ollama_models_sorted_alphabetically(client):
    fake_tags = _fake_ollama_tags("zebra:7b", "alpha:13b", "mistral:7b")
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: fake_tags
        resp = client.get("/api/simulation/available-models")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    names = [m["name"] for m in data["ollama"]]
    assert names == ["alpha:13b", "mistral:7b", "zebra:7b"]


def test_ollama_preset_filtered_when_not_installed(client, monkeypatch):
    monkeypatch.setattr(
        Config,
        "LLM_MODEL_PRESETS",
        [
            {"name": "qwen2.5:32b", "label": "Qwen 2.5 32B (lokal)", "kind": "ollama"},
            {"name": "llama3.1:8b", "label": "Llama 3.1 8B", "kind": "ollama"},
        ],
    )
    fake_tags = _fake_ollama_tags("llama3.1:8b")
    with patch("requests.get") as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: fake_tags
        resp = client.get("/api/simulation/available-models")
    data = resp.get_json()["data"]
    preset_names = [p["name"] for p in data["presets"]]
    assert "qwen2.5:32b" not in preset_names
    assert "llama3.1:8b" in preset_names


def test_cloud_preset_always_passes_through(client, monkeypatch):
    monkeypatch.setattr(
        Config,
        "LLM_MODEL_PRESETS",
        [
            {"name": "qwen3-coder-next:cloud", "label": "Qwen3 Coder", "kind": "cloud"},
            {"name": "qwen2.5:32b", "label": "Qwen 2.5 32B", "kind": "ollama"},
        ],
    )
    # Ollama unreachable
    with patch("requests.get", side_effect=ConnectionError("boom")):
        resp = client.get("/api/simulation/available-models")
    data = resp.get_json()["data"]
    preset_names = [p["name"] for p in data["presets"]]
    assert "qwen3-coder-next:cloud" in preset_names
    # Ollama-Preset gefiltert, weil keine Tags abrufbar
    assert "qwen2.5:32b" not in preset_names


def test_ollama_unreachable_returns_empty_list(client):
    with patch("requests.get", side_effect=ConnectionError("boom")):
        resp = client.get("/api/simulation/available-models")
    data = resp.get_json()["data"]
    assert data["ollama"] == []
    assert data["ollama_reachable"] is False
    assert data["ollama_error"]


def test_model_catalog_ollama_fallback_is_empty():
    """ModelCatalogService._get_fallbacks darf für ollama_cloud keine halluzinierten Modelle liefern."""
    from app.services.model_catalog_service import ModelCatalogService

    svc = ModelCatalogService()
    assert svc._get_fallbacks("ollama_cloud") == []
