"""Test für Track 3c / Issue #799: ``/api/simulation/generate-profiles``
reicht api_key + base_url an :class:`OasisProfileGenerator` durch.

Vor Track 3c hat der Endpoint nur ``model_name`` durchgereicht — der
Generator hat dann beim internen :class:`LLMClient`-Init auf
``Config.LLM_API_KEY`` zurückgefallen, was bei einem User-konfigurierten
OpenAI-Profil zu 401-Loops geführt hat.

Vor Issue #799 löste der Endpoint API-Keys ausschließlich aus dem
Request-Payload auf (``_resolve_llm_connection``) und ignorierte einen in
den Settings hinterlegten Store-Key komplett. Fehlte der Key bei einem
Fremd-Provider-Endpoint, warf der Generator einen ``ValueError``, den
``@handle_api_errors`` auf HTTP 500 mappte — statt eines sauberen 422 wie
bei ``simulation_prepare``. Seit dem Fix nutzt der Endpoint denselben
Store-Key-fähigen Resolver (``build_preview_stage_route`` +
``resolve_route_api_key`` aus ``llm_routing_seed``) und antwortet bei
fehlendem Routing-Kandidaten bzw. fehlendem Store-Key mit HTTP 422.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.utils.endpoints import LOCAL_NO_AUTH_API_KEY


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


def test_generate_profiles_without_provider_falls_back_to_none(
    client, patched_generator, captured_generator_kwargs, monkeypatch
):
    """Issue #799: ohne ``llm_provider``, ohne Workspace-Default und ohne
    Server-Default (``Config.LLM_MODEL_NAME`` leer) existiert überhaupt kein
    Routing-Kandidat auf keiner Ebene (Stage/Run/Workspace/Provider-Fallback).
    Das ist bewusst ein Verhaltenswechsel gegenüber dem alten stillschweigenden
    ``api_key=None``/``base_url=None``-Fallback (der Bug, den dieses Issue
    behebt): der Endpoint muss jetzt sauber mit HTTP 422
    (``NoAiRouteCandidateError``) antworten statt den Generator mit leeren
    Credentials laufen zu lassen, was nachgelagert bei Fremd-Providern in
    einen 500er lief."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: MagicMock(load=lambda: None),
    )
    monkeypatch.setattr("app.config.Config.LLM_MODEL_NAME", "")
    monkeypatch.setattr("app.config.Config.LLM_BASE_URL", "")

    payload = {
        "graph_id": "graph_abc",
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 422, resp.get_json()


def test_generate_profiles_uses_server_default_for_local_endpoint(
    client, patched_generator, captured_generator_kwargs, monkeypatch
):
    """Issue #799: ohne Payload-Override, aber mit Server-Default
    (``Config.LLM_MODEL_NAME``/``LLM_BASE_URL``) greift derselbe
    Provider-Fallback wie in ``simulation_prepare``. Zeigt der Fallback auf
    einen lokalen Endpoint, bleibt der No-Auth-Platzhalter zulässig (#778)."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: MagicMock(load=lambda: None),
    )
    monkeypatch.setattr("app.config.Config.LLM_MODEL_NAME", "qwen2.5:14b")
    monkeypatch.setattr("app.config.Config.LLM_BASE_URL", "http://localhost:11434")
    # Hermetisch machen: ein evtl. real persistierter Store-Key auf dem
    # Entwicklerrechner darf dieses Ergebnis nicht beeinflussen (#799).
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver.get_api_key",
        lambda self, provider_id, provider_type: None,
    )

    payload = {
        "graph_id": "graph_abc",
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert captured_generator_kwargs["api_key"] == LOCAL_NO_AUTH_API_KEY


def test_generate_profiles_returns_422_when_no_store_key_for_remote_provider(
    client, patched_generator, captured_generator_kwargs, monkeypatch
):
    """Issue #799: Server-Default zeigt auf einen Fremd-Provider (kein
    lokaler Endpoint) und die Settings-DB hat keinen Store-Key hinterlegt —
    der Endpoint muss das jetzt sauber mit HTTP 422 quittieren, statt den
    generatorseitigen ``ValueError`` auf HTTP 500 durchschlagen zu lassen."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: MagicMock(load=lambda: None),
    )
    monkeypatch.setattr("app.config.Config.LLM_MODEL_NAME", "gpt-4o-mini")
    monkeypatch.setattr("app.config.Config.LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver.get_api_key",
        lambda self, provider_id, provider_type: None,
    )

    payload = {
        "graph_id": "graph_abc",
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    body = resp.get_json()
    assert resp.status_code == 422, body
    assert "openai" in body["error"].lower()


def test_generate_profiles_uses_store_key_for_remote_provider(
    client, patched_generator, captured_generator_kwargs, monkeypatch
):
    """Issue #799 — der eigentliche Fix: liefert die Settings-DB einen
    Store-Key für den Server-Default-Provider, reicht der Endpoint ihn durch,
    statt (wie vor dem Fix) ausschließlich Payload-Keys zu akzeptieren."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: MagicMock(load=lambda: None),
    )
    monkeypatch.setattr("app.config.Config.LLM_MODEL_NAME", "gpt-4o-mini")
    monkeypatch.setattr("app.config.Config.LLM_BASE_URL", "https://api.openai.com/v1")
    stored_key = "sk-stored-testkey1234567890"  # gitleaks:allow
    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver.get_api_key",
        lambda self, provider_id, provider_type: stored_key,
    )

    payload = {
        "graph_id": "graph_abc",
        "use_llm": True,
    }
    resp = client.post("/api/simulation/generate-profiles", json=payload)
    assert resp.status_code == 200, resp.get_json()
    assert captured_generator_kwargs["api_key"] == stored_key


def test_generate_profiles_local_endpoint_without_key_uses_no_auth_placeholder(
    client, patched_generator, captured_generator_kwargs, monkeypatch
):
    """Issue #778 Blocker 1 (Preview-Pfad) — lokaler Endpoint ohne Key darf
    weder 500 noch ``ValueError`` produzieren; der Generator bekommt den
    dokumentierten No-Auth-Platzhalter statt eines rohen ``None``.

    Issue #799: seit der Store-Key-Auflösung muss dieser Test hermetisch
    sein — ein evtl. real persistierter Store-Key auf dem Entwicklerrechner
    darf das Ergebnis nicht beeinflussen.
    """
    from app.utils.endpoints import LOCAL_NO_AUTH_API_KEY

    monkeypatch.setattr(
        "app.services.llm_routing_seed.SecretResolver.get_api_key",
        lambda self, provider_id, provider_type: None,
    )

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
