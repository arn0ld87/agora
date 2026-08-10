"""API für Embedding-Konfigurationen (Onboarding Slice 4.2).

Routen unter ``/api/llm/embedding/configurations``:

* ``GET /`` listet alle Konfigurationen (optional ``?scope=global|project``).
* ``GET /active`` liefert die aktive globale Konfiguration, oder
  falls keine existiert, die aus ``Config.EMBEDDING_*`` abgeleitete
  Legacy-Sicht.
* ``GET /<id>`` liefert eine einzelne Konfiguration.
* ``PUT /<id>`` legt eine neue Konfiguration an oder aktualisiert sie.
  Bei ``id="legacy-embedding"`` wird der Body als Update der Legacy-Sicht
  interpretiert und in eine persistente Konfiguration umgewandelt.
* ``DELETE /<id>`` loescht eine Konfiguration.
* ``POST /<id>/test`` fuehrt die Probe aus und aktualisiert den Status.
* ``POST /sync-legacy`` uebernimmt ``Config.EMBEDDING_*`` als neue,
  persistente Konfiguration (Status ``proposed``), sofern noch keine
  aktive globale Konfiguration existiert.

Die Routen folgen dem Slice-3-Stil: ``handle_api_errors``-Decorator,
``json_success``/``json_error``, ``pydantic.ValidationError`` → 400,
``KeyError`` → 404. Secrets sind explizit ausgeschlossen — der Aufrufer
verweist nur per ``provider_connection_id`` auf eine bereits angelegte
Verbindung, der API-Key liegt im Secret-Store.
"""

from __future__ import annotations

from typing import Optional

from flask import request
from pydantic import ValidationError

from . import llm_bp
from ..contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationUpsertRequest,
    EmbeddingLegacySyncRequest,
)
from ..services.embedding_configuration_store import EmbeddingConfigurationStore
from ..services.embedding_configurations.legacy import (
    build_legacy_view,
    legacy_view_to_configuration,
)
from ..services.embedding_configurations.service import (
    EmbeddingConfigurationService,
)
from ..services.llm_provider_secrets_store import (
    get_llm_provider_secrets_store,
)
from ..services.provider_connection_store import ProviderConnectionStore
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

logger = get_logger("agora.api.embedding_configurations")

_store_instance: EmbeddingConfigurationStore | None = None


def get_embedding_configuration_store() -> EmbeddingConfigurationStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = EmbeddingConfigurationStore()
    return _store_instance


