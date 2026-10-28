"""Subprocess environment variable resolution for LLM routing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..contracts.llm_routing_contract import ResolvedRoute


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
    from . import llm_routing_seed as _seed

    env: dict[str, str] = {"LLM_MODEL_NAME": route.model}
    if run_id:
        env["AGORA_RUN_ID"] = run_id
    is_workspace_scoped = _seed.workspace_credential_id_for_run(run_id) is not None
    if is_workspace_scoped:
        env[_seed.CREDENTIAL_SCOPE_ENV_KEY] = _seed.WORKSPACE_CREDENTIAL_SCOPE_VALUE
    provider = next(
        (p for p in _seed.LlmProviderRegistry().get_providers() if p.id == route.provider_id),
        None,
    )
    # Base-URL-Auflösung symmetrisch zur Key-Auflösung in
    # ``resolve_route_api_key``: trägt die Route keine base_url — der
    # Legacy-/Workspace-Default-Pfad ohne ``ai_model_ref`` erzeugt Routen mit
    # nackter Registry-``provider_id`` —, gilt der Registry-Endpoint DERSELBEN
    # provider_id. Ohne diese Auflösung bleibt ``LLM_BASE_URL`` hier ungesetzt,
    # der OASIS-Subprozess erbt das stale ``LLM_BASE_URL`` des Backend-Prozesses
    # (``SAFE_ENV_KEYS``-Whitelist in ``process_manager``) und schickt Modell und
    # Provider-Key an einen fremden Endpoint — Root Cause des
    # ``404 model 'MiniMax-M3' not found`` trotz #852. Kein Provider-Fallback:
    # Key und URL stammen aus derselben provider_id.
    #
    # Zwischen Route und Registry-Default liegt seit diesem Fix der Store: die
    # in der UI gepflegte Connection-Base-URL gewinnt gegen den hartkodierten
    # ``default_base_url``. Ohne diese Stufe war das UI-Feld fuer Simulationen
    # wirkungslos — siehe ``store_base_url_for_provider``.
    base_url = (
        route.base_url_sanitized
        or _seed.store_base_url_for_provider(route.provider_id)
        or (provider.base_url if provider else None)
    )
    # Issue #1284 Codex-Finding: Transport-Guard als zweite Verteidigungslinie
    # hinter ``_apply_override``/``_resolve_selected_connection``, analog zum
    # ``LLMClient``-Guard fuer den direkten HTTP-Pfad. Faengt eine bereits
    # persistierte oder wiederaufgenommene Route ab (z. B. ein vor diesem Fix
    # gespeicherter ``stage_override``), die die frueheren Gates umgangen hat
    # — die OASIS-Subprozess-Route baut nie einen ``LLMClient`` und wuerde den
    # dortigen Guard sonst nicht durchlaufen. Zentrale ``detect_provider``-
    # Erkennung, keine zweite Heuristik.
    if _seed.detect_provider(base_url, route.model, mode="http") == "anthropic":
        raise ValueError(_seed.ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED)
    definition = _seed.LlmProviderRegistry.connection_definition(route.provider_id)
    is_cli_transport = definition is not None and definition.transport == "cli"
    if is_cli_transport:
        # Issue #1423: für einen CLI-Provider ist die fehlende ``base_url``
        # der Normalfall, kein ungelöster Zustand. Der Subprozess darf das
        # ``LLM_BASE_URL`` des Backends NICHT erben — genau daran ging das
        # geroutete Modell an den ``.env``-Endpunkt (beobachtet:
        # ``gpt-5.6-luna`` an ``api.minimax.io`` → HTTP 400 (2013)).
        # ``process_manager`` entfernt das geerbte Feld, wenn dieses Signal
        # gesetzt ist; die Runner wählen daran den CLI-Transport überhaupt.
        # ``CLI_PROVIDER_ENV_KEY`` benennt zusätzlich WELCHEN CLI-Provider
        # (codex_cli/claude_cli) — mit zwei CLI-Providern reicht das reine
        # Transport-Signal allein nicht mehr, um die Model-Klasse zu wählen.
        env[_seed.TRANSPORT_ENV_KEY] = _seed.CLI_TRANSPORT_VALUE
        env[_seed.CLI_PROVIDER_ENV_KEY] = route.provider_id
    elif not base_url and route.provider_id:
        # Weder Route noch Registry kennen einen Endpoint: der Subprozess wird
        # das Parent-``LLM_BASE_URL`` erben (Alt-Verhalten, Standalone-/
        # Dev-Pfad). Sichtbar machen statt still driften.
        _seed.logger.warning(
            "build_route_subprocess_env: keine base_url für provider_id=%s "
            "auflösbar — Subprozess erbt LLM_BASE_URL aus dem Backend-Env",
            route.provider_id,
        )
    if api_key:
        secret_env: dict[str, str] = {"LLM_API_KEY": api_key, "OPENAI_API_KEY": api_key}
        if provider and provider.api_key_ref:
            secret_env[provider.api_key_ref] = api_key
        # CAMELs GeminiModel (OASIS-Subprozess) liest ``GEMINI_API_KEY``; der
        # Google-Provider fuehrt aber ``api_key_ref="GOOGLE_API_KEY"``. Ohne
        # diesen Alias crasht der Subprozess trotz Store-Key mit
        # ``Missing required API keys: GEMINI_API_KEY``. Der Alias haelt den
        # UI-Secrets-Store als Single Source — kein ``.env`` fuer Gemini-Sims.
        if _seed.detect_provider(base_url, route.model, mode="oasis") == "google":
            secret_env["GEMINI_API_KEY"] = api_key
        # Finding B1 (Security-Review 2026-09-26, #1688): eine Workspace-
        # eigene Zugangsdaten darf nie im Klartext im Subprozess-Env landen —
        # jeder Prozess mit demselben OS-User (auf einer Demo-Instanz: jede
        # gleichzeitig laufende Simulation jedes Workspace) kann
        # ``/proc/<pid>/environ`` eines Geschwisterprozesses lesen. Statt
        # ``env.update(secret_env)`` (Operator-Pfad, unveraendert) wird das
        # Secret hinter einem privaten Marker verpackt; ``_build_subprocess_env``
        # in ``process_environment.py`` wandelt ihn in eine Pipe-FD um, bevor
        # ``subprocess.Popen`` je aufgerufen wird — die Env-Merge-Logik dort
        # laesst diesen Marker nie unveraendert durch.
        if is_workspace_scoped:
            env[_seed.WORKSPACE_SECRET_ENV_MARKER] = json.dumps(secret_env)
        else:
            env.update(secret_env)
    elif is_workspace_scoped:
        # Finding H5: a workspace-scoped run must ALWAYS get a pipe, even
        # when no key resolved (empty payload) — the child treats a
        # missing pipe (no marker at all) as a hard failure via
        # AGORA_CREDENTIAL_SCOPE, so this must not look like "no marker
        # means operator run, .env is fine" for a workspace run that
        # happens to have no resolvable key.
        env[_seed.WORKSPACE_SECRET_ENV_MARKER] = json.dumps({})
    if base_url:
        env["LLM_BASE_URL"] = base_url
        env["OPENAI_BASE_URL"] = base_url
        env["OPENAI_API_BASE"] = base_url
        env["OPENAI_API_BASE_URL"] = base_url
    return env
