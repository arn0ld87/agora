import os
from unittest.mock import patch, MagicMock
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

    with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
        resolver_no_session = SecretResolver()
        assert resolver_no_session.get_api_key("openai", "openai") == "env-key"

def test_secret_resolver_sanitize_url():
    resolver = SecretResolver()
    assert resolver.sanitize_url("http://user:pass@localhost:11434/v1?query=1") == "http://localhost:11434/v1"
    assert resolver.sanitize_url("https://api.openai.com/v1") == "https://api.openai.com/v1"

@patch("requests.get")
def test_model_catalog_ollama_discovery(mock_get):
    # Mock /v1/models response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "model1"}, {"id": "model2"}]}
    mock_get.return_value = mock_resp

    service = ModelCatalogService()
    models = service.get_models("ollama", "ollama_local", "http://localhost:11434/v1", None)

    assert len(models) == 2
    assert models[0].id == "model1"
    assert models[0].source == "live"

def test_model_catalog_fallback():
    service = ModelCatalogService()
    # Clear cache to force fallback
    service._cache = {}

    with patch("requests.get", side_effect=Exception("Connection error")):
        models = service.get_models("openai", "openai", "https://api.openai.com/v1", "key")
        assert len(models) > 0
        assert models[0].source == "fallback"
