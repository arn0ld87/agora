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

@patch("app.api.llm_providers.get_provider_connection_service")
def test_list_provider_models(mock_get_service, client):
    from app.services.provider_connections.adapters import ProviderProbeResult

    mock_get_service.return_value.probe.return_value = ProviderProbeResult(
        status="available", status_message=None, models=()
    )
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
        data = resp.json["data"]
        assert data["ai_route"]["provider_connection_id"] == "o"
        assert data["ai_route"]["model_id"] == "m"
        assert data["ai_route"]["source"] == "legacy"
        assert data["ai_route"]["provider_options"] == {}
        assert {key: value for key, value in data.items() if key != "ai_route"} == {
            "runtime_config": mock_load.return_value.model_dump(mode="json"),
            "snapshots": {},
            "invocation_events": [{"stage": "report_generation", "success": True}],
        }

def test_patch_stage_llm_routing_locked(client):
    with patch("app.services.runtime_run_config.RuntimeRunConfig.load_stage_snapshot") as mock_snap:
        mock_snap.return_value = {"locked": True}
        resp = client.patch("/api/runs/proj_123/llm-routing/stages/graph_build", json={})
        assert resp.status_code == 409
        assert resp.json["code"] == "stage_already_started"


def test_public_ai_route_serializer_strips_internal_legacy_marker():
    from app.api.llm_routing import _serialize_public_ai_route
    from app.contracts.ai_provider_contract import AiRoute
    from app.contracts.llm_routing_contract import StageLLMRoute

    public = _serialize_public_ai_route(
        StageLLMRoute(
            provider_id="provider-1",
            model="model-1",
            temperature=0.2,
            provider_options={
                "base_url": "http://localhost:11434",
                "num_ctx": 4096,
                "api_key": "must-not-leak",
                "timeout": 30,
            },
        ),
        source="legacy",
    )

    assert public["provider_options"] == {
        "base_url": "http://localhost:11434",
        "num_ctx": 4096,
    }
    assert "__legacy_stage_route__" not in str(public)
    assert AiRoute.model_validate(public).model_dump(mode="json") == public


def test_replace_run_routing_is_additive(client):
    from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute

    old = RuntimeLlmRouting(global_default=StageLLMRoute(provider_id="old", model="old"))
    payload = {
        "global_default": {"provider_id": "new", "model": "model"},
        "stage_overrides": {},
        "routing_version": 1,
    }
    with patch("app.services.runtime_run_config.RuntimeRunConfig.load_config", return_value=old), patch(
        "app.services.runtime_run_config.RuntimeRunConfig.save_config"
    ):
        resp = client.put("/api/runs/proj_123/llm-routing", json=payload)

    assert resp.status_code == 200
    data = resp.json["data"]
    assert data["ai_route"]["provider_connection_id"] == "new"
    assert data["ai_route"]["source"] == "run_override"
    legacy = RuntimeLlmRouting.model_validate(payload).model_copy(update={"routing_version": 2})
    assert {key: value for key, value in data.items() if key != "ai_route"} == legacy.model_dump(mode="json")


def test_patch_run_stage_routing_is_additive(client):
    from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute

    config = RuntimeLlmRouting(global_default=StageLLMRoute(provider_id="base", model="base"))
    with patch(
        "app.services.runtime_run_config.RuntimeRunConfig.load_stage_snapshot", return_value=None
    ), patch(
        "app.services.runtime_run_config.RuntimeRunConfig.load_config", return_value=config
    ), patch("app.services.runtime_run_config.RuntimeRunConfig.save_config"):
        resp = client.patch(
            "/api/runs/proj_123/llm-routing/stages/graph_build",
            json={"provider_id": "stage-provider", "model": "stage-model"},
        )

    assert resp.status_code == 200
    data = resp.json["data"]
    assert data["ai_route"]["provider_connection_id"] == "stage-provider"
    assert data["ai_route"]["model_id"] == "stage-model"
    assert data["ai_route"]["source"] == "stage_override"
    assert data["stage_overrides"]["graph_build"]["provider_id"] == "stage-provider"


def test_get_workspace_defaults_is_additive(client):
    from app.contracts.llm_routing_contract import StageLLMRoute
    from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults

    defaults = WorkspaceLlmRoutingDefaults(
        global_default=StageLLMRoute(provider_id="workspace-provider", model="workspace-model")
    )
    with patch("app.api.llm_routing.get_workspace_routing_store") as get_store:
        get_store.return_value.load.return_value = defaults
        resp = client.get("/api/llm/routing/defaults")

    data = resp.json["data"]
    assert data["ai_route"]["source"] == "workspace"
    assert data["ai_route"]["provider_connection_id"] == "workspace-provider"
    assert {key: value for key, value in data.items() if key != "ai_route"} == defaults.model_dump(mode="json")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("put", "/api/llm/routing/defaults"),
        ("patch", "/api/llm/routing/defaults/stages/graph_build"),
    ],
)
def test_mutate_workspace_defaults_is_additive(client, method, path):
    from app.contracts.llm_routing_contract import StageLLMRoute
    from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults

    route = StageLLMRoute(provider_id="workspace-provider", model="workspace-model")
    defaults = WorkspaceLlmRoutingDefaults(
        global_default=route,
        stage_overrides={"graph_build": route} if method == "patch" else {},
    )
    payload = defaults.model_dump(mode="json") if method == "put" else route.model_dump(mode="json")
    with patch("app.api.llm_routing.get_workspace_routing_store") as get_store:
        get_store.return_value.save.return_value = defaults
        get_store.return_value.set_stage_override.return_value = defaults
        resp = getattr(client, method)(path, json=payload)

    assert resp.status_code == 200
    data = resp.json["data"]
    assert data["ai_route"]["source"] == "workspace"
    assert data["ai_route"]["provider_connection_id"] == "workspace-provider"
    assert {key: value for key, value in data.items() if key != "ai_route"} == defaults.model_dump(mode="json")
