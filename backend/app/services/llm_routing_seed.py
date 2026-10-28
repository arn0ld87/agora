# ruff: noqa: F401, E402, F811
"""Helpers to seed per-run LLM routing from the legacy request overrides.

Bridges the existing ``llm_model`` / ``llm_provider`` request contract to the
new ``RuntimeLlmRouting`` persistence model so runtime snapshots and stage locks
can be used without a flag day across all API surfaces.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Mapping, NamedTuple, Optional, cast
from uuid import UUID

from flask import has_request_context

from ..contracts.ai_provider_contract import AiModelRef, ProviderConnection
from ..contracts.auth_contract import AuthType
from ..contracts.llm_routing_contract import (
    ResolvedRoute,
    RuntimeLlmRouting,
    StageId,
    StageLLMRoute,
)
from ..contracts.provider_types import (
    ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED,
    PROVIDER_ANTHROPIC,
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CODEX_CLI,
)
from ..llm.providers.codex_cli import (
    CLI_PROVIDER_ENV_KEY,
    CLI_TRANSPORT_VALUE,
    TRANSPORT_ENV_KEY,
)
from ..llm.providers.registry import detect_provider
from ..repositories.llm_profile_repository import get_llm_profile_repository
from ..utils.logger import get_logger
from .llm_provider_registry import LlmProviderRegistry
from .llm_provider_secrets_store import get_llm_provider_secrets_store
from .llm_routing_seed_data import (
    CREDENTIAL_SCOPE_ENV_KEY,
    WORKSPACE_CREDENTIAL_SCOPE_VALUE,
    WORKSPACE_SECRET_ENV_MARKER,
    _OPERATOR_SENTINEL,
    _PROVIDER_ID_MAP,
    _ROUTE_TO_RUNTIME_PROVIDER,
    _UNSCOPED,
    _UNSPECIFIED_FALLBACK_REASON,
    _apply_override,
    _apply_workspace_defaults,
    _assert_run_workspace_owner,
    _credential_workspace,
    _fallback_reason_for,
    _persisted_workspace_for_run,
    _prune_stage_overrides,
    _reject_anthropic_connection,
    _request_workspace_for_run,
    _RunCredentialScope,
    _workspace_id_from_run_metadata,
    build_runtime_llm_config,
    demo_mode_enabled,
    map_runtime_provider_to_route_provider,
    operator_credential_context,
    store_base_url_for_provider,
    validate_workspace_route,
    workspace_credential_context_for_run,
    workspace_credential_id_for_run,
    workspace_credential_metadata,
)
from .llm_routing_seed_env import build_route_subprocess_env
from .llm_routing_seed_validation import (
    _assert_connection_secret_bound,
    _bind_connection_secret,
    _resolve_selected_connection,
    _verify_selected_model,
    prevalidate_ai_model_ref,
    prevalidate_ai_model_ref_with_discovery,
)
from .llm_runtime import RuntimeLlmConfig
from .profile_connection_resolver import (
    canonical_connection_base_url,
    normalize_endpoint_url,
    resolve_profile_connection,
)
from .provider_connection_store import ProviderConnectionStore
from .provider_connections.service import ProviderConnectionService
from .runtime_run_config import RuntimeRunConfig
from .secret_resolver import SecretResolver, get_bound_store_api_key
from .workspace_provider_credentials_store import WorkspaceProviderCredentialsStore
from .workspace_routing_store import get_workspace_routing_store

logger = get_logger("agora.llm_routing_seed")


def build_preview_stage_route(
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
) -> ResolvedRoute:
    """Zustandslose Variante für Preview-Endpoints ohne persistierten Run
    (z. B. /simulation/generate-profiles). Nutzt denselben Workspace-Default-
    und Override-Resolver wie seed_run_stage_routing, schreibt aber nie auf
    Platte und versiegelt keine Stage — sicher für jeden Request."""
    from uuid import uuid4

    from .stage_model_router import StageModelRouter

    config = RuntimeLlmRouting(global_default=StageLLMRoute())
    _apply_workspace_defaults(config)
    _apply_override(config, stage_id, llm_model_override=llm_model_override, llm_runtime=llm_runtime)
    router = StageModelRouter(f"preview-{uuid4().hex}")
    return router.resolve(stage_id, runtime_cfg=config)


def seed_run_stage_routing(
    run_id: str,
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
    llm_profile_id: Optional[str] = None,
    ai_model_ref: Optional[AiModelRef] = None,
) -> RuntimeLlmRouting:
    """
    Persist per-run routing for a stage, applying workspace defaults and request-specific overrides.
    
    Parameters:
        run_id (str): Identifier of the run whose routing configuration is updated.
        stage_id (StageId): Identifier of the stage receiving the routing configuration.
        llm_model_override (Optional[str]): Model name to use for the stage.
        llm_runtime (Optional[RuntimeLlmConfig]): Runtime provider settings to apply.
        llm_profile_id (Optional[str]): Identifier of an LLM profile to use for the stage.
    
    Returns:
        RuntimeLlmRouting: The saved per-run routing configuration.
    
    Raises:
        ValueError: If the specified LLM profile or a compatible activated provider connection is unavailable.
    """
    config_service = RuntimeRunConfig(run_id)
    has_existing_config = os.path.exists(config_service.config_path)
    config = config_service.load_config()

    # Bei frischen Runs: Workspace-Defaults als Seed übernehmen. Versiegelte Stages
    # (= bereits in den Per-Run-Snapshots vorhanden) werden NICHT überschrieben.
    if not has_existing_config:
        _apply_workspace_defaults(config)

    # Stale-Override-Prune läuft IMMER — auch bei fresh runs kann er Workspace-
    # Defaults betreffen (z. B. workspace_routing.json aus alter Umgebung mit
    # ``ollama_cloud``-override, der in der neuen Umgebung zu 401/HTML-Antworten
    # führt). Symmetrische Behandlung zu bestehender Config: geprunete Stages
    # fallen auf den aktuellen global_default zurück.
    pruned_count = _prune_stage_overrides(config)
    if pruned_count > 0 and has_existing_config:
        _apply_workspace_defaults(config)
        config.routing_version += 1

    runtime = llm_runtime or RuntimeLlmConfig()

    if ai_model_ref is not None:
        # Höchste Priorität: die vom UI explizit gewählte (Connection, Modell)-Route.
        # Die Connection ist die SSoT für Base-URL und Secret-Bindung — kein
        # ``.env``-Fallback, keine lokale Detection-Heuristik.
        connection = _resolve_selected_connection(ai_model_ref.provider_connection_id)
        _verify_selected_model(connection, ai_model_ref.model_id)
        ref_options: dict[str, object] = {}
        connection_base_url = canonical_connection_base_url(connection)
        if connection_base_url:
            ref_options["base_url"] = connection_base_url
        _bind_connection_secret(connection, ref_options)
        # Issue #901: Herkunft und ggf. Fallback-Grund wandern mit in den
        # Snapshot. Ohne sie schrieb ai_route_from_stage_route beim Auflesen
        # hart source="legacy" — eine bewusste Nutzerwahl war danach von einem
        # Provider-Fallback nicht mehr zu unterscheiden.
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=connection.id,
            model=ai_model_ref.model_id,
            provider_options=ref_options,
            ai_model_ref_source=ai_model_ref.source,
            fallback_reason=_fallback_reason_for(ai_model_ref),
        )
        if has_existing_config:
            config.routing_version += 1
    elif llm_model_override or runtime.enabled:
        _apply_override(
            config,
            stage_id,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
        )
        if has_existing_config:
            config.routing_version += 1
    elif llm_profile_id:
        profile = get_llm_profile_repository().get(
            llm_profile_id,
            include_api_key=False,
        )
        if profile is None:
            raise ValueError(f"LLM-Profil {llm_profile_id!r} nicht gefunden")
        resolved = resolve_profile_connection(
            profile,
            ProviderConnectionStore().list_connections(),
        )
        if resolved is None:
            raise ValueError(
                f"LLM-Profil {llm_profile_id!r}: keine passende aktivierte "
                "ProviderConnection"
            )
        connection = resolved.connection
        _reject_anthropic_connection(connection)
        provider_options: dict[str, object] = {"base_url": resolved.base_url}
        # Auth-Semantik der ProviderConnection ist maßgeblich (SSoT): api_key-
        # Connections werden an ihr gebundenes Secret gekoppelt und ohne Secret
        # hart abgelehnt (Issue #817) — identisch zum ai_model_ref-Pfad, damit der
        # Profilpfad die Bindung nicht umgeht. Lokale No-Auth-Connections
        # (auth_mode="none") laufen nicht durch und bleiben auf base_url beschränkt.
        _bind_connection_secret(connection, provider_options)
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=connection.id,
            model=profile.model_name,
            provider_options=provider_options,
        )
        if has_existing_config:
            config.routing_version += 1

    config_service.save_config(config)
    return config


def resolve_route_api_key(
    route: ResolvedRoute,
    llm_runtime: Optional[RuntimeLlmConfig] = None,
    *,
    run_id: str | None = None,
    workspace_id: UUID | None = None,
) -> Optional[str]:
    """Resolve the API key for a resolved route.
    
    Connection-only routes use their bound secret reference. Other routes use a
    matching request-scoped runtime key when available, then fall back to the
    server-side provider secret.
    
    Parameters:
        route (ResolvedRoute): The resolved route whose API key is needed.
        llm_runtime (Optional[RuntimeLlmConfig]): Request-scoped runtime
            configuration that may provide a matching API key.
    
    Returns:
        Optional[str]: The resolved API key, or None when no key is available.
    """
    credential_workspace_id = workspace_id or workspace_credential_id_for_run(run_id)
    if credential_workspace_id is not None:
        validate_workspace_route(route)
        return WorkspaceProviderCredentialsStore().get_plaintext(
            credential_workspace_id, route.provider_id
        )

    if route.provider_options.get("connection_only") is True:
        raw_secret_ref = route.provider_options.get("secret_ref")
        secret_ref = raw_secret_ref if isinstance(raw_secret_ref, str) else ""
        return get_bound_store_api_key(
            secret_ref,
            secrets_store=get_llm_provider_secrets_store(),
        )

    runtime = llm_runtime or RuntimeLlmConfig()
    runtime_provider_id = map_runtime_provider_to_route_provider(runtime.provider)
    if runtime.enabled and runtime.api_key and runtime_provider_id == route.provider_id:
        return runtime.api_key

    registry = LlmProviderRegistry()
    provider = next((p for p in registry.get_providers() if p.id == route.provider_id), None)
    provider_type = provider.type if provider else "openai_compatible"
    return SecretResolver().get_api_key(route.provider_id, provider_type)


__all__ = [
    "CREDENTIAL_SCOPE_ENV_KEY",
    "WORKSPACE_CREDENTIAL_SCOPE_VALUE",
    "WORKSPACE_SECRET_ENV_MARKER",
    "_OPERATOR_SENTINEL",
    "_PROVIDER_ID_MAP",
    "_ROUTE_TO_RUNTIME_PROVIDER",
    "_UNSCOPED",
    "_UNSPECIFIED_FALLBACK_REASON",
    "_RunCredentialScope",
    "_apply_override",
    "_apply_workspace_defaults",
    "_assert_connection_secret_bound",
    "_assert_run_workspace_owner",
    "_bind_connection_secret",
    "_credential_workspace",
    "_fallback_reason_for",
    "_persisted_workspace_for_run",
    "_prune_stage_overrides",
    "_reject_anthropic_connection",
    "_request_workspace_for_run",
    "_resolve_selected_connection",
    "_verify_selected_model",
    "_workspace_id_from_run_metadata",
    "build_preview_stage_route",
    "build_route_subprocess_env",
    "build_runtime_llm_config",
    "demo_mode_enabled",
    "map_runtime_provider_to_route_provider",
    "operator_credential_context",
    "prevalidate_ai_model_ref",
    "prevalidate_ai_model_ref_with_discovery",
    "resolve_route_api_key",
    "seed_run_stage_routing",
    "store_base_url_for_provider",
    "validate_workspace_route",
    "workspace_credential_context_for_run",
    "workspace_credential_id_for_run",
    "workspace_credential_metadata",
]
