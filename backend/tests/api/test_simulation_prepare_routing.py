from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute


VALID_SIM_ID = "sim_0123456789ab"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"] = 1000
    app.config["AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"] = 60
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def test_prepare_endpoint_uses_resolved_route_for_legacy_service_call(client, monkeypatch):
    captured: dict = {}

    fake_state = MagicMock()
    fake_state.project_id = "proj_123"
    fake_state.graph_id = "graph_123"
    fake_state.source_simulation_id = None
    fake_state.root_simulation_id = None
    fake_state.branch_name = None
    fake_state.branch_depth = 0
    fake_state.entities_count = 1
    fake_state.entity_types = ["Person"]

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Discuss the project"

    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}

    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = fake_state
    fake_manager.prepare_simulation.side_effect = lambda **kwargs: captured.update(kwargs) or MagicMock(
        to_simple_dict=lambda: {"simulation_id": VALID_SIM_ID, "status": "ready"}
    )

    class FakeTaskManager:
        def create_task(self, *args, **kwargs):
            return "task_prepare_1"

        def update_task(self, *args, **kwargs):
            return None

        def complete_task(self, *args, **kwargs):
            return None

        def fail_task(self, *args, **kwargs):
            return None

    class FakeRouter:
        def __init__(self, run_id: str):
            self.run_id = run_id

        def resolve(self, _stage_id: str):
            return ResolvedRoute(
                stage="persona_generation",
                provider_id="openai",
                model="gpt-4o-mini",
                base_url_sanitized="https://api.openai.com/v1",
                routing_version=9,
            )

        def lock_stage(self, *_args, **_kwargs):
            return None

    def run_inline(self):
        self.run()

    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_project", lambda _pid: fake_project)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_extracted_text", lambda _pid: "document text")
    monkeypatch.setattr("app.api.simulation_prepare.get_simulation_storage", lambda: MagicMock())
    monkeypatch.setattr(
        "app.api.simulation_prepare.EntityReader",
        lambda _storage: MagicMock(filter_defined_entities=MagicMock(return_value=fake_filtered)),
    )
    monkeypatch.setattr("app.api.simulation_prepare.seed_run_stage_routing", lambda *a, **k: None)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.api.simulation_prepare.resolve_route_api_key", lambda *_a, **_k: "sk-route")
    monkeypatch.setattr(
        "app.api.simulation_prepare.run_registry.create_run",
        lambda *a, **k: {"run_id": "run_prepare_1"},
    )
    # PR 2: Thread-Start liegt jetzt in app.jobs.enqueue (single point of change).
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    response = client.post(
        "/api/simulation/prepare",
        json={"simulation_id": VALID_SIM_ID, "llm_model": "ignored-by-route"},
    )

    assert response.status_code == 200, response.get_json()
    assert captured["llm_model"] == "gpt-4o-mini"
    assert captured["llm_runtime"].api_key == "sk-route"
    assert captured["llm_runtime"].base_url == "https://api.openai.com/v1"


def _run_prepare_with_route(client, monkeypatch, *, resolved_route, resolved_api_key):
    """Hilfsfunktion: teilt das Fixture-Setup zwischen den Key-Routing-Tests (#778)."""
    captured: dict = {}

    fake_state = MagicMock()
    fake_state.project_id = "proj_123"
    fake_state.graph_id = "graph_123"
    fake_state.source_simulation_id = None
    fake_state.root_simulation_id = None
    fake_state.branch_name = None
    fake_state.branch_depth = 0
    fake_state.entities_count = 1
    fake_state.entity_types = ["Person"]

    fake_project = MagicMock()
    fake_project.simulation_requirement = "Discuss the project"

    fake_filtered = MagicMock()
    fake_filtered.filtered_count = 1
    fake_filtered.entity_types = {"Person"}

    fake_manager = MagicMock()
    fake_manager.get_simulation.return_value = fake_state
    fake_manager.prepare_simulation.side_effect = lambda **kwargs: captured.update(kwargs) or MagicMock(
        to_simple_dict=lambda: {"simulation_id": VALID_SIM_ID, "status": "ready"}
    )

    class FakeTaskManager:
        def create_task(self, *args, **kwargs):
            return "task_prepare_1"

        def update_task(self, *args, **kwargs):
            return None

        def complete_task(self, *args, **kwargs):
            return None

        def fail_task(self, *args, **kwargs):
            return None

    class FakeRouter:
        def __init__(self, run_id: str):
            self.run_id = run_id

        def resolve(self, _stage_id: str):
            return resolved_route

        def lock_stage(self, *_args, **_kwargs):
            return None

    def run_inline(self):
        self.run()

    monkeypatch.setattr("app.api.simulation_prepare.SimulationManager", lambda: fake_manager)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_project", lambda _pid: fake_project)
    monkeypatch.setattr("app.api.simulation_prepare.ProjectManager.get_extracted_text", lambda _pid: "document text")
    monkeypatch.setattr("app.api.simulation_prepare.get_simulation_storage", lambda: MagicMock())
    monkeypatch.setattr(
        "app.api.simulation_prepare.EntityReader",
        lambda _storage: MagicMock(filter_defined_entities=MagicMock(return_value=fake_filtered)),
    )
    monkeypatch.setattr("app.api.simulation_prepare.seed_run_stage_routing", lambda *a, **k: None)
    monkeypatch.setattr("app.api.simulation_prepare.StageModelRouter", FakeRouter)
    monkeypatch.setattr("app.api.simulation_prepare.resolve_route_api_key", lambda *_a, **_k: resolved_api_key)
    monkeypatch.setattr(
        "app.api.simulation_prepare.run_registry.create_run",
        lambda *a, **k: {"run_id": "run_prepare_1"},
    )
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    response = client.post(
        "/api/simulation/prepare",
        json={"simulation_id": VALID_SIM_ID},
    )
    return response, captured


