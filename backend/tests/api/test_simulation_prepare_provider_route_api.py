"""API-Vertrag für ``POST /api/simulation/prepare`` mit ``AiModelRef`` (#896)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.llm_routing_contract import ResolvedRoute


VALID_SIM_ID = "sim_0123456789ab"
CONNECTION_ID = "conn-minimax"
MODEL_ID = "MiniMax-M3"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "")
    app = Flask(__name__)
    app.config.update(
        AGORA_AUTH_TOKEN="",
        AGORA_LLM_TRIGGER_RATE_LIMIT_MAX=1000,
        AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS=60,
    )
    app.extensions = {"neo4j_storage": MagicMock(name="Neo4jStorage")}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


@pytest.fixture
def prepare_route_env(monkeypatch):
    observed: dict[str, object] = {
        "seed_ref": None,
        "seed_profile": None,
        "prevalidated_ref": None,
        "prepared_checked": False,
        "resolved": None,
        "locked": None,
        "failed_run": None,
        "failed_task": None,
    }
    project = SimpleNamespace(
        simulation_requirement="Discuss the project",
        llm_profile_id=None,
    )
    state = SimpleNamespace(
        project_id="proj_123",
        graph_id="graph_123",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
        entities_count=1,
        entity_types=["Person"],
    )
    manager = MagicMock()
    manager.get_simulation.return_value = state
    manager.prepare_simulation.side_effect = lambda **_kwargs: MagicMock(
        to_simple_dict=lambda: {"simulation_id": VALID_SIM_ID, "status": "ready"}
    )
    filtered = MagicMock(filtered_count=1, entity_types={"Person"})
    resolved_route = ResolvedRoute(
        stage="persona_generation",
        provider_id=CONNECTION_ID,
        model=MODEL_ID,
        base_url_sanitized="https://api.minimax.io/v1",
        routing_version=1,
        provider_options={"connection_only": True, "secret_ref": "configured-secret"},
    )

    class FakeTaskManager:
        def create_task(self, *_args, **_kwargs):
            return "task_prepare_1"

        def update_task(self, *_args, **_kwargs):
            return None

        def complete_task(self, *_args, **_kwargs):
            return None

        def fail_task(self, task_id, error):
            observed["failed_task"] = {"task_id": task_id, "error": error}
            return None

    class FakeRouter:
        def __init__(self, _run_id: str):
            pass

        def resolve(self, _stage_id: str):
            observed["resolved"] = resolved_route
            return resolved_route

        def lock_stage(self, _stage_id: str, route: ResolvedRoute):
            observed["locked"] = route
            return route

    def capture_seed(
        _run_id,
        _stage,
        *,
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        ai_model_ref=None,
    ):
        observed["seed_ref"] = ai_model_ref
        observed["seed_profile"] = llm_profile_id

    def capture_prepared_check(_simulation_id):
        observed["prepared_checked"] = True
        return False, {}

    def capture_prevalidation(ai_model_ref):
        observed["prevalidated_ref"] = ai_model_ref
        return MagicMock(name="ValidatedProviderConnection")
    def capture_failed_run(run_id, **updates):
        observed["failed_run"] = {"run_id": run_id, **updates}
        return observed["failed_run"]

    def run_inline(self):
        self.run()

    prefix = "app.api.simulation_prepare"
    monkeypatch.setattr(f"{prefix}.SimulationManager", lambda: manager)
    monkeypatch.setattr(f"{prefix}.ProjectManager.get_project", lambda _pid: project)
    monkeypatch.setattr(f"{prefix}.ProjectManager.get_extracted_text", lambda _pid: "document text")
    monkeypatch.setattr(f"{prefix}.get_simulation_storage", lambda: MagicMock())
    monkeypatch.setattr(
        f"{prefix}.EntityReader",
        lambda _storage: MagicMock(filter_defined_entities=MagicMock(return_value=filtered)),
    )
    monkeypatch.setattr(f"{prefix}.seed_run_stage_routing", capture_seed)
    monkeypatch.setattr(f"{prefix}._check_simulation_prepared", capture_prepared_check)
    monkeypatch.setattr(f"{prefix}.StageModelRouter", FakeRouter)
    monkeypatch.setattr(f"{prefix}.resolve_route_api_key", lambda *_args: "bound-key")
    monkeypatch.setattr(
        f"{prefix}.run_registry.create_run", lambda *_args, **_kwargs: {"run_id": "run_prepare_1"}
    )
    monkeypatch.setattr(f"{prefix}.run_registry.update_run", capture_failed_run)
    monkeypatch.setattr("app.jobs.threading.Thread.start", run_inline)
    monkeypatch.setattr("app.models.task.TaskManager", FakeTaskManager)
    monkeypatch.setattr(
        "app.services.llm_routing_seed.prevalidate_ai_model_ref",
        capture_prevalidation,
        raising=False,
    )

    return SimpleNamespace(
        observed=observed,
        project=project,
        monkeypatch=monkeypatch,
    )


def _ref_body(**extra):
    body = {
        "simulation_id": VALID_SIM_ID,
        "ai_model_ref": {
            "provider_connection_id": CONNECTION_ID,
            "model_id": MODEL_ID,
            "source": "explicit",
        },
    }
    body.update(extra)
    return body


def _post(client, **payload):
    return client.post("/api/simulation/prepare", json=_ref_body(**payload))


def test_valid_ai_model_ref_is_seeded_resolved_and_locked(client, prepare_route_env):
    response = _post(client)

    assert response.status_code == 200, response.get_json()
    forwarded = prepare_route_env.observed["seed_ref"]
    assert forwarded is not None
    assert forwarded.provider_connection_id == CONNECTION_ID
    assert forwarded.model_id == MODEL_ID
    prevalidated = prepare_route_env.observed["prevalidated_ref"]
    assert prevalidated is not None
    assert prevalidated.provider_connection_id == CONNECTION_ID
    assert prevalidated.model_id == MODEL_ID
    resolved = prepare_route_env.observed["resolved"]
    assert resolved.provider_id == CONNECTION_ID
    assert resolved.model == MODEL_ID
    assert prepare_route_env.observed["locked"] is resolved


@pytest.mark.parametrize(
    ("legacy_field", "legacy_value"),
    [
        ("llm_model", "gpt-4o-mini"),
        ("llm_profile_id", "profile-legacy"),
        ("llm_provider", {"provider": "openai", "base_url": "https://api.openai.com/v1"}),
        ("llm_runtime", {"provider": "openai", "base_url": "https://api.openai.com/v1"}),
    ],
)
def test_ai_model_ref_conflicts_with_legacy_override_returns_400(
    client, prepare_route_env, legacy_field, legacy_value
):
    response = _post(client, **{legacy_field: legacy_value})
    assert response.status_code == 400
    assert "ai_model_ref" in str(response.get_json())


def test_ai_model_ref_reprepare_bypasses_already_prepared_short_circuit(
    client, prepare_route_env
):
    prepare_route_env.monkeypatch.setattr(
        "app.api.simulation_prepare._check_simulation_prepared",
        lambda _simulation_id: (True, {"profiles": 12}),
    )

    response = _post(client)

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["already_prepared"] is False
    assert prepare_route_env.observed["seed_ref"] is not None


def test_explicit_ai_model_ref_beats_project_profile(client, prepare_route_env):
    prepare_route_env.project.llm_profile_id = "profile-project"

    response = _post(client)

    assert response.status_code == 200, response.get_json()
    assert prepare_route_env.observed["seed_ref"] is not None
    assert prepare_route_env.observed["seed_profile"] is None


def test_invalid_ai_model_ref_returns_400_without_echoing_sensitive_input(client, prepare_route_env):
    response = client.post(
        "/api/simulation/prepare",
        json={"simulation_id": VALID_SIM_ID, "ai_model_ref": {"model_id": "sensitive-value"}},
    )

    assert response.status_code == 400
    assert "ai_model_ref" in str(response.get_json())
    assert "sensitive-value" not in response.get_data(as_text=True)


def test_seed_model_mismatch_fails_created_run_and_task_without_secret_leak(
    client, prepare_route_env
):
    def reject_model_mismatch(*_args, **_kwargs):
        raise ValueError(
            f"Modell {MODEL_ID!r} gehört nicht zur ProviderConnection {CONNECTION_ID!r}"
        )

    prepare_route_env.monkeypatch.setattr(
        "app.api.simulation_prepare.seed_run_stage_routing",
        reject_model_mismatch,
    )
    response = _post(client)
    assert response.status_code == 400
    error = str(response.get_json())
    assert "gehört nicht zur ProviderConnection" in error
    assert "configured-secret" not in error
    failed_run = prepare_route_env.observed["failed_run"]
    assert failed_run is not None
    assert failed_run["run_id"] == "run_prepare_1"
    assert failed_run["status"] == "failed"
    assert "gehört nicht zur ProviderConnection" in failed_run["error"]
    assert "configured-secret" not in failed_run["error"]
    failed_task = prepare_route_env.observed["failed_task"]
    assert failed_task is not None
    assert failed_task["task_id"] == "task_prepare_1"
    assert "gehört nicht zur ProviderConnection" in failed_task["error"]
    assert "configured-secret" not in failed_task["error"]


def test_unknown_provider_connection_returns_deterministic_400_without_secret_leak(
    client, prepare_route_env
):
    def reject_unknown_connection(_ref):
        raise ValueError("ProviderConnection 'conn-missing' nicht gefunden")

    prepare_route_env.monkeypatch.setattr(
        "app.services.llm_routing_seed.prevalidate_ai_model_ref",
        reject_unknown_connection,
        raising=False,
    )

    response = _post(client, ai_model_ref={
        "provider_connection_id": "conn-missing",
        "model_id": MODEL_ID,
        "source": "explicit",
    })

    assert response.status_code == 400
    error = str(response.get_json())
    assert "ProviderConnection" in error
    assert "conn-missing" in error
    assert "configured-secret" not in error
