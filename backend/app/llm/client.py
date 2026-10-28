# ruff: noqa: F401, E402, F811
"""
LLM Client Wrapper
Unified OpenAI format API calls
Supports Ollama num_ctx parameter to prevent prompt truncation

``LLMClient`` facade — extracted from ``app/utils/llm_client.py`` (#582,
mechanical split, no behavior change). Provider-specific quirks live in
``app.llm.providers.*``, num_ctx heuristics in ``app.llm.context``, JSON-mode
orchestration in ``app.llm.json_mode``, and native tool-calling in
``app.llm.tool_calls``.
"""

import os
import re
import time as _time_mod
from uuid import UUID
from typing import Literal, Optional, Dict, Any, List, Tuple
from openai import OpenAI
from pydantic import BaseModel

from ..config import Config
from ..contracts.provider_types import (
    ANTHROPIC_CHAT_TRANSPORT_UNSUPPORTED,
    PROVIDER_CLAUDE_CLI,
    PROVIDER_CODEX_CLI,
)
from ..contracts.llm_routing_contract import ResolvedRoute, ReasoningEffort
from ..utils.logger import get_logger
from ..utils.retry import llm_call_with_retry

from .context import _resolve_num_ctx
from .tokens import resolve_max_tokens, resolve_num_ctx_for_output
# Re-Export: ``from app.llm.client import LLMOutputTruncatedError`` bleibt der
# gewohnte Importpfad, auch wenn der Typ jetzt in ``errors`` lebt (Provider-
# Adapter brauchen ihn und werden von diesem Modul importiert).
from .errors import LLMOutputTruncatedError  # noqa: F401  (re-exported)
from .json_mode import (
    JsonSchemaLike,
    _STRICT_UNSUPPORTED_HINTS,
    _enforce_openai_strict_schema,
    _env_flag,
    _is_json_object_mode_disabled,
    _is_json_schema_mode_disabled,
    _read_active_config_safely,
    _parse_llm_json,
    _strip_llm_json_envelope,
)
from .providers import base as _provider_base
from .providers import ollama as _provider_ollama
from .providers import openai as _provider_openai
from .providers.claude_cli import ClaudeCliClient
from .providers.codex_cli import CodexCliClient
from .providers.registry import openai_compat_base_url
from .request_plan import (
    REASONING_EFFORT_QUIRK,
    TEMPERATURE_QUIRK,
    TOKEN_KEY_QUIRK,
    build_request,
    execute,
    thinking_extra_body,
)
from .tool_calls import _chat_with_tools
from .transport_security import ensure_credentialed_transport_security

logger = get_logger("agora.llm_client")



# Re-exported helper functions from _client_routes
from ._client_routes import (
    get_llm_provider_secrets_store,
    _lookup_provider_descriptor,
    _resolve_active_api_key,
    _apply_active_config,
    _route_api_key,
)
from ._client_quirks import LLMClientQuirksMixin
from ._client_telemetry import LLMClientTelemetryMixin
from ._client_transport import LLMClientTransportMixin
from ._client_route_factory import LLMClientRouteFactoryMixin
from ._client_chat import LLMClientChatMixin
from ._client_vision import LLMClientVisionMixin
from ._client_json import LLMClientJsonMixin


