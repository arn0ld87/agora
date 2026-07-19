from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.contracts.ai_provider_contract import ProviderConnection
from app.contracts.llm_profile_contract import LlmProfile
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_routing_seed import (
    build_route_subprocess_env,
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.runtime_run_config import RuntimeRunConfig


def _profile(profile_id: str, *, model: str = "gpt-4.1-mini") -> LlmProfile:
    """
    Create a test profile with fixed OpenAI connection details and timestamps.
    
    Parameters:
        profile_id (str): Identifier assigned to the profile.
        model (str): Model name assigned to the profile.
    
    Returns:
        LlmProfile: A profile populated with the specified identifier and model.
    """
    now = datetime.now(UTC)
    return LlmProfile(
        id=profile_id,
        name="Contract profile",
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name=model,
        api_key="must-not-enter-route",
        created_at=now,
        updated_at=now,
    )


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


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_profile_id_expands_to_a_secret_free_stage_route(mock_run_dir, monkeypatch, tmp_path):
    run_id = "run_profile_only"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)
    profile_store = MagicMock()
    profile_store.get.return_value = _profile("profile-openai")
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [
        ProviderConnection(
            id="openai",
            provider_kind="openai",
            display_name="OpenAI",
            transport="http",
            auth_mode="api_key",
            base_url="https://api.openai.com/v1",
            secret_ref="openai",
        )
    ]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )

    config = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        llm_profile_id="profile-openai",
    )

    route = config.stage_overrides["graph_build"]
    assert route.provider_id == "openai"
    assert route.model == "gpt-4.1-mini"
    assert route.provider_options == {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai",
        "connection_only": True,
    }
    assert "api_key" not in route.model_dump(mode="json")
    profile_store.get.assert_called_once_with("profile-openai", include_api_key=False)


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_explicit_runtime_route_wins_without_reading_the_profile(mock_run_dir, monkeypatch, tmp_path):
    run_id = "run_explicit_over_profile"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)
    profile_store = MagicMock()
    profile_store.get.side_effect = AssertionError("profile path must not be read")
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )

    config = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override="gpt-5-mini",
        llm_runtime=RuntimeLlmConfig(
            provider="openai",
            api_key="request-secret",
            base_url="https://api.openai.com/v1",
        ),
        llm_profile_id="profile-openai",
    )

    route = config.stage_overrides["graph_build"]
    assert route.provider_id == "openai"
    assert route.model == "gpt-5-mini"
    profile_store.get.assert_not_called()


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


def test_build_route_subprocess_env_injects_google_api_key_for_gemini():
    """OASIS subprocess findet den Gemini-Key ohne .env, sobald der Workspace-
    Secrets-Store ihn liefert (`api_key_ref="GOOGLE_API_KEY"` aus Registry)."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        base_url_sanitized="https://generativelanguage.googleapis.com/v1beta/openai/",
        routing_version=3,
    )

    env = build_route_subprocess_env(route, api_key="goog-server-key", run_id="run_gemini")

    assert env["GOOGLE_API_KEY"] == "goog-server-key"
    assert env["LLM_API_KEY"] == "goog-server-key"
    assert env["OPENAI_API_KEY"] == "goog-server-key"
    assert env["LLM_MODEL_NAME"] == "models/gemini-2.5-flash"


def test_build_route_subprocess_env_aliases_gemini_api_key_for_camel():
    """CAMELs GeminiModel im OASIS-Subprozess liest ``GEMINI_API_KEY``, nicht
    ``GOOGLE_API_KEY`` (die ``api_key_ref`` des Google-Providers). Ohne diesen
    Alias crasht der Subprozess trotz gesetztem Store-Key mit
    ``ValueError: Missing required API keys: GEMINI_API_KEY`` (Arbeitsprotokoll
    2026-07-18, Symptom 4). Damit bleibt der UI-Secrets-Store Single Source und
    ``.env`` wird fuer Gemini-Sims nicht mehr gebraucht."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        base_url_sanitized="https://generativelanguage.googleapis.com/v1beta/openai/",
        routing_version=3,
    )

    env = build_route_subprocess_env(route, api_key="goog-server-key", run_id="run_gemini")

    assert env["GEMINI_API_KEY"] == "goog-server-key"


def test_build_route_subprocess_env_no_gemini_alias_for_non_google():
    """Nicht-Google-Routen bekommen KEINEN GEMINI_API_KEY-Alias untergeschoben."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=2,
    )

    env = build_route_subprocess_env(route, api_key="server-key")

    assert "GEMINI_API_KEY" not in env


def test_build_route_subprocess_env_injects_ollama_api_key_for_ollama_cloud():
    """
    Ensure Ollama Cloud routes receive their API key in the subprocess environment.
    
    Returns:
        None
    """
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="ollama_cloud",
        model="qwen3-coder-next:cloud",
        base_url_sanitized="https://ollama.com/v1",
        routing_version=1,
    )

    env = build_route_subprocess_env(route, api_key="ollama-cloud-key")

    assert env["OLLAMA_API_KEY"] == "ollama-cloud-key"
    assert env["LLM_API_KEY"] == "ollama-cloud-key"


def test_build_route_subprocess_env_does_not_set_provider_key_without_api_key():
    """Ohne resolved api_key bleiben sowohl generische als auch provider-
    spezifische Env-Vars leer — die Subprozesse müssen dann selbst entscheiden,
    ob sie aus dem Parent-Env (`.env`-Fallback) ziehen."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        routing_version=1,
    )

    env = build_route_subprocess_env(route, api_key=None)

    assert "GOOGLE_API_KEY" not in env
    assert "LLM_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


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
