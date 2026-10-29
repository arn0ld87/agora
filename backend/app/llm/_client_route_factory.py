"""Factory method from_route mixin for LLMClient."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID
from ..contracts.llm_routing_contract import ResolvedRoute

if TYPE_CHECKING:
    from .client import LLMClient


from ._client_shim import get_client_attr as _get_client_attr


class LLMClientRouteFactoryMixin:
    @classmethod
    def from_route(
        cls: Any,
        route: ResolvedRoute,
        secret_resolver: Optional["Any"] = None,
        timeout: float = 300.0,
        run_id: Optional[str] = None,
        api_key_override: Optional[str] = None,
        workspace_id: UUID | None = None,
    ) -> "LLMClient":
        """Factory: create LLMClient from a resolved stage route.

        Resolves actual base_url and api_key from the provider configuration,
        falling back to sanitized/config defaults if no resolver is provided.
        """
        base_url = route.base_url_sanitized
        connection_only = route.provider_options.get("connection_only") is True
        from ..services.llm_routing_seed import (
            validate_workspace_route,
            workspace_credential_id_for_run,
        )

        credential_workspace_id = workspace_id or workspace_credential_id_for_run(run_id)
        if credential_workspace_id is not None:
            validate_workspace_route(route)

        # Issue #1405 Codex-Review-Finding: der Provider-Typ der Route wurde
        # zwar hier nachgeschlagen (fuer die api_key-Aufloesung unten), aber
        # nie an ``cls(...)`` durchgereicht — eine explizit geroutete
        # codex_cli-Connection blieb dadurch von der globalen Active-Config
        # abhaengig statt von der tatsaechlichen Route. Reiner Metadaten-
        # Lookup, kein Secret — deshalb unabhaengig von ``secret_resolver``/
        # ``connection_only`` immer ausgefuehrt.
        from ..services.llm_provider_registry import LlmProviderRegistry
        _route_registry = LlmProviderRegistry()
        _route_descriptor = next(
            (p for p in _route_registry.get_providers() if p.id == route.provider_id),
            None,
        )
        provider_type = _route_descriptor.type if _route_descriptor else None
        api_key, api_key_source = _get_client_attr("_route_api_key")(
            route, credential_workspace_id, connection_only, api_key_override,
            secret_resolver, provider_type,
        )

        # If a secret resolver is provided, we try to get the real secrets.
        # This prevents leaking them into ResolvedRoute but allows LLMClient
        # to use them.
        if secret_resolver and not connection_only and credential_workspace_id is None:
            # Use real base_url from provider_options if present, otherwise from descriptor
            real_base = route.provider_options.get("base_url") or (
                _route_descriptor.base_url if _route_descriptor else None
            )
            if real_base:
                base_url = real_base

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=route.model,
            timeout=timeout,
            reasoning_effort=route.reasoning_effort,
            provider_options=route.provider_options,
            run_id=run_id,
            routing_version=route.routing_version,
            route_stage=route.stage,
            route_provider_id=route.provider_id,
            provider_type=provider_type,
            api_key_source=api_key_source,
            use_active_config=not connection_only and credential_workspace_id is None,
            allow_api_key_fallback=not connection_only and credential_workspace_id is None,
        )
