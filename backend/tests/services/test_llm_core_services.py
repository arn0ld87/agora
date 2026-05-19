import os
from unittest.mock import patch
from app.services.llm_provider_registry import LlmProviderRegistry
from app.services.secret_resolver import SecretResolver
from app.services.model_catalog_service import ModelCatalogService

def test_provider_registry_metadata():
    registry = LlmProviderRegistry()
    providers = registry.get_providers()
    openai = next(p for p in providers if p.id == "openai")
    assert openai.label == "OpenAI"
    assert openai.base_url == "https://api.openai.com/v1"
    assert openai.api_key_ref == "OPENAI_API_KEY"
    assert openai.supports_models_endpoint is True

def test_secret_resolver():
    resolver = SecretResolver(session_api_keys={"openai": "session-key"})
    assert resolver.get_api_key("openai", "openai") == "session-key"

    # Track 1: ENV-Wert muss dem ``sk-``-Format entsprechen, sonst lehnt der
    # Resolver ihn ab und schreibt eine WARNING ins Log.
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-validkey1234567890abcDEF"}):  # gitleaks:allow
        resolver_no_session = SecretResolver()
        assert (
            resolver_no_session.get_api_key("openai", "openai")
            == "sk-env-validkey1234567890abcDEF"
        )

def test_secret_resolver_sanitize_url():
    resolver = SecretResolver()
    assert resolver.sanitize_url("http://user:pass@localhost:11434/v1?query=1") == "http://localhost:11434/v1"
    assert resolver.sanitize_url("https://api.openai.com/v1") == "https://api.openai.com/v1"

@patch("app.services.model_catalog_service._http_get_json")
def test_model_catalog_ollama_discovery(mock_http):
    # Mock /v1/models response (Helper returnt bereits geparstes JSON)
    mock_http.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}

    service = ModelCatalogService()
    # Cache leeren — Modul-level dict überlebt sonst zwischen Tests.
    service._cache = {}
    models = service.get_models("ollama", "ollama_cloud", "http://localhost:11434/v1", None)

    assert len(models) == 2
    assert models[0].id == "model1"
    assert models[0].source == "live"


@patch("app.services.model_catalog_service._http_get_json")
def test_model_catalog_ollama_cloud_sends_bearer_token(mock_http):
    """Regression: Ollama Cloud erfordert Authorization-Header (Issue #529)."""
    mock_http.return_value = {"data": [{"id": "ministral-3:8b"}]}
    service = ModelCatalogService()
    service._cache = {}
    service.get_models("ollama_cloud", "ollama_cloud", "https://ollama.com/v1", "sk-test-key")
    # api_key MUSS an _http_get_json durchgereicht worden sein (sonst 401 silent).
    call = mock_http.call_args
    assert call.kwargs.get("api_key") == "sk-test-key"


def test_model_catalog_fallback():
    service = ModelCatalogService()
    # Clear cache to force fallback
    service._cache = {}

    with patch(
        "app.services.model_catalog_service._http_get_json",
        side_effect=Exception("Connection error"),
    ):
        models = service.get_models("openai", "openai", "https://api.openai.com/v1", "key")
        assert len(models) > 0
        assert models[0].source == "fallback"