def test_prepare_local_route_without_store_key_uses_no_auth_placeholder(client, monkeypatch):
    """Issue #778 Blocker 1 — RED vor der Korrektur: eine lokale Route ohne
    Store-Key darf den Generator nicht mit `ValueError` scheitern lassen, auch
    wenn die Base-URL als String von `Config.LLM_BASE_URL` abweicht
    (`host.docker.internal` vs. `localhost` ist der klassische Container-Fall).
    """
    from app.config import Config
    from app.api.simulation_prepare import LOCAL_NO_AUTH_API_KEY

    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    local_route = ResolvedRoute(
        stage="persona_generation",
        provider_id="ollama",
        model="qwen2.5:14b",
        base_url_sanitized="http://host.docker.internal:11434/v1",
        routing_version=1,
    )

    response, captured = _run_prepare_with_route(
        client, monkeypatch, resolved_route=local_route, resolved_api_key=None
    )

    assert response.status_code == 200, response.get_json()
    assert captured["llm_runtime"].api_key == LOCAL_NO_AUTH_API_KEY
    assert captured["llm_runtime"].base_url == "http://host.docker.internal:11434/v1"


@pytest.mark.parametrize(
    "provider_id,model,base_url_sanitized",
    [
        (
            "google",
            "gemini-2.5-flash",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        (
            "minimax",
            "MiniMax-M3",
            "https://api.minimax.io/v1",
        ),
        (
            "openai",
            "gpt-4o-mini",
            "https://api.openai.com/v1",
        ),
    ],
)
def test_prepare_foreign_provider_with_store_key_passes_store_key_through(
    client, monkeypatch, provider_id, model, base_url_sanitized
):
    """Issue #778 AK 2 + AK 3 — fremder Provider mit aufgeloestem Store-Key:
    der Generator erhaelt exakt den Store-Key, nicht den `.env`-Fallback.
    Parametrisierung deckt Google, MiniMax und OpenAI ab, weil Issue-Body den
    Provider-Wechsel Gemini <-> MiniMax <-> Ollama explizit als Pruefstein
    nennt. Die Base-URLs sind Test-Fixtures und werden nie aufgeloest.
    """
    from app.config import Config

    monkeypatch.setattr(Config, "LLM_API_KEY", "env-key-fixture")
    monkeypatch.setattr(Config, "LLM_BASE_URL", "http://localhost:11434/v1")

    foreign_route = ResolvedRoute(
        stage="persona_generation",
        provider_id=provider_id,
        model=model,
        base_url_sanitized=base_url_sanitized,
        routing_version=1,
    )

    response, captured = _run_prepare_with_route(
        client, monkeypatch, resolved_route=foreign_route, resolved_api_key="store-key-fixture"
    )

    assert response.status_code == 200, response.get_json()
    assert captured["llm_runtime"].api_key == "store-key-fixture"
    assert captured["llm_runtime"].api_key != "env-key-fixture"
    assert captured["llm_runtime"].base_url == base_url_sanitized
