"""
LLM Provider API.
"""

from flask import request
from pydantic import ValidationError

from . import llm_bp
from ..contracts.llm_provider_keys_contract import (
    LlmProviderKeyCreateRequest,
    LlmProviderKeysListResponse,
)
from ..services.llm_provider_registry import LlmProviderRegistry
from ..services.llm_provider_secrets_store import get_llm_provider_secrets_store
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

    base_url = request.args.get("base_url") or provider.base_url
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
    base_url = data.get("base_url") or provider.base_url
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
        logger.exception("Provider test failed for %s: %s", provider_id, exc)
        return json_error("Test failed: connectivity or authentication error", status=400)


# ---------------------------------------------------------------------------
# Provider-API-Key-CRUD (Frontend-Setup: speichern, anzeigen, widerrufen)
# ---------------------------------------------------------------------------


def _provider_or_404(provider_id: str):
    providers = provider_registry.get_providers()
    return next((p for p in providers if p.id == provider_id), None)


@llm_bp.route("/providers/api-keys", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_api_keys():
    """List all provider API keys (masked)."""
    items = get_llm_provider_secrets_store().list_entries()
    response = LlmProviderKeysListResponse(items=items, total=len(items))
    return json_success(response.model_dump(mode="json"))


@llm_bp.route("/providers/<provider_id>/api-key", methods=["GET"])
@handle_api_errors(logger=logger)
def get_provider_api_key(provider_id: str):
    """Return the stored (masked) key entry for one provider."""
    if _provider_or_404(provider_id) is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    entry = get_llm_provider_secrets_store().get_entry(provider_id)
    if entry is None:
        return json_error("API key not configured", status=404, code="not_found")
    return json_success(entry.model_dump(mode="json"))


@llm_bp.route("/providers/<provider_id>/api-key", methods=["POST", "PUT"])
@handle_api_errors(logger=logger)
def upsert_provider_api_key(provider_id: str):
    """Store or replace the API key for one provider."""
    provider = _provider_or_404(provider_id)
    if provider is None:
        return json_error(f"Provider not found: {provider_id}", status=404)

    payload = request.get_json(silent=True) or {}
    try:
        body = LlmProviderKeyCreateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )

    store = get_llm_provider_secrets_store()
    try:
        entry = store.upsert(
            provider_id,
            api_key=body.api_key,
            base_url=body.base_url or provider.base_url,
        )
    except RuntimeError as exc:
        logger.error("Secret-Store-Fehler beim Speichern: %s", exc)
        return json_error(
            "Secret store unavailable (AGORA_SECRET_KEY missing or invalid)",
            status=503,
            code="secret_store_unavailable",
        )

    # Optionaler Inline-Validate
    if request.args.get("validate") == "1":
        base_url = entry.base_url or provider.base_url
        if base_url:
            try:
                model_catalog.get_models(provider_id, provider.type, base_url, body.api_key)
                entry = store.mark_validated(provider_id, ok=True) or entry
            except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning("Provider-Validate fehlgeschlagen für %s: %s", provider_id, exc)
                entry = store.mark_validated(provider_id, ok=False) or entry

    # POST → 201 Created; PUT → 200 OK (Gemini MEDIUM #8)
    status_code = 201 if request.method == "POST" else 200
    return json_success(entry.model_dump(mode="json"), status=status_code)


@llm_bp.route("/providers/<provider_id>/has-key", methods=["GET"])
@handle_api_errors(logger=logger)
def provider_has_key(provider_id: str):
    """Read-only: prüft ob für diesen Provider ein API-Schlüssel in der Settings-DB hinterlegt ist.

    Gibt ``{"has_key": true|false}`` und immer HTTP 200 zurück — auch für
    unbekannte Provider-IDs (Copilot PR #466). Der Frontend-Banner-Code
    interpretiert ``has_key=false`` korrekt als "Pflichteingabe", deshalb
    ist 200 + has_key=false die sauberere Antwort als 404.
    Hinweis: dieser Endpoint liest nur den persistenten Store, kein env-Fallback.
    """
    if _provider_or_404(provider_id) is None:
        return json_success({"has_key": False, "provider_id": provider_id})
    try:
        stored = get_llm_provider_secrets_store().get_plaintext(provider_id)
        has_key = bool(stored)
    except RuntimeError:
        # AGORA_SECRET_KEY fehlt — wir wissen nicht ob ein Key da ist
        has_key = False
    return json_success({"has_key": has_key, "provider_id": provider_id})


@llm_bp.route("/providers/<provider_id>/api-key", methods=["DELETE"])
@handle_api_errors(logger=logger)
def delete_provider_api_key(provider_id: str):
    """Revoke the API key for one provider."""
    if _provider_or_404(provider_id) is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    deleted = get_llm_provider_secrets_store().delete(provider_id)
    if not deleted:
        return json_error("API key not configured", status=404, code="not_found")
    return json_success({"provider_id": provider_id, "status": "revoked"})
