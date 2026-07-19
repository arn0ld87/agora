"""LLM-Provider-API mit kanonischem Connection-Lifecycle."""
from __future__ import annotations

from flask import request
from pydantic import SecretStr, ValidationError
from typing import cast

from . import llm_bp
from .deprecation import add_legacy_deprecation_headers
from ..contracts.ai_provider_contract import (
    ProviderConnection,
    ProviderConnectionProviderKind,
    ProviderConnectionResponse,
    ProviderConnectionUpsertRequest,
)
from ..contracts.llm_provider_keys_contract import (
    LlmProviderKeyCreateRequest,
    LlmProviderKeysListResponse,
)
from ..services.llm_provider_registry import LlmProviderRegistry
from ..services.llm_provider_secrets_store import (
    LlmProviderSecretsStore,
    get_llm_provider_secrets_store,
)
from ..services.provider_connection_store import ProviderConnectionStore
from ..services.provider_connections.service import ProviderConnectionService
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

logger = get_logger("agora.api.llm_providers")
provider_registry = LlmProviderRegistry()

_LEGACY_PROVIDER_VIEW_NAMES = frozenset(
    {
        "list_providers",
        "list_provider_models",
        "test_provider",
        "list_provider_api_keys",
        "get_provider_api_key",
        "upsert_provider_api_key",
        "provider_has_key",
        "delete_provider_api_key",
    }
)


@llm_bp.after_request
def add_provider_deprecation_headers(response):
    """
    Add deprecation headers to legacy provider responses.
    
    Parameters:
        response: The Flask response to process.
    
    Returns:
        The response with legacy deprecation headers when applicable.
    """
    view_name = (request.endpoint or "").rsplit(".", maxsplit=1)[-1]
    if view_name in _LEGACY_PROVIDER_VIEW_NAMES:
        return add_legacy_deprecation_headers(response)
    return response


_store_instance: ProviderConnectionStore | None = None


def get_provider_connection_store() -> ProviderConnectionStore:
    """Build the canonical metadata store on demand for process-safe API use."""
    global _store_instance
    if _store_instance is None:
        _store_instance = ProviderConnectionStore()
    return _store_instance


def get_provider_connection_service() -> ProviderConnectionService:
    store = get_provider_connection_store()
    secrets_store: LlmProviderSecretsStore = get_llm_provider_secrets_store()
    return ProviderConnectionService(store=store, secrets_store=secrets_store)


def _connection_or_404(connection_id: str) -> ProviderConnection | None:
    return next(
        (
            connection
            for connection in get_provider_connection_store().list_connections()
            if connection.id == connection_id
        ),
        None,
    )


def _invalid_connection_request() -> tuple:
    return json_error("Invalid provider connection request", status=400, code="invalid_request")


def _probe_response(connection: ProviderConnection) -> tuple:
    if not connection.enabled:
        return json_error(
            "Disabled provider connections cannot be tested",
            status=409,
            code="invalid_status_transition",
        )
    result = get_provider_connection_service().probe(connection)
    return json_success(
        {
            "status": result.status,
            "status_message": result.status_message,
            "models_found": len(result.models),
        }
    )


# ---------------------------------------------------------------------------
# Canonical provider-connection lifecycle
# ---------------------------------------------------------------------------


