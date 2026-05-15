import pytest
import os
from unittest.mock import patch, MagicMock
from app.services.stage_model_router import StageModelRouter
from app.services.runtime_run_config import RuntimeRunConfig
from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute, ResolvedRoute
from app.services.secret_resolver import SecretResolver
from app.utils.llm_client import LLMClient

@pytest.fixture
def temp_run_dir(tmp_path):
    run_id = "proj_hardening123"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    with patch("app.utils.artifact_locator.ArtifactLocator.run_dir", return_value=str(run_dir)):
        yield run_id

def test_stage_model_router_filters_provider_options(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    # Route with sensitive fields in provider_options
    global_default = StageLLMRoute(
        provider_id="openai",
        model="gpt-4o",
        provider_options={
            "api_key": "secret-key",
            "base_url": "https://user:pass@api.openai.com/v1?token=abc",
            "num_ctx": 4096,
            "temperature": 0.5
        }
    )
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)
    service.save_config(config)

    router = StageModelRouter(temp_run_dir)
    resolved = router.resolve("document_ingest")

    # Verify filtering
    assert "api_key" not in resolved.provider_options
    assert "base_url" not in resolved.provider_options
    assert resolved.provider_options["num_ctx"] == 4096
    assert resolved.provider_options["temperature"] == 0.5

    # Verify sanitized URL
    assert resolved.base_url_sanitized == "https://api.openai.com/v1"

def test_secret_resolver_resolves_base_url():
    resolver = SecretResolver()

    # 1. From provider_options (highest precedence)
    url = resolver.get_base_url("any", "openai", {"base_url": "https://custom.openai.com"})
    assert url == "https://custom.openai.com"

    # 2. From environment (using a provider_id NOT in registry to reach env fallback)
    with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://env.openai.com"}):
        url = resolver.get_base_url("not-in-registry", "openai")
        assert url == "https://env.openai.com"

    # 3. From registry
    # "openai" is a standard provider ID in LlmProviderRegistry
    url = resolver.get_base_url("openai", "openai")
    assert url == "https://api.openai.com/v1"

def test_secret_resolver_sanitize_url():
    resolver = SecretResolver()
    assert resolver.sanitize_url("https://user:pass@host:1234/path?query=1#frag") == "https://host:1234/path"
    assert resolver.sanitize_url("http://localhost:11434") == "http://localhost:11434"
    assert resolver.sanitize_url(None) is None

def test_llm_client_from_route_restores_secrets(temp_run_dir):
    # This test simulates the full cycle:
    # StageLLMRoute (with secrets) -> ResolvedRoute (clean) -> LLMClient (with secrets)

    # Mocking SecretResolver to return secrets we expect
    mock_resolver = MagicMock(spec=SecretResolver)
    mock_resolver.get_api_key.return_value = "real-api-key"
    mock_resolver.get_base_url.return_value = "https://user:pass@api.openai.com/v1"

    resolved = ResolvedRoute(
        stage="document_ingest",
        provider_id="openai",
        model="gpt-4o",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
        provider_options={"num_ctx": 4096}
    )

    with patch("app.services.secret_resolver.SecretResolver", return_value=mock_resolver):
        client = LLMClient.from_route(resolved)

        assert client.api_key == "real-api-key"
        assert client.base_url == "https://user:pass@api.openai.com/v1"
        assert client.model == "gpt-4o"
        assert client.provider_options == {"num_ctx": 4096}

def test_integration_full_hardening_cycle(temp_run_dir):
    # Real integration test for StageModelRouter + LLMClient
    service = RuntimeRunConfig(temp_run_dir)

    # User provides a route with secrets
    user_route = StageLLMRoute(
        provider_id="openai_compatible",
        model="custom-model",
        provider_options={
            "api_key": "user-secret",
            "base_url": "https://secret-token@proxy.com/v1",
            "num_ctx": 8192
        }
    )
    config = RuntimeLlmRouting(global_default=user_route)
    # Normally save_config would already sanitize, but we want to test ResolvedRoute hardening
    service.save_config(config)

    router = StageModelRouter(temp_run_dir)
    resolved = router.resolve("graph_build")

    # 1. Check ResolvedRoute is clean
    assert "api_key" not in resolved.provider_options
    assert "base_url" not in resolved.provider_options
    assert resolved.base_url_sanitized == "https://proxy.com/v1"

    # 2. Check Snapshot on disk is clean
    router.lock_stage("graph_build", resolved)
    snapshot = service.load_stage_snapshot("graph_build")
    assert "api_key" not in snapshot["provider_options"]
    assert "base_url" not in snapshot["provider_options"]

    # 3. Rebuild Client from Snapshot
    # Since it's a custom provider, we need to make sure SecretResolver can find the base_url
    # For "openai_compatible", it falls back to Config.LLM_BASE_URL if no other source is found.
    # But wait, our get_base_url logic for "openai_compatible" uses global fallback.

    # Let's test that it can resolve from environment if we set it there
    with patch.dict(os.environ, {"LLM_API_KEY": "env-key", "LLM_BASE_URL": "https://env-url.com"}):
        client = LLMClient.from_route(resolved)
        assert client.api_key == "env-key"
        assert client.base_url == "https://env-url.com"
