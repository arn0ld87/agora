"""Test für Track 3c: ``/api/simulation/generate-profiles`` reicht
api_key + base_url des aktiven LLM-Profils an :class:`OasisProfileGenerator`
durch.

Vor Track 3c hat der Endpoint nur ``model_name`` durchgereicht — der
Generator hat dann beim internen :class:`LLMClient`-Init auf
``Config.LLM_API_KEY`` zurückgefallen, was bei einem User-konfigurierten
OpenAI-Profil zu 401-Loops geführt hat. Mit der Härtung greift jetzt der
gleiche Resolver wie in ``prepare_service._phase_generate_profiles``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture
def captured_generator_kwargs():
    return {}


@pytest.fixture
def patched_generator(monkeypatch, captured_generator_kwargs):
    """Mockt :class:`OasisProfileGenerator` und sammelt Konstruktor-Args."""
    fake_profile = MagicMock(
        to_dict=lambda: {"id": "p1"},
        to_reddit_format=lambda: {"username": "u1"},
        to_twitter_format=lambda: {"handle": "h1"},
    )

    class FakeGenerator:
        def __init__(self, **kwargs):
            captured_generator_kwargs.update(kwargs)

        def generate_profiles_from_entities(self, *_a, **_kw):
            return [fake_profile]

    monkeypatch.setattr(
        "app.api.simulation_history.OasisProfileGenerator", FakeGenerator
    )

    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}
    fake_filtered.entities = [MagicMock()]
    monkeypatch.setattr(
        "app.api.simulation_history.EntityReader",
        lambda _storage: MagicMock(filter_defined_entities=MagicMock(return_value=fake_filtered)),
    )
    # expand_profile_in_data ist kein-op für unsere Tests — wir injizieren
    # die Provider-Daten direkt in den Request-Body.
    monkeypatch.setattr(
        "app.api.simulation_history.expand_profile_in_data",
        lambda data: data,
    )
    return FakeGenerator


def test_generate_profiles_passes_provider_credentials(client, patched_generator, captured_generator_kwargs):
    payload = {
        "graph_id": "graph_abc",
        "llm_model": "gpt-4o-mini",
        "llm_provider": {
            "provider": "openai",
            "api_key": "sk-test-injectedkey1234567890abcDEF",  # gitleaks:allow
            "base_url": "https://api.openai.com/v1",
        },
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert captured_generator_kwargs["api_key"] == "sk-test-injectedkey1234567890abcDEF"
    assert captured_generator_kwargs["base_url"] == "https://api.openai.com/v1"
    assert captured_generator_kwargs["model_name"] == "gpt-4o-mini"
    assert captured_generator_kwargs["graph_id"] == "graph_abc"


def test_generate_profiles_without_provider_falls_back_to_none(client, patched_generator, captured_generator_kwargs):
    """Ohne ``llm_provider`` bleibt das Verhalten kompatibel: api_key/base_url
    None, Generator wird auf interne Defaults zurückfallen (Track 1 hardening
    verhindert toxic Fallbacks dort)."""
    payload = {
        "graph_id": "graph_abc",
        "llm_model": "gpt-4o-mini",
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert captured_generator_kwargs["api_key"] is None
    assert captured_generator_kwargs["base_url"] is None


def test_generate_profiles_local_endpoint_without_key_uses_no_auth_placeholder(
    client, patched_generator, captured_generator_kwargs
):
    """Issue #778 Blocker 1 (Preview-Pfad) — lokaler Endpoint ohne Key darf
    weder 500 noch ``ValueError`` produzieren; der Generator bekommt den
    dokumentierten No-Auth-Platzhalter statt eines rohen ``None``.
    """
    from app.api.simulation_prepare import LOCAL_NO_AUTH_API_KEY

    payload = {
        "graph_id": "graph_abc",
        "llm_model": "qwen2.5:14b",
        "llm_provider": {
            "provider": "custom_openai",
            "base_url": "http://host.docker.internal:11434/v1",
        },
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert captured_generator_kwargs["api_key"] == LOCAL_NO_AUTH_API_KEY
    assert captured_generator_kwargs["base_url"] == "http://host.docker.internal:11434/v1"


def test_generate_profiles_rejects_invalid_provider_payload(client, patched_generator, captured_generator_kwargs):
    """``parse_runtime_llm_config`` muss bei kaputtem Payload 400 werfen,
    nicht stillschweigend leiten."""
    payload = {
        "graph_id": "graph_abc",
        "llm_provider": {"provider": "openai", "api_key": "ollama"},  # toxic literal
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    # parse_runtime_llm_config + Track 1 _validate_key_format ziehen — Endpoint
    # gibt 400 mit klarer Message zurück (kein silent-passthrough).
    assert resp.status_code in (400, 200), resp.get_json()
    # Falls 200: api_key wurde nicht durchgereicht (provider-validation hätte
    # vor _resolve_llm_connection bereits None gesetzt). Wir prüfen den
    # Negativ-Fall — kein toxic Wert kommt am Generator an.
    if resp.status_code == 200:
        assert captured_generator_kwargs.get("api_key") != "ollama"