@llm_bp.route("/provider-connections", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_connections():
    connections = get_provider_connection_store().list_connections()
    return json_success(
        {
            "items": [connection.model_dump(mode="json") for connection in connections],
            "total": len(connections),
        }
    )


@llm_bp.route("/provider-connections/<connection_id>", methods=["PUT"])
@handle_api_errors(logger=logger)
def upsert_provider_connection(connection_id: str):
    definition = LlmProviderRegistry.connection_definition(connection_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(connection_id)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _invalid_connection_request()
    try:
        body = ProviderConnectionUpsertRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid provider connection request",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    if connection_id != body.provider_kind:
        return json_error(
            "Connection ID must match provider kind", status=400, code="invalid_connection_id"
        )
    try:
        connection = get_provider_connection_store().upsert_connection(body)
    except RuntimeError:
        logger.error(
            "Provider-Connection konnte nicht gespeichert werden: id=%s kind=%s category=store",
            connection_id,
            body.provider_kind,
        )
        return json_error("Provider connection store unavailable", status=503, code="store_unavailable")
    return json_success(ProviderConnectionResponse(connection=connection).model_dump(mode="json"))


@llm_bp.route("/provider-connections/<connection_id>", methods=["DELETE"])
@handle_api_errors(logger=logger)
def delete_provider_connection(connection_id: str):
    store = get_provider_connection_store()
    if _connection_or_404(connection_id) is None:
        return json_error("Provider connection not found", status=404, code="not_found")
    try:
        store.delete_connection(connection_id)
    except RuntimeError:
        logger.error("Provider-Connection konnte nicht gelöscht werden: id=%s category=store", connection_id)
        return json_error("Provider connection store unavailable", status=503, code="store_unavailable")
    return json_success({"connection_id": connection_id, "status": "deleted"})


@llm_bp.route("/provider-connections/<connection_id>/test", methods=["POST"])
@handle_api_errors(logger=logger)
def test_provider_connection(connection_id: str):
    definition = LlmProviderRegistry.connection_definition(connection_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(connection_id)
    connection = _connection_or_404(connection_id)
    if connection is None:
        return json_error("Provider connection not found", status=404, code="not_found")
    return _probe_response(connection)


@llm_bp.route("/provider-connections/<connection_id>/models", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_connection_models(connection_id: str):
    definition = LlmProviderRegistry.connection_definition(connection_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(connection_id)
    connection = _connection_or_404(connection_id)
    if connection is None:
        return json_error("Provider connection not found", status=404, code="not_found")
    if not connection.enabled:
        return json_error(
            "Disabled provider connections cannot be discovered",
            status=409,
            code="invalid_status_transition",
        )
    result = get_provider_connection_service().probe(connection)
    return json_success([model.model_dump(mode="json") for model in result.models])


# ---------------------------------------------------------------------------
# Legacy compatibility adapters. All discovery is delegated to the lifecycle.
# ---------------------------------------------------------------------------


@llm_bp.route("/providers", methods=["GET"])
@handle_api_errors(logger=logger)
def list_providers():
    return json_success([provider.model_dump(mode="json") for provider in provider_registry.get_providers()])


def _legacy_connection(provider_id: str) -> ProviderConnection | None:
    connection = _connection_or_404(provider_id)
    if connection is not None:
        return connection
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if definition is None or definition.adapter_kind == "unsupported":
        return None
    # Lazy, additive migration of legacy metadata. Secret writes stay in the
    # canonical store; no key value is read or copied here.
    return get_provider_connection_store().upsert_connection(
        ProviderConnectionUpsertRequest(
            display_name=definition.display_name,
            provider_kind=cast(ProviderConnectionProviderKind, definition.provider_kind),
            base_url=definition.default_base_url,
            enabled=True,
        )
    )


def _unsupported_provider_response(provider_id: str) -> tuple:
    return json_error(
        f"Provider is unsupported for connections: {provider_id}",
        status=409,
        code="provider_unsupported",
    )


@llm_bp.route("/providers/<provider_id>/models", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_models(provider_id: str):
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(provider_id)
    connection = _legacy_connection(provider_id)
    if connection is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    if not connection.enabled:
        return json_error("Disabled provider connections cannot be discovered", status=409)
    result = get_provider_connection_service().probe(connection)
    return json_success([model.model_dump(mode="json") for model in result.models])


@llm_bp.route("/providers/<provider_id>/test", methods=["POST"])
@handle_api_errors(logger=logger)
def test_provider(provider_id: str):
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(provider_id)
    connection = _legacy_connection(provider_id)
    if connection is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    return _probe_response(connection)


# ---------------------------------------------------------------------------
# Provider-API-Key compatibility adapters. Secret storage remains central.
# ---------------------------------------------------------------------------


def _provider_or_404(provider_id: str):
    return next((provider for provider in provider_registry.get_providers() if provider.id == provider_id), None)


@llm_bp.route("/providers/api-keys", methods=["GET"])
@handle_api_errors(logger=logger)
def list_provider_api_keys():
    items = get_llm_provider_secrets_store().list_entries()
    return json_success(LlmProviderKeysListResponse(items=items, total=len(items)).model_dump(mode="json"))


@llm_bp.route("/providers/<provider_id>/api-key", methods=["GET"])
@handle_api_errors(logger=logger)
def get_provider_api_key(provider_id: str):
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(provider_id)
    if _provider_or_404(provider_id) is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    entry = get_llm_provider_secrets_store().get_entry(provider_id)
    if entry is None:
        return json_error("API key not configured", status=404, code="not_found")
    return json_success(entry.model_dump(mode="json"))


@llm_bp.route("/providers/<provider_id>/api-key", methods=["POST", "PUT"])
@handle_api_errors(logger=logger)
def upsert_provider_api_key(provider_id: str):
    provider = _provider_or_404(provider_id)
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if provider is None or definition is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    if definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(provider_id)
    try:
        body = LlmProviderKeyCreateRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        return json_error("Invalid request body", status=400, code="invalid_request")
    try:
        get_provider_connection_store().upsert_connection(
            ProviderConnectionUpsertRequest(
                display_name=definition.display_name,
                provider_kind=cast(ProviderConnectionProviderKind, definition.provider_kind),
                base_url=body.base_url or definition.default_base_url,
                api_key=SecretStr(body.api_key),
            )
        )
        entry = get_llm_provider_secrets_store().get_entry(provider_id)
    except RuntimeError:
        logger.error("Provider-Schlüssel konnte nicht gespeichert werden: id=%s category=store", provider_id)
        return json_error("Secret store unavailable", status=503, code="secret_store_unavailable")
    status_code = 201 if request.method == "POST" else 200
    return json_success(entry.model_dump(mode="json") if entry else {"provider_id": provider_id}, status=status_code)


@llm_bp.route("/providers/<provider_id>/has-key", methods=["GET"])
@handle_api_errors(logger=logger)
def provider_has_key(provider_id: str):
    if _provider_or_404(provider_id) is None:
        return json_success({"has_key": False, "provider_id": provider_id})
    try:
        has_key = bool(get_llm_provider_secrets_store().get_plaintext(provider_id))
    except RuntimeError:
        has_key = False
    return json_success({"has_key": has_key, "provider_id": provider_id})


@llm_bp.route("/providers/<provider_id>/api-key", methods=["DELETE"])
@handle_api_errors(logger=logger)
def delete_provider_api_key(provider_id: str):
    definition = LlmProviderRegistry.connection_definition(provider_id)
    if definition is not None and definition.adapter_kind == "unsupported":
        return _unsupported_provider_response(provider_id)
    if _provider_or_404(provider_id) is None:
        return json_error(f"Provider not found: {provider_id}", status=404)
    connection = _connection_or_404(provider_id)
    if connection is not None:
        deleted = get_provider_connection_store().delete_connection(provider_id)
    else:
        deleted = get_llm_provider_secrets_store().delete(provider_id)
    if not deleted:
        return json_error("API key not configured", status=404, code="not_found")
    return json_success({"provider_id": provider_id, "status": "revoked"})
