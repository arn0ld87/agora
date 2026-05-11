from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

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
    monkeypatch.setattr("app.api.simulation_prepare.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)

    response = client.post(
        "/api/simulation/prepare",
        json={"simulation_id": VALID_SIM_ID, "llm_model": "ignored-by-route"},
    )

    assert response.status_code == 200, response.get_json()
    assert captured["llm_model"] == "gpt-4o-mini"
    assert captured["llm_runtime"].api_key == "sk-route"
    assert captured["llm_runtime"].base_url == "https://api.openai.com/v1"
