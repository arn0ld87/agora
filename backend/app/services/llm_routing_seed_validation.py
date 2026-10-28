"""Pre-validation and connection verification helpers for LLM routing seeding."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..contracts.ai_provider_contract import AiModelRef, ProviderConnection


def _resolve_selected_connection(connection_id: str) -> ProviderConnection:
    """Resolve an explicitly selected ProviderConnection by id."""
    from . import llm_routing_seed as _seed

    match = next(
        (c for c in _seed.ProviderConnectionStore().list_connections() if c.id == connection_id),
        None,
    )
    if match is None:
        raise ValueError(f"ProviderConnection {connection_id!r} nicht gefunden")
    if not match.enabled:
        raise ValueError(f"ProviderConnection {connection_id!r} ist deaktiviert")
    _seed._reject_anthropic_connection(match)
    return match


def _verify_selected_model(connection: ProviderConnection, model_id: str) -> None:
    """Prüft per Live-Discovery, dass ``model_id`` tatsächlich zum Modell-Katalog
    von ``connection`` gehört (Issue #819)."""
    from . import llm_routing_seed as _seed

    workspace_id = _seed.workspace_credential_id_for_run(None)
    if workspace_id is not None:
        if not _seed.WorkspaceProviderCredentialsStore().get_plaintext(workspace_id, connection.id):
            raise ValueError("Workspace provider credential is missing")
        return

    service = _seed.ProviderConnectionService(
        store=_seed.ProviderConnectionStore(),
        secrets_store=_seed.get_llm_provider_secrets_store(),
    )
    try:
        result = service.probe(connection)
    except Exception as exc:  # noqa: BLE001 — Providerfehler dürfen keine Secrets propagieren
        _seed.logger.warning(
            "Model-Discovery fehlgeschlagen [connection_id=%s, error_type=%s]",
            connection.id,
            type(exc).__name__,
        )
        raise ValueError(
            f"Modell-Katalog für ProviderConnection {connection.id!r} derzeit "
            f"nicht abrufbar ({type(exc).__name__})"
        ) from None
    if result.status != "available":
        raise ValueError(
            f"Modell-Katalog für ProviderConnection {connection.id!r} derzeit "
            f"nicht abrufbar ({result.status})"
        )
    known_model_ids = {model.model_id for model in result.models}
    if model_id not in known_model_ids:
        raise ValueError(
            f"Modell {model_id!r} gehört nicht zur ProviderConnection {connection.id!r}"
        )


def _assert_connection_secret_bound(connection: ProviderConnection) -> None:
    """Prüft die Secret-Bindung, ohne Route-Options zu konfigurieren."""
    from . import llm_routing_seed as _seed

    _seed._bind_connection_secret(connection, {})


def _bind_connection_secret(
    connection: ProviderConnection, options: dict[str, object]
) -> None:
    """Bindet das Secret einer api_key-Connection strikt an die Route-Options."""
    from . import llm_routing_seed as _seed

    workspace_id = _seed.workspace_credential_id_for_run(None)
    if workspace_id is not None:
        if connection.auth_mode != "api_key":
            raise ValueError(
                f"ProviderConnection {connection.id!r}: Workspace-Runs "
                "dürfen nicht an eine keyless/lokale Connection routen"
            )
        if not _seed.WorkspaceProviderCredentialsStore().get_plaintext(workspace_id, connection.id):
            raise ValueError("Workspace provider credential is missing")
        options["connection_only"] = True
        return
    if connection.auth_mode != "api_key":
        return
    if not connection.secret_ref:
        raise ValueError(
            f"ProviderConnection {connection.id!r}: Cloud-Connection ohne "
            "gebundenes Secret — kein .env-Fallback für Report-Routen"
        )
    options["secret_ref"] = connection.secret_ref
    options["connection_only"] = True


def prevalidate_ai_model_ref(ai_model_ref: AiModelRef) -> ProviderConnection:
    """Günstige Vorab-Prüfung einer ``ai_model_ref`` ohne Live-Discovery."""
    from . import llm_routing_seed as _seed

    connection = _seed._resolve_selected_connection(ai_model_ref.provider_connection_id)
    _seed._assert_connection_secret_bound(connection)
    return connection


def prevalidate_ai_model_ref_with_discovery(
    ai_model_ref: AiModelRef,
) -> ProviderConnection:
    """Vollständige AiModelRef-Prüfung inklusive bestehender Model-Discovery."""
    from . import llm_routing_seed as _seed

    connection = _seed.prevalidate_ai_model_ref(ai_model_ref)
    _seed._verify_selected_model(connection, ai_model_ref.model_id)
    return connection
