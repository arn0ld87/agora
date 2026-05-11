"""
LLM Provider API.
"""

from flask import request
from . import llm_bp
from ..services.llm_provider_registry import LlmProviderRegistry
from ..services.model_catalog_service import ModelCatalogService
from ..services.secret_resolver import SecretResolver
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.logger import get_logger

logger = get_logger("agora.api.llm_providers")
provider_registry = LlmProviderRegistry()
model_catalog = ModelCatalogService()

@llm_bp.route("/providers", methods=["GET"])
@handle_api_errors(logger=logger)
def list_providers():
    """List available LLM providers and their auth status."""
    # In a real app, session keys might come from a secure cookie or session store.
    # For now, we assume no session keys for the public listing.
    providers = provider_registry.get_providers()
    return json_success([p.model_dump(mode="json") for p in providers])

@llm_bp.route("/providers/<provider_id>/models", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_models(provider_id: str):
    """List models for a specific provider."""
    providers = provider_registry.get_providers()
    provider = next((p for p in providers if p.id == provider_id), None)
    if not provider:
        return json_error(f"Provider not found: {provider_id}", status=404)

    base_url = request.args.get("base_url") or provider.default_base_url
    if not base_url:
        return json_error("base_url is required for this provider", status=400)

    resolver = SecretResolver()
    api_key = resolver.get_api_key(provider_id, provider.type)

    models = model_catalog.get_models(provider_id, provider.type, base_url, api_key)
    return json_success([m.model_dump(mode="json") for m in models])

@llm_bp.route("/providers/<provider_id>/test", methods=["POST"])
@handle_api_errors(logger=logger)
def test_provider(provider_id: str):
    """Test connectivity to a provider."""
    providers = provider_registry.get_providers()
    provider = next((p for p in providers if p.id == provider_id), None)
    if not provider:
        return json_error(f"Provider not found: {provider_id}", status=404)

    data = request.get_json() or {}
    base_url = data.get("base_url") or provider.default_base_url
    api_key = data.get("api_key") # Allow explicit key for testing

    if not base_url:
        return json_error("base_url is required", status=400)

    resolver = SecretResolver()
    if not api_key:
        api_key = resolver.get_api_key(provider_id, provider.type)

    try:
        models = model_catalog.get_models(provider_id, provider.type, base_url, api_key)
        inference_test = request.args.get("inference") == "1"
        test_result = {"connectivity": "ok", "models_found": len(models)}

        if inference_test and models:
            from ..utils.llm_client import LLMClient
            client = LLMClient(api_key=api_key, base_url=base_url, model=models[0].id)
            resp = client.chat([{"role": "user", "content": "ping"}], max_tokens=10)
            test_result["inference"] = "ok"
            test_result["response_preview"] = resp[:50]

        return json_success(test_result)
    except Exception as exc:
        return json_error(f"Test failed: {exc}", status=400)
