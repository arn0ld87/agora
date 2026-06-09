"""Tests für den Backend-Fallback: Provider-Override ohne Payload-Key → Settings-DB-Key.

Smoke-Fix Welle 2, Slice 04 — P1 #3 + #17.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.api import simulation_bp, llm_bp
from app.contracts.llm_routing_contract import ResolvedRoute


VALID_SIM_ID = "sim_0123456789ab"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prepare_client(monkeypatch):
    """Flask test-client mit simulation_bp."""
    # @require_scope greift sobald AGORA_AUTH_TOKEN gesetzt ist. Diese Tests
    # prüfen Validierungs-/Routing-Logik, nicht Auth — Open-Mode erzwingen.
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture()
def llm_client(monkeypatch):
    """Flask test-client mit llm_bp."""
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    return app.test_client()


def _base_prepare_mocks(monkeypatch, *, resolved_api_key: str | None):
    """Setzt alle Mocks für /api/simulation/prepare außer resolve_route_api_key."""
    fake_state = MagicMock()
    fake_state.project_id = "proj_001"
    fake_state.graph_id = "graph_001"
    fake_state.source_simulation_id = None
    fake_state.root_simulation_id = None
    fake_state.branch_name = None
    fake_state.branch_depth = 0
    fake_state.entities_count = 1
    fake_state.entity_types = ["Person"]

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Testszenarien diskutieren"

    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}

    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = fake_state

    class FakeTaskManager:
        def create_task(self, *a, **k):
            return "task_1"
        def update_task(self, *a, **k):
            return None
        def complete_task(self, *a, **k):
            return None
        def fail_task(self, *a, **k):
            return None

    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_project", lambda _: fake_project)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_extracted_text", lambda _: "text")
    monkeypatch.setattr("app.api.simulation_prepare.get_simulation_storage", lambda: MagicMock())
    monkeypatch.setattr(
        "app.api.simulation_prepare.EntityReader",
        lambda _s: MagicMock(filter_defined_entities=MagicMock(return_value=fake_filtered)),
    )
    monkeypatch.setattr("app.api.simulation_prepare.seed_run_stage_routing", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.api.simulation_prepare.run_registry.create_run",
        lambda *a, **k: {"run_id": "run_test_1"},
    )
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)
    monkeypatch.setattr(
        "app.api.simulation_prepare.resolve_route_api_key",
        lambda *_a, **_k: resolved_api_key,
    )


# ---------------------------------------------------------------------------
# Test 1: Provider ohne Payload-Key → Backend nutzt DB-Key
# ---------------------------------------------------------------------------


def test_override_uses_db_key_when_payload_key_empty(prepare_client, monkeypatch):
    """Wenn Payload provider='openai' aber kein api_key sendet, nutzt Backend den DB-Key (sk-foo)."""
    captured: dict = {}

    class FakeRouter:
        def __init__(self, _run_id: str):
            pass
        def resolve(self, _stage: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=1,
            )
        def lock_stage(self, *_a, **_k):
            return None

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        m = MagicMock()
        m.to_simple_dict.return_value = {"simulation_id": VALID_SIM_ID, "status": "ready"}
        return m

    _base_prepare_mocks(monkeypatch, resolved_api_key="sk-foo")
    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = MagicMock(
        project_id="proj_001", graph_id="g1",
        source_simulation_id=None, root_simulation_id=None,
        branch_name=None, branch_depth=0,
        entities_count=1, entity_types=["Person"],
    )
    fake_manager.prepare_simulation.side_effect = fake_prepare
    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.jobs.threading.Thread.start", lambda self: self.run())

    resp = prepare_client.post(
        "/api/simulation/prepare",
        json={
            "simulation_id": VALID_SIM_ID,
            "llm_provider": {"provider": "openai"},  # kein api_key
        },
    )

    # 200 erwartet — Backend hat DB-Key "sk-foo" erfolgreich genutzt
    assert resp.status_code == 200, resp.get_json()
    assert captured.get("llm_runtime") is not None
    assert captured["llm_runtime"].api_key == "sk-foo"


# ---------------------------------------------------------------------------
# Test 2: Expliziter Payload-Key überschreibt DB-Key
# ---------------------------------------------------------------------------


def test_override_prefers_explicit_payload_key_over_db_key(prepare_client, monkeypatch):
    """api_key_override='sk-bar' im Payload gewinnt gegenüber DB-Key 'sk-foo'."""
    captured: dict = {}

    class FakeRouter:
        def __init__(self, _run_id: str):
            pass
        def resolve(self, _stage: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=1,
            )
        def lock_stage(self, *_a, **_k):
            return None

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        m = MagicMock()
        m.to_simple_dict.return_value = {"simulation_id": VALID_SIM_ID, "status": "ready"}
        return m

    # resolve_route_api_key gibt "sk-bar" zurück (Payload-Key hat Vorrang — Logik in llm_routing_seed.py)
    _base_prepare_mocks(monkeypatch, resolved_api_key="sk-bar")
    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = MagicMock(
        project_id="proj_001", graph_id="g1",
        source_simulation_id=None, root_simulation_id=None,
        branch_name=None, branch_depth=0,
        entities_count=1, entity_types=["Person"],
    )
    fake_manager.prepare_simulation.side_effect = fake_prepare
    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.jobs.threading.Thread.start", lambda self: self.run())

    resp = prepare_client.post(
        "/api/simulation/prepare",
        json={
            "simulation_id": VALID_SIM_ID,
            "llm_provider": {"provider": "openai", "api_key": "sk-bar"},
        },
    )

    assert resp.status_code == 200, resp.get_json()
    assert captured["llm_runtime"].api_key == "sk-bar"


# ---------------------------------------------------------------------------
# Test 3: Cloud-Provider, kein Payload-Key, kein DB-Key → 422
# ---------------------------------------------------------------------------


def test_override_422_when_no_payload_no_db_and_cloud_provider(prepare_client, monkeypatch):
    """Cloud-Provider (openai), kein Key im Payload, kein Key in DB → 422 mit Fehlermeldung."""

    class FakeRouter:
        def __init__(self, _run_id: str):
            pass
        def resolve(self, _stage: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=1,
            )
        def lock_stage(self, *_a, **_k):
            return None

    _base_prepare_mocks(monkeypatch, resolved_api_key=None)
    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = MagicMock(
        project_id="proj_001", graph_id="g1",
        source_simulation_id=None, root_simulation_id=None,
        branch_name=None, branch_depth=0,
        entities_count=1, entity_types=["Person"],
    )
    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)

    resp = prepare_client.post(
        "/api/simulation/prepare",
        json={
            "simulation_id": VALID_SIM_ID,
            "llm_provider": {"provider": "openai"},  # kein Key, DB auch leer (mock liefert None)
        },
    )

    assert resp.status_code == 422, resp.get_json()
    body = resp.get_json()
    assert "provider_override" in body.get("message", "").lower() or "provider_override" in str(body).lower()


# ---------------------------------------------------------------------------
# Test 4: Lokaler Ollama-Provider ohne Key → kein Fail
# ---------------------------------------------------------------------------


def test_override_no_key_required_for_local_ollama(prepare_client, monkeypatch):
    """Lokaler Ollama-Endpoint (localhost:11434) braucht keinen API-Key → kein 422."""
    captured: dict = {}

    class FakeRouter:
        def __init__(self, _run_id: str):
            pass
        def resolve(self, _stage: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="ollama_local",
                model="qwen3:8b",
                base_url_sanitized="http://localhost:11434/v1",
                routing_version=1,
            )
        def lock_stage(self, *_a, **_k):
            return None

    def fake_prepare(**kwargs):
        captured.update(kwargs)
        m = MagicMock()
        m.to_simple_dict.return_value = {"simulation_id": VALID_SIM_ID, "status": "ready"}
        return m

    # resolve_route_api_key liefert None (kein Key konfiguriert für Ollama)
    _base_prepare_mocks(monkeypatch, resolved_api_key=None)
    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = MagicMock(
        project_id="proj_001", graph_id="g1",
        source_simulation_id=None, root_simulation_id=None,
        branch_name=None, branch_depth=0,
        entities_count=1, entity_types=["Person"],
    )
    fake_manager.prepare_simulation.side_effect = fake_prepare
    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.jobs.threading.Thread.start", lambda self: self.run())

    resp = prepare_client.post(
        "/api/simulation/prepare",
        json={
            "simulation_id": VALID_SIM_ID,
            "llm_provider": {
                "provider": "custom_openai",
                "base_url": "http://localhost:11434/v1",
            },
        },
    )

    # Kein 422 — lokaler Endpoint ist exempt
    assert resp.status_code == 200, resp.get_json()


# ---------------------------------------------------------------------------
# Test 5: has-key Endpoint — Key vorhanden
# ---------------------------------------------------------------------------


def test_has_key_endpoint_returns_true_when_key_stored(llm_client, monkeypatch):
    """GET /api/llm/providers/<id>/has-key → {has_key: true} wenn Key in DB."""
    from app.contracts.llm_routing_contract import ProviderDescriptor

    fake_provider = ProviderDescriptor(id="openai", label="OpenAI", type="openai")
    monkeypatch.setattr(
        "app.api.llm_providers.provider_registry.get_providers",
        lambda: [fake_provider],
    )
    with patch("app.api.llm_providers.get_llm_provider_secrets_store") as mock_store:
        mock_store.return_value.get_plaintext.return_value = "sk-secret"
        resp = llm_client.get("/api/llm/providers/openai/has-key")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["has_key"] is True


# ---------------------------------------------------------------------------
# Test 6: has-key Endpoint — kein Key vorhanden
# ---------------------------------------------------------------------------


def test_has_key_endpoint_returns_false_when_no_key(llm_client, monkeypatch):
    """GET /api/llm/providers/<id>/has-key → {has_key: false} wenn kein Key in DB."""
    from app.contracts.llm_routing_contract import ProviderDescriptor

    fake_provider = ProviderDescriptor(id="openai", label="OpenAI", type="openai")
    monkeypatch.setattr(
        "app.api.llm_providers.provider_registry.get_providers",
        lambda: [fake_provider],
    )
    with patch("app.api.llm_providers.get_llm_provider_secrets_store") as mock_store:
        mock_store.return_value.get_plaintext.return_value = None
        resp = llm_client.get("/api/llm/providers/openai/has-key")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["has_key"] is False


# ---------------------------------------------------------------------------
# Gemini-Followup PR #466 — Subdomain-Smuggling-Schutz für _is_local_endpoint
# ---------------------------------------------------------------------------


def test_is_local_endpoint_accepts_real_local_hosts():
    """``_is_local_endpoint`` erkennt echte lokale Hostnamen unabhängig vom Port."""
    from app.api.simulation_prepare import _is_local_endpoint

    assert _is_local_endpoint("http://localhost:11434/v1") is True
    assert _is_local_endpoint("http://127.0.0.1:11434/v1") is True
    assert _is_local_endpoint("http://host.docker.internal:11434/v1") is True
    assert _is_local_endpoint("http://localhost") is True
    assert _is_local_endpoint("http://[::1]:11434/v1") is True


def test_is_local_endpoint_rejects_subdomain_smuggling():
    """Cloud-URLs, die ``localhost`` oder ``11434`` als Substring enthalten, dürfen
    nicht fälschlich als lokal gelten — Gemini-MEDIUM auf PR #466.
    """
    from app.api.simulation_prepare import _is_local_endpoint

    # Hostname enthält ``localhost`` als Substring → kein echter Local-Host.
    assert _is_local_endpoint("http://not-localhost.com/v1") is False
    assert _is_local_endpoint("https://localhost.evil.example/v1") is False
    # Port 11434 auf einem Remote-Host darf nicht reichen.
    assert _is_local_endpoint("http://remote-server.example:11434/v1") is False
    # 127-Subdomain-Smuggling.
    assert _is_local_endpoint("http://127.0.0.1.evil.example/v1") is False
    # Leerstring / None bleiben False.
    assert _is_local_endpoint("") is False
    assert _is_local_endpoint(None) is False
