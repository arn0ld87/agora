from __future__ import annotations

from unittest.mock import patch

from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_routing_seed import (
    build_route_subprocess_env,
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.runtime_run_config import RuntimeRunConfig


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_seed_run_stage_routing_persists_stage_override(mock_run_dir, tmp_path):
    run_id = "run_seed_123"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    config = seed_run_stage_routing(
        run_id,
        "report_generation",
        llm_model_override="gpt-4o-mini",
        llm_runtime=RuntimeLlmConfig(
            provider="custom_openai",
            api_key="session-secret",
            base_url="https://gateway.example/v1",
        ),
    )

    loaded = RuntimeRunConfig(run_id).load_config()
    override = loaded.stage_overrides["report_generation"]
    assert config.stage_overrides["report_generation"].provider_id == "openai_compatible"
    assert override.provider_id == "openai_compatible"
    assert override.model == "gpt-4o-mini"
    assert override.provider_options == {"base_url": "https://gateway.example/v1"}


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_seed_run_stage_routing_keeps_server_default_without_override(mock_run_dir, tmp_path):
    run_id = "run_seed_default"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    # WorkspaceRoutingStore mocken — sonst leckt ein im Container persistierter
    # Default in den Test und überschreibt den Config-Default
    # (Smoke-Live 2026-05-15).
    from app.services.workspace_routing_store import get_workspace_routing_store
    get_workspace_routing_store().reset_for_tests()

    with patch("app.config.Config.LLM_BASE_URL", "https://api.openai.com/v1"), patch(
        "app.config.Config.LLM_MODEL_NAME", "gpt-4o"
    ):
        loaded = seed_run_stage_routing(
            run_id,
            "graph_build",
            llm_model_override=None,
            llm_runtime=RuntimeLlmConfig(),
        )

    assert loaded.global_default.provider_id == "openai"
    assert loaded.global_default.model == "gpt-4o"
    assert loaded.stage_overrides == {}


@patch("app.services.secret_resolver.SecretResolver.get_api_key")
def test_resolve_route_api_key_prefers_runtime_secret_for_matching_provider(mock_get_api_key):
    route = ResolvedRoute(
        stage="report_generation",
        provider_id="google",
        model="gemini-1.5-pro",
        routing_version=3,
    )

    api_key = resolve_route_api_key(
        route,
        RuntimeLlmConfig(
            provider="google",
            api_key="runtime-google-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
    )

    assert api_key == "runtime-google-key"
    mock_get_api_key.assert_not_called()


def test_build_route_subprocess_env_uses_resolved_route_values():
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=2,
        provider_options={"num_ctx": 32768},
    )

    env = build_route_subprocess_env(route, api_key="server-key", run_id="run_telemetry")

    assert env["AGORA_RUN_ID"] == "run_telemetry"
    assert env["LLM_API_KEY"] == "server-key"
    assert env["OPENAI_API_KEY"] == "server-key"
    assert env["LLM_BASE_URL"] == "https://api.openai.com/v1"
    assert env["LLM_MODEL_NAME"] == "gpt-4o-mini"


def test_build_runtime_llm_config_maps_resolved_route_for_legacy_callers():
    route = ResolvedRoute(
        stage="persona_generation",
        provider_id="ollama_cloud",
        model="qwen2.5:32b",
        base_url_sanitized="http://localhost:11434/v1",
        routing_version=4,
    )

    cfg = build_runtime_llm_config(route, api_key="local-key")

    assert cfg.provider == "custom_openai"
    assert cfg.api_key == "local-key"
    assert cfg.base_url == "http://localhost:11434/v1"
