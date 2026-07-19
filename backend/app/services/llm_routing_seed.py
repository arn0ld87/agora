"""Helpers to seed per-run LLM routing from the legacy request overrides.

Bridges the existing ``llm_model`` / ``llm_provider`` request contract to the
new ``RuntimeLlmRouting`` persistence model so runtime snapshots and stage locks
can be used without a flag day across all API surfaces.
"""

from __future__ import annotations

import os
from typing import Optional

from ..contracts.llm_routing_contract import ResolvedRoute, RuntimeLlmRouting, StageId, StageLLMRoute
from ..llm.providers.registry import detect_provider
from .llm_provider_registry import LlmProviderRegistry
from .llm_provider_secrets_store import get_llm_provider_secrets_store
from .llm_profiles_store import get_llm_profiles_store
from .llm_runtime import RuntimeLlmConfig
from .profile_connection_resolver import resolve_profile_connection
from .provider_connection_store import ProviderConnectionStore
from .runtime_run_config import RuntimeRunConfig
from .secret_resolver import SecretResolver, get_bound_store_api_key
from .workspace_routing_store import get_workspace_routing_store

_PROVIDER_ID_MAP = {
    "default": None,
    "openai": "openai",
    "google": "google",
    "custom_openai": "openai_compatible",
    "github_copilot": "github_copilot",
}

_ROUTE_TO_RUNTIME_PROVIDER = {
    "openai": "openai",
    "google": "google",
    "openai_compatible": "custom_openai",
    "ollama_cloud": "custom_openai",
    "github_copilot": "custom_openai",
}


def map_runtime_provider_to_route_provider(provider: str) -> Optional[str]:
    return _PROVIDER_ID_MAP.get((provider or "default").strip().lower())


def seed_run_stage_routing(
    run_id: str,
    stage_id: StageId,
    *,
    llm_model_override: Optional[str],
    llm_runtime: Optional[RuntimeLlmConfig],
    llm_profile_id: Optional[str] = None,
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
        try:
            workspace_defaults = get_workspace_routing_store().load()
        except Exception:  # noqa: BLE001 — Defaults sind „best effort", kein Run-Stopper
            workspace_defaults = None
        if workspace_defaults is not None:
            if workspace_defaults.global_default.model:
                config.global_default = workspace_defaults.global_default
            for ws_stage_id, ws_route in workspace_defaults.stage_overrides.items():
                config.stage_overrides[ws_stage_id] = ws_route

    runtime = llm_runtime or RuntimeLlmConfig()
    route_provider_id = map_runtime_provider_to_route_provider(runtime.provider)

    if llm_model_override or runtime.enabled:
        provider_options = {}
        if runtime.base_url:
            provider_options["base_url"] = runtime.base_url
        # Wenn der Request "default" als Provider schickt, mappt das Provider-ID-Dict
        # auf None. ResolvedRoute.provider_id ist Pflichtfeld; deshalb auf den
        # global_default des Runs zurückfallen statt None zu persistieren.
        effective_provider_id = route_provider_id or config.global_default.provider_id
        effective_model = llm_model_override or config.global_default.model
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=effective_provider_id,
            model=effective_model,
            provider_options=provider_options,
        )
        if has_existing_config:
            config.routing_version += 1
    elif llm_profile_id:
        profile = get_llm_profiles_store().get(
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
        provider_options: dict[str, object] = {"base_url": resolved.base_url}
        # Nur echte api_key-Connections an ihr gebundenes Secret koppeln. Lokale
        # No-Auth-Connections (auth_mode="none") würden über connection_only sonst
        # auf ein nicht existentes Secret zeigen; die strikte Auflösung liefert dann
        # None und der Run bricht mit "LLM_API_KEY not configured" — das lokale
        # Ollama-Betriebsmodell bliebe gebrochen. Die Auth-Semantik der
        # ProviderConnection ist maßgeblich (SSoT), kein pauschales connection_only.
        if connection.auth_mode == "api_key" and connection.secret_ref:
            provider_options["secret_ref"] = connection.secret_ref
            provider_options["connection_only"] = True
        config.stage_overrides[stage_id] = StageLLMRoute(
            provider_id=connection.id,
            model=profile.model_name,
            provider_options=provider_options,
        )
        if has_existing_config:
            config.routing_version += 1

    config_service.save_config(config)
    return config


def resolve_route_api_key(route: ResolvedRoute, llm_runtime: Optional[RuntimeLlmConfig] = None) -> Optional[str]:
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


def build_runtime_llm_config(route: ResolvedRoute, api_key: Optional[str]) -> RuntimeLlmConfig:
    """Bridge a resolved route back into the legacy RuntimeLlmConfig contract."""
    provider = _ROUTE_TO_RUNTIME_PROVIDER.get(route.provider_id, "custom_openai")
    return RuntimeLlmConfig(
        provider=provider,
        api_key=api_key,
        base_url=route.base_url_sanitized,
    )


def build_route_subprocess_env(
    route: ResolvedRoute,
    api_key: Optional[str],
    run_id: Optional[str] = None,
) -> dict[str, str]:
    """Translate a resolved route into the subprocess environment variables expected by OASIS.
    
    Parameters:
        route (ResolvedRoute): Resolved model, provider, and endpoint configuration.
        api_key (Optional[str]): API key to expose to the subprocess.
        run_id (Optional[str]): Run identifier to expose to the subprocess.
    
    Returns:
        dict[str, str]: Environment variables containing the model, optional run identifier,
            API key aliases, and base URL settings.
    """
    env: dict[str, str] = {"LLM_MODEL_NAME": route.model}
    if run_id:
        env["AGORA_RUN_ID"] = run_id
    if api_key:
        env["LLM_API_KEY"] = api_key
        env["OPENAI_API_KEY"] = api_key
        provider = next(
            (p for p in LlmProviderRegistry().get_providers() if p.id == route.provider_id),
            None,
        )
        if provider and provider.api_key_ref:
            env[provider.api_key_ref] = api_key
        # CAMELs GeminiModel (OASIS-Subprozess) liest ``GEMINI_API_KEY``; der
        # Google-Provider fuehrt aber ``api_key_ref="GOOGLE_API_KEY"``. Ohne
        # diesen Alias crasht der Subprozess trotz Store-Key mit
        # ``Missing required API keys: GEMINI_API_KEY``. Der Alias haelt den
        # UI-Secrets-Store als Single Source — kein ``.env`` fuer Gemini-Sims.
        if detect_provider(route.base_url_sanitized, route.model, mode="oasis") == "google":
            env["GEMINI_API_KEY"] = api_key
    if route.base_url_sanitized:
        env["LLM_BASE_URL"] = route.base_url_sanitized
        env["OPENAI_BASE_URL"] = route.base_url_sanitized
        env["OPENAI_API_BASE"] = route.base_url_sanitized
        env["OPENAI_API_BASE_URL"] = route.base_url_sanitized
    return env