def get_embedding_configuration_service() -> EmbeddingConfigurationService:
    return EmbeddingConfigurationService(
        store=get_embedding_configuration_store(),
        connection_store=ProviderConnectionStore(),
        secrets_store=get_llm_provider_secrets_store(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_404(configuration_id: str) -> EmbeddingConfiguration | None:
    return get_embedding_configuration_store().get_configuration(configuration_id)


def _ensure_known_provider_connection(connection_id: str) -> None:
    """Wirft ``KeyError``, wenn die Provider-Connection nicht existiert.

    Wird vom Service genutzt, um 409/400 von 404 zu trennen.
    """
    for connection in ProviderConnectionStore().list_connections():
        if connection.id == connection_id:
            return
    raise KeyError(f"Unbekannte Provider-Connection: {connection_id}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@llm_bp.route("/embedding/configurations", methods=["GET"])
@handle_api_errors(logger=logger)
def list_embedding_configurations():
    scope_raw: Optional[str] = request.args.get("scope")
    scope: str | None = None
    if scope_raw:
        if scope_raw not in ("global", "project"):
            return json_error(
                f"Ungültiger scope: {scope_raw}",
                status=400,
                code="invalid_request",
            )
        scope = scope_raw
    configs = get_embedding_configuration_store().list_configurations(scope=scope)
    return json_success(
        {
            "configurations": [
                c.model_dump(mode="json") for c in configs
            ],
        }
    )


@llm_bp.route("/embedding/configurations/active", methods=["GET"])
@handle_api_errors(logger=logger)
def get_active_embedding_configuration():
    config = get_embedding_configuration_store().get_active_global_configuration()
    if config is not None:
        return json_success(
            {"configuration": config.model_dump(mode="json"), "source": "store"}
        )
    legacy = build_legacy_view()
    if legacy is None:
        return json_success({"configuration": None, "source": "none"})
    return json_success(
        {
            "configuration": legacy_view_to_configuration(legacy).model_dump(mode="json"),
            "source": "legacy",
        }
    )


@llm_bp.route(
    "/embedding/configurations/<configuration_id>", methods=["GET"]
)
@handle_api_errors(logger=logger)
def get_embedding_configuration(configuration_id: str):
    config = _get_or_404(configuration_id)
    if config is None:
        return json_error(
            f"Unbekannte Embedding-Konfiguration: {configuration_id}",
            status=404,
            code="not_found",
        )
    return json_success({"configuration": config.model_dump(mode="json")})


@llm_bp.route(
    "/embedding/configurations/<configuration_id>", methods=["PUT"]
)
@handle_api_errors(logger=logger)
def upsert_embedding_configuration(configuration_id: str):
    try:
        payload = request.get_json(force=True, silent=False) or {}
        request_model = EmbeddingConfigurationUpsertRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid embedding configuration request",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    try:
        _ensure_known_provider_connection(request_model.provider_connection_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")

    target_id: str | None = (
        None if configuration_id == "new" else configuration_id
    )
    config = get_embedding_configuration_store().upsert_configuration(
        configuration_id=target_id,
        provider_connection_id=request_model.provider_connection_id,
        provider_kind=request_model.provider_kind,
        model_id=request_model.model_id,
        dimensions=request_model.dimensions,
        scope=request_model.scope,
        project_id=request_model.project_id,
        status="proposed",
    )
    return json_success({"configuration": config.model_dump(mode="json")})


@llm_bp.route(
    "/embedding/configurations/<configuration_id>", methods=["DELETE"]
)
@handle_api_errors(logger=logger)
def delete_embedding_configuration(configuration_id: str):
    deleted = get_embedding_configuration_store().delete_configuration(configuration_id)
    if not deleted:
        return json_error(
            f"Unbekannte Embedding-Konfiguration: {configuration_id}",
            status=404,
            code="not_found",
        )
    return json_success({"deleted": True})


@llm_bp.route(
    "/embedding/configurations/<configuration_id>/test", methods=["POST"]
)
@handle_api_errors(logger=logger)
def test_embedding_configuration(configuration_id: str):
    try:
        config, result = get_embedding_configuration_service().probe(configuration_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    return json_success(
        {
            "configuration": config.model_dump(mode="json"),
            "probe": {
                "status": result.status,
                "status_message": result.status_message,
                "actual_dimensions": result.actual_dimensions,
            },
        }
    )


@llm_bp.route(
    "/embedding/configurations/<configuration_id>/activate", methods=["POST"]
)
@handle_api_errors(logger=logger)
def activate_embedding_configuration(configuration_id: str):
    try:
        config = get_embedding_configuration_service().activate(configuration_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")
    except ValueError as exc:
        return json_error(str(exc), status=409, code="invalid_status_transition")
    return json_success({"configuration": config.model_dump(mode="json")})


@llm_bp.route("/embedding/configurations/sync-legacy", methods=["POST"])
@handle_api_errors(logger=logger)
def sync_legacy_embedding_configuration():
    try:
        payload = request.get_json(force=True, silent=False) or {}
        request_model = EmbeddingLegacySyncRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid embedding legacy-sync request",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    try:
        _ensure_known_provider_connection(request_model.provider_connection_id)
    except KeyError as exc:
        return json_error(str(exc), status=404, code="not_found")

    view = build_legacy_view()
    if view is None:
        return json_error(
            "Keine Legacy-Embedding-Konfiguration vorhanden (Config.EMBEDDING_* leer)",
            status=409,
            code="no_legacy_config",
        )

    config = get_embedding_configuration_service().sync_legacy(
        provider_connection_id=request_model.provider_connection_id,
        provider_kind=view.provider_kind,
        model_id=view.model_id,
        dimensions=view.dimensions,
    )
    if config is None:
        return json_error(
            "Es existiert bereits eine aktive globale Embedding-Konfiguration",
            status=409,
            code="active_configuration_exists",
        )
    return json_success({"configuration": config.model_dump(mode="json")})