class LLMClient(
    LLMClientQuirksMixin,
    LLMClientTelemetryMixin,
    LLMClientTransportMixin,
    LLMClientRouteFactoryMixin,
    LLMClientChatMixin,
    LLMClientVisionMixin,
    LLMClientJsonMixin,
):
    """Client facade for OpenAI-compatible LLM interactions."""

    _codex_cli_active: bool = False
    _claude_cli_active: bool = False

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0,
        reasoning_effort: Optional[ReasoningEffort] = None,
        provider_options: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        routing_version: Optional[int] = None,
        route_stage: Optional[str] = None,
        route_provider_id: Optional[str] = None,
        use_active_config: bool = True,
        api_key_source: Optional[str] = None,
        allow_api_key_fallback: bool = True,
        provider_type: Optional[str] = None,
    ):
        # When no explicit model is set, fall back to the user's active
        # provider/model selection (Settings → LLM-Auswahl). Falls back to
        # Config.* if no active config exists. Resolves api_key+base_url via
        # SecretResolver/Provider-Registry analogous to from_route().
        # ``api_key_source`` ist eine Audit-Annotation für das einmalige
        # Init-Log am Ende dieses Konstruktors. Track 1c (Pure-Gosling).
        # Ein übergebener api_key ohne explizite Annotation gilt als "passed_in"
        # (Caller hat den Key direkt übergeben), statt auf "unknown" durchzufallen.
        resolved_source: Optional[str] = (api_key_source or "passed_in") if api_key else None
        from ..services.llm_routing_seed import workspace_credential_id_for_run

        if workspace_credential_id_for_run(run_id) is not None:
            use_active_config = False
            allow_api_key_fallback = False
            if not api_key or not base_url or not model:
                raise ValueError("Workspace LLM route requires explicit model, endpoint and credential")
        active_provider_id: Optional[str] = None
        # Issue #1405: codex_cli hat weder base_url noch api_key — die
        # Ollama/Minimax-URL-Heuristiken und der OpenAI-SDK-Client-Bau
        # muessen dafuer explizit kurzgeschlossen werden statt sich auf
        # Zufallstreffer eines (u.U. Ollama-artigen) Config.LLM_BASE_URL zu
        # verlassen. Seed aus dem expliziten ``provider_type``-Parameter
        # (z. B. von ``from_route()`` aus der geroutet Stage/Run-Connection
        # abgeleitet) — Codex-Review-Finding: vorher wurde dieser Wert nur
        # aus der GLOBALEN Active-Config gelesen, wodurch eine explizit
        # geroutete codex_cli-Connection ignoriert wurde, sobald sie nicht
        # zugleich der globale Default war.
        resolved_provider_type: Optional[str] = provider_type
        # Issue #1101: Active-Config-Lookup ist Fallback für fehlende Werte,
        # nicht an ``model is None`` gekoppelt. Wurde das Modell vom Caller
        # explizit übergeben (Normalfall im Prepare/Run-Pfad:
        # ``prepare_simulation(llm_model=resolved_route.model, …)``), fiel
        # zuvor der *gesamte* Block weg — inkl. ``base_url``-Übernahme — und
        # ``base_url`` kollabierte auf ``Config.LLM_BASE_URL`` (.env-Ollama-
        # Gateway). Das Modell aus der UI-Auswahl (OpenAI) ging an den
        # .env-Endpoint → HTTP 404 → stiller regelbasierter Persona-Fallback.
        # Aktive Config überschreibt niemals explizit übergebene Werte.
        # ``active_provider_id`` annotiert das Init-Log (Vorrang vor
        # ``route_provider_id``) sobald die Active-Config für einen Lookup
        # herangezogen wurde (model, base_url oder api_key). Hat der Caller
        # alle drei explizit übergeben, behält die aufgelöste Route den Vorrang.
        if use_active_config:
            (
                model,
                base_url,
                api_key,
                resolved_source,
                resolved_provider_type,
                active_provider_id,
            ) = _apply_active_config(model, base_url, api_key, resolved_source, resolved_provider_type)

        self.model = model or Config.LLM_MODEL_NAME
        self.reasoning_effort = reasoning_effort or "none"
        self.provider_options = provider_options or {}
        self.run_id = run_id or os.environ.get("AGORA_RUN_ID")
        self.routing_version = routing_version
        self.route_stage = route_stage
        self.route_provider_id = route_provider_id

        # Issue #1405: setzt self.api_key/self.base_url/self.client/
        # self._codex_cli_active und baut den Transport auf (OpenAI-SDK oder
        # CodexCliClient-Shim). Ausgelagert aus __init__ (radon MAI-17-Gate) —
        # die codex_cli-Fallunterscheidung braucht mehrere Branches, die in
        # __init__ selbst die Komplexitäts-Obergrenze gerissen haetten.
        resolved_source = self._resolve_transport(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            resolved_provider_type=resolved_provider_type,
            resolved_source=resolved_source,
            allow_api_key_fallback=allow_api_key_fallback,
        )

        # Track 1c Audit-Log: einmalig pro LLMClient-Init. Niemals den Key-Wert
        # selbst loggen — nur die Quelle (session/store/env:NAME/config_fallback/
        # passed_in/unknown). Provider-Erkennung priorisiert ``active_provider_id``
        # vor ``route_provider_id``, damit die laufende Session-Auswahl Vorrang hat.
        #
        # ``provider_type`` steht daneben, weil ``provider_id`` allein den
        # laufenden Provider nicht immer benennen kann: Aufrufer, die Key und
        # base_url selbst aufloesen und direkt durchreichen (z. B.
        # simulation_config_generator), betreten den Active-Config-Zweig nicht,
        # so dass weder ``active_provider_id`` noch ``route_provider_id`` gesetzt
        # ist. Die Zeile las sich dann als ``provider_id=unknown base_url=None``
        # — bei codex_cli beides korrekt (kein HTTP-Transport, und
        # ``_detect_provider`` gibt fuer codex_cli bewusst "unknown" zurueck,
        # siehe dort), aber vom Log her ununterscheidbar von einem kaputten
        # Client. ``resolved_provider_type`` traegt den tatsaechlichen Typ und
        # stammt aus derselben Aufloesung wie ``_codex_cli_active`` — es ist
        # keine zweite Detection-Heuristik neben ``registry.py::detect_provider``.
        self._api_key_source = resolved_source or "unknown"
        # Gemini-Review (security-medium) zu PR #559: ``base_url`` kann in
        # Edge-Cases (Azure-OpenAI-Query-Param, Userinfo) Secret-Material
        # tragen. SecretResolver.sanitize_url strippt userinfo+query+fragment
        # vor dem Log, ohne den Hostname zu maskieren.
        from ..services.secret_resolver import SecretResolver as _UrlSanitizer
        logger.info(
            "LLMClient initialized provider_id=%s provider_type=%s model=%s "
            "base_url=%s api_key_source=%s",
            active_provider_id or route_provider_id or "unknown",
            resolved_provider_type or "unknown",
            self.model,
            _UrlSanitizer().sanitize_url(self.base_url) if self.base_url else None,
            self._api_key_source,
        )

        # Ollama context window size — prevents prompt truncation.
        # Sub-Slice 05.5: Cloud-aware Heuristik statt fix OLLAMA_NUM_CTX=8192.
        # Vorher kappte 8192 Cloud-Modelle wie gemini-3:cloud (1M) oder
        # qwen3-coder-next:cloud (256k) auf einen Bruchteil ihrer Kapazität.
        self._num_ctx = _resolve_num_ctx(
            model_name=self.model,
            provider_options_num_ctx=self.provider_options.get("num_ctx"),
        )
        # Ollama thinking toggle (mapped from reasoning_effort).
        # OLLAMA_THINKING=false in der env überstimmt reasoning_effort —
        # konsistent zu backend/scripts/run_*_simulation.py, das dieselbe
        # Heuristik nutzt. Honcho-Pflicht-Env für Agent-Workflows; ohne
        # diese Verdrahtung liefern thinking-Modelle (qwen3, gpt-oss) bei
        # chat_json schemalose leere `content`-Outputs → `JSON parsing
        # failed: line 1 column 1 (char 0)`.
        self._think = self.reasoning_effort != "none"
        _think_env = os.environ.get("OLLAMA_THINKING", "").lower()
        if _think_env in ("0", "false", "no", "off"):
            self._think = False
        elif _think_env in ("1", "true", "yes", "on"):
            self._think = True

        # Transient-failure retry knobs (Ollama Cloud sometimes 5xx-flaps).
        self._max_retries = int(os.environ.get('LLM_MAX_RETRIES', '3'))
        self._retry_initial_delay = float(os.environ.get('LLM_RETRY_INITIAL_DELAY', '1.0'))
        self._retry_max_delay = float(os.environ.get('LLM_RETRY_MAX_DELAY', '30.0'))


LLMClient.chat_with_tools = _chat_with_tools  # type: ignore[attr-defined]
