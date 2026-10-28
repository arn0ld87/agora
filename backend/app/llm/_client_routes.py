"""Route resolution and secrets helpers for LLMClient."""

from typing import Any, Optional
from uuid import UUID

from ..contracts.llm_routing_contract import ResolvedRoute
from ..utils.logger import get_logger
from .json_mode import _read_active_config_safely

logger = get_logger("agora.llm_client")


def _get_client_attr(name: str, default: Any = None) -> Any:
    import sys

    mod = sys.modules.get("app.llm.client")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return default


def get_llm_provider_secrets_store() -> Any:
    """Load the secrets store lazily to avoid the services package import cycle."""
    from ..services.llm_provider_secrets_store import get_llm_provider_secrets_store as get_store

    return get_store()


def _lookup_provider_descriptor(provider_id: str) -> Any:
    """Sucht den Provider-Descriptor zu ``provider_id`` in der Registry.

    Einzige Typ-Quelle fuer die Init-Audit-Zeile. Bewusst keine Ableitung
    aus ``base_url`` oder Modellnamen: das waere eine zweite
    Detection-Heuristik neben ``registry.py::detect_provider`` und laut
    AGENTS.md unzulaessig.

    Ein Registry-Fehler darf den Konstruktor nie brechen — er wird
    geloggt, der Aufrufer faellt auf ``None`` zurueck.
    """
    try:
        from ..services.llm_provider_registry import LlmProviderRegistry

        return next(
            (p for p in LlmProviderRegistry().get_providers() if p.id == provider_id),
            None,
        )
    except Exception as exc:  # noqa: BLE001 — Provider-Aufloesung darf den Init nicht brechen
        logger.warning(
            "Failed to resolve provider descriptor (provider=%s): %s",
            provider_id,
            exc,
        )
        return None


def _resolve_active_api_key(
    provider_id: str, provider_type: str, current_source: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Loest den API-Key der Active-Config auf.

    Liefert ``(api_key, api_key_source)``. Schlaegt die Aufloesung fehl,
    bleibt der Key ``None`` und die bisherige Quelle erhalten — der
    Konstruktor faellt dann auf die ``Config``-Defaults zurueck.
    """
    try:
        from ..services.secret_resolver import SecretResolver

        resolver = SecretResolver()
        api_key = resolver.get_api_key(provider_id, provider_type)
        if api_key:
            return api_key, resolver.last_source
        return api_key, current_source
    except Exception as exc:  # noqa: BLE001 — fall back to Config defaults
        logger.warning(
            "Failed to resolve active LLM config (provider=%s): %s",
            provider_id,
            exc,
        )
        return None, current_source


def _apply_active_config(
    model: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    resolved_source: Optional[str],
    provider_type: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    active = _get_client_attr("_read_active_config_safely", _read_active_config_safely)()
    if not active:
        return model, base_url, api_key, resolved_source, provider_type, None
    active_pid = active.get("provider_id")
    active_model = active.get("model")
    active_base = active.get("base_url")
    active_used = False
    if active_model and not model:
        model = active_model
        active_used = True
    if active_base and not base_url:
        base_url = active_base
        active_used = True
    if active_pid and not api_key:
        active_used = True
        descriptor = _get_client_attr("_lookup_provider_descriptor", _lookup_provider_descriptor)(active_pid)
        if descriptor is not None:
            if provider_type is None:
                provider_type = descriptor.type
            if not base_url:
                base_url = descriptor.base_url
            api_key, resolved_source = _get_client_attr("_resolve_active_api_key", _resolve_active_api_key)(
                active_pid, descriptor.type, resolved_source
            )
    if active_pid and active_used and provider_type is None:
        descriptor = _get_client_attr("_lookup_provider_descriptor", _lookup_provider_descriptor)(active_pid)
        if descriptor is not None:
            provider_type = descriptor.type
    active_provider_id = active_pid if active_pid and active_used else None
    return model, base_url, api_key, resolved_source, provider_type, active_provider_id


def _route_api_key(
    route: ResolvedRoute,
    credential_workspace_id: UUID | None,
    connection_only: bool,
    api_key_override: Optional[str],
    secret_resolver: Any,
    provider_type: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if credential_workspace_id is not None:
        from ..services.workspace_provider_credentials_store import WorkspaceProviderCredentialsStore

        api_key = WorkspaceProviderCredentialsStore().get_plaintext(
            credential_workspace_id, route.provider_id
        )
        return api_key, "workspace_store" if api_key else None
    if connection_only:
        from ..services.secret_resolver import get_bound_store_api_key

        raw_secret_ref = route.provider_options.get("secret_ref")
        secret_ref = raw_secret_ref if isinstance(raw_secret_ref, str) else ""
        api_key = get_bound_store_api_key(
            secret_ref,
            secrets_store=_get_client_attr("get_llm_provider_secrets_store", get_llm_provider_secrets_store)(),
        )
        return api_key, "store" if api_key else None
    api_key = api_key_override
    api_key_source = "passed_in" if api_key_override else None
    if secret_resolver and not api_key:
        api_key = secret_resolver.get_api_key(route.provider_id, provider_type or "unknown")
        api_key_source = getattr(secret_resolver, "last_source", None)
    return api_key, api_key_source
