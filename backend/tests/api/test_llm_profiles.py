"""Minimal API-Tests fuer /api/settings/llm-profiles (P5.2)."""
from __future__ import annotations

import pytest
from flask import Flask

from app.api.llm_profiles import llm_profiles_bp
from app.services.llm_profiles_store import get_llm_profiles_store


@pytest.fixture(autouse=True)
def _reset_store():
    get_llm_profiles_store().reset_for_tests()
    yield
    get_llm_profiles_store().reset_for_tests()


@pytest.fixture
def app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.register_blueprint(llm_profiles_bp, url_prefix="/api/settings/llm-profiles")
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app: Flask):
    return app.test_client()


_PROFILE = {
    "name": "Test-Ollama",
    "provider": "ollama",
    "base_url": "http://localhost:11434/v1",
    "model_name": "qwen2.5:32b",
    "api_key": "",
    "is_default": True,
}


def test_list_returns_bootstrap_profile(client, monkeypatch):
    # Bootstrap erfolgt nur, wenn LLM_MODEL_NAME nicht-leer ist. Vorher hat der
    # Store stillschweigend ein Profil mit `qwen2.5:32b` erzeugt — was in
    # Cloud-Setups dead-on-arrival war.
    monkeypatch.setenv("LLM_MODEL_NAME", "qwen2.5:32b")
    res = client.get("/api/settings/llm-profiles/")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data["data"]["profiles"]) >= 1


def test_list_returns_empty_when_no_model_env(client, monkeypatch):
    # P5.3-Fix: ohne LLM_MODEL_NAME wird KEIN Auto-Profil mehr erzeugt.
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    res = client.get("/api/settings/llm-profiles/")
    assert res.status_code == 200
    data = res.get_json()
    assert data["data"]["profiles"] == []


def test_create_and_list(client):
    res = client.post("/api/settings/llm-profiles/", json=_PROFILE)
    assert res.status_code == 201
    created = res.get_json()["data"]
    assert created["name"] == "Test-Ollama"
    assert created["api_key"] == ""  # niemals zuruckgeben


def test_delete_profile(client):
    res = client.post("/api/settings/llm-profiles/", json=_PROFILE)
    pid = res.get_json()["data"]["id"]
    del_res = client.delete(f"/api/settings/llm-profiles/{pid}")
    assert del_res.status_code == 200
    assert del_res.get_json()["data"]["deleted"] == pid


def test_set_default_not_found(client):
    res = client.post("/api/settings/llm-profiles/nonexistent/default")
    assert res.status_code == 404
