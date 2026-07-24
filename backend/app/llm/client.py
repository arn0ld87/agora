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

import json
import os
import re
import time as _time_mod
from typing import Literal, Optional, Dict, Any, List
from openai import OpenAI
from pydantic import BaseModel

from ..config import Config
from ..contracts.llm_routing_contract import ResolvedRoute, ReasoningEffort
from ..utils.logger import get_logger
from ..utils.retry import llm_call_with_retry

from .context import _resolve_num_ctx
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
    _strip_llm_json_envelope,
    _try_repair_truncated_json,
)
from .providers import base as _provider_base
from .providers import ollama as _provider_ollama
from .providers import openai as _provider_openai
from .tool_calls import _chat_with_tools

logger = get_logger("agora.llm_client")


def get_llm_provider_secrets_store() -> Any:
    """Load the secrets store lazily to avoid the services package import cycle."""
    from ..services.llm_provider_secrets_store import get_llm_provider_secrets_store as get_store

    return get_store()


class LLMClient:
    """LLM Client"""

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
    ):
        # When no explicit model is set, fall back to the user's active
        # provider/model selection (Settings → LLM-Auswahl). Falls back to
        # Config.* if no active config exists. Resolves api_key+base_url via
        # SecretResolver/Provider-Registry analogous to from_route().
        # ``api_key_source`` ist eine Audit-Annotation für das einmalige
        # Init-Log am Ende dieses Konstruktors. Track 1c (Pure-Gosling).
        resolved_source: Optional[str] = api_key_source if api_key else None
        active_provider_id: Optional[str] = None
        if use_active_config and model is None:
            active = _read_active_config_safely()
            if active:
                active_provider_id = active.get("provider_id")
                active_model = active.get("model")
                active_base = active.get("base_url")
                if active_model:
                    model = active_model
                if active_base and not base_url:
                    base_url = active_base
                if active_provider_id and not api_key:
                    try:
                        from ..services.llm_provider_registry import LlmProviderRegistry
                        from ..services.secret_resolver import SecretResolver
                        registry = LlmProviderRegistry()
                        descriptor = next(
                            (p for p in registry.get_providers() if p.id == active_provider_id),
                            None,
                        )
                        if descriptor is not None:
                            if not base_url:
                                base_url = descriptor.base_url
                            resolver = SecretResolver()
                            api_key = resolver.get_api_key(active_provider_id, descriptor.type)
                            if api_key:
                                resolved_source = resolver.last_source
                    except Exception as exc:  # noqa: BLE001 — fall back to Config defaults
                        logger.warning(
                            "Failed to resolve active LLM config (provider=%s): %s",
                            active_provider_id,
                            exc,
                        )

        if api_key:
            self.api_key = api_key
            # resolved_source bleibt erhalten (passed_in oder vom Resolver)
        elif allow_api_key_fallback:
            self.api_key = Config.LLM_API_KEY
            if self.api_key:
                resolved_source = "config_fallback"
        else:
            self.api_key = None
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.reasoning_effort = reasoning_effort or "none"
        self.provider_options = provider_options or {}
        self.run_id = run_id or os.environ.get("AGORA_RUN_ID")
        self.routing_version = routing_version
        self.route_stage = route_stage
        self.route_provider_id = route_provider_id

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        # Track 1c Audit-Log: einmalig pro LLMClient-Init. Niemals den Key-Wert
        # selbst loggen — nur die Quelle (session/store/env:NAME/config_fallback/
        # passed_in/unknown). Provider-Erkennung priorisiert ``active_provider_id``
        # vor ``route_provider_id``, damit die laufende Session-Auswahl Vorrang hat.
        self._api_key_source = resolved_source or "unknown"
        # Gemini-Review (security-medium) zu PR #559: ``base_url`` kann in
        # Edge-Cases (Azure-OpenAI-Query-Param, Userinfo) Secret-Material
        # tragen. SecretResolver.sanitize_url strippt userinfo+query+fragment
        # vor dem Log, ohne den Hostname zu maskieren.
        from ..services.secret_resolver import SecretResolver as _UrlSanitizer
        logger.info(
            "LLMClient initialized provider_id=%s model=%s base_url=%s api_key_source=%s",
            active_provider_id or route_provider_id or "unknown",
            self.model,
            _UrlSanitizer().sanitize_url(self.base_url) if self.base_url else None,
            self._api_key_source,
        )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
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

    @classmethod
    def from_route(
        cls,
        route: ResolvedRoute,
        secret_resolver: Optional["Any"] = None,
        timeout: float = 300.0,
        run_id: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> "LLMClient":
        """Factory: create LLMClient from a resolved stage route.

        Resolves actual base_url and api_key from the provider configuration,
        falling back to sanitized/config defaults if no resolver is provided.
        """
        base_url = route.base_url_sanitized
        connection_only = route.provider_options.get("connection_only") is True
        if connection_only:
            from ..services.secret_resolver import get_bound_store_api_key

            raw_secret_ref = route.provider_options.get("secret_ref")
            secret_ref = raw_secret_ref if isinstance(raw_secret_ref, str) else ""
            api_key = get_bound_store_api_key(
                secret_ref,
                secrets_store=get_llm_provider_secrets_store(),
            )
            api_key_source: Optional[str] = "store" if api_key else None
        else:
            api_key = api_key_override
            api_key_source = "passed_in" if api_key_override else None

        # If a secret resolver is provided, we try to get the real secrets.
        # This prevents leaking them into ResolvedRoute but allows LLMClient
        # to use them.
        if secret_resolver and not connection_only:
            # We need to know the provider type to resolve the key correctly.
            # ResolvedRoute only has provider_id.
            # In a full implementation, we'd look up the provider descriptor.
            # For now, we use the fallback logic in SecretResolver.
            from ..services.llm_provider_registry import LlmProviderRegistry
            registry = LlmProviderRegistry()
            descriptor = next((p for p in registry.get_providers() if p.id == route.provider_id), None)

            p_type = descriptor.type if descriptor else "unknown"
            if not api_key:
                api_key = secret_resolver.get_api_key(route.provider_id, p_type)
                api_key_source = getattr(secret_resolver, "last_source", None)

            # Use real base_url from provider_options if present, otherwise from descriptor
            real_base = route.provider_options.get("base_url") or (descriptor.base_url if descriptor else None)
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
            api_key_source=api_key_source,
            use_active_config=not connection_only,
            allow_api_key_fallback=not connection_only,
        )

    def _is_ollama(self) -> bool:
        """Determine whether the configured endpoint is an Ollama server.
        
        Returns:
            `true` if the configured base URL identifies an Ollama server, `false` otherwise.
        """
        return _provider_base.is_ollama(self.base_url)

    def _is_minimax(self) -> bool:
        """Determine whether the configured endpoint is a MiniMax service.
        
        Returns:
            bool: `true` if the endpoint uses MiniMax, `false` otherwise.
        """
        return self._detect_provider() == "minimax"

    def _minimax_thinking_extra_body(
        self, *, force_no_thinking: bool = False
    ) -> Dict[str, Any]:
        """
        Builds the MiniMax thinking configuration for a request.
        
        Parameters:
            force_no_thinking (bool): Whether to disable reasoning regardless of the
                configured thinking preference.
        
        Returns:
            Dict[str, Any]: A request body containing ``thinking.type`` set to
                ``"adaptive"`` when reasoning is enabled or ``"disabled"`` otherwise.
        """
        think_on = self._think and not force_no_thinking
        return {"thinking": {"type": "adaptive" if think_on else "disabled"}}

    @staticmethod
    def _uses_max_completion_tokens(model: str) -> bool:
        """Determine whether a model uses the ``max_completion_tokens`` parameter.
        
        Parameters:
            model (str): Model name to inspect.
        
        Returns:
            bool: ``True`` if the model uses ``max_completion_tokens``, ``False`` otherwise.
        """
        return _provider_openai.uses_max_completion_tokens(model)

    @staticmethod
    def _is_token_key_400(exc: Exception) -> bool:
        """Siehe ``app.llm.providers.openai.is_token_key_400``."""
        return _provider_openai.is_token_key_400(exc)

    @staticmethod
    def _swap_token_kwargs(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Siehe ``app.llm.providers.openai.swap_token_kwargs``."""
        return _provider_openai.swap_token_kwargs(kwargs)

    def _completion_token_kwargs(
        self, max_tokens: int, model: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Build the token-limit parameter for the selected model.
        
        Parameters:
            max_tokens (int): Maximum number of completion tokens.
            model (Optional[str]): Model used to select the token-limit parameter; defaults to the client's model.
        
        Returns:
            Dict[str, int]: A mapping containing either ``max_completion_tokens`` or ``max_tokens`` with the requested limit.
        """
        target_model = model if model is not None else (self.model or "")
        key = (
            "max_completion_tokens"
            if self._uses_max_completion_tokens(target_model)
            else "max_tokens"
        )
        return {key: max_tokens}

    def _detect_provider(self) -> Literal["ollama", "cloud", "minimax", "openai", "google", "unknown"]:
        """
        Identify the LLM provider associated with the configured endpoint and model.
        
        Returns:
            str: The provider name: ``"ollama"``, ``"cloud"``, ``"minimax"``,
                ``"openai"``, ``"google"``, or ``"unknown"``.
        """
        return _provider_base.detect_provider(self.base_url, self.model)

    def _publish_model_active(
        self,
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        """Publish a :class:`ModelActiveEvent` to the module-level bus.

        Fail-safe: any exception is caught and logged as a warning so that LLM
        calls are never blocked by bus errors.
        """
        try:
            from ..services.model_event_bus import ModelActiveEvent, model_event_bus

            extra: Dict[str, Any] = {}
            if max_tokens is not None:
                extra["max_tokens"] = max_tokens
            if temperature is not None:
                extra["temperature"] = temperature

            event = ModelActiveEvent(
                model=self.model or "unknown",
                context=context,
                provider=self._detect_provider(),
                ts=_time_mod.time(),
                extra=extra if extra else None,
            )
            model_event_bus.publish(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "model_event_bus.publish failed (LLM call proceeds): %s", exc
            )

    def _log_invocation_event(
        self,
        *,
        stage: str,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        remote_request_id: Optional[str] = None,
    ) -> None:
        """Persist LLM call telemetry for routed runs without blocking execution."""
        if not getattr(self, "run_id", None):
            return

        try:
            from ..services.llm_invocation_logger import LlmInvocationLogger

            logger_service = LlmInvocationLogger(self.run_id)
            logger_service.log_event(
                stage=getattr(self, "route_stage", None) or stage,
                provider_id=getattr(self, "route_provider_id", None) or self._detect_provider(),
                model=self.model or "unknown",
                base_url=self.base_url,
                routing_version=getattr(self, "routing_version", None) or 0,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                http_status=http_status,
                remote_request_id=remote_request_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm invocation logging failed (LLM call proceeds): %s", exc)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ] = "chat",
        force_no_thinking: bool = False,
        require_complete: bool = False,
    ) -> str:
        """
        Send a chat request and return the cleaned model response.
        
        Parameters:
            messages (List[Dict[str, str]]): Chat messages to send.
            temperature (float): Sampling temperature.
            max_tokens (int): Maximum number of completion tokens.
            response_format (Optional[Dict]): Optional requested response format.
            context (Literal): Logical context label for observability.
            force_no_thinking (bool): Whether to disable reasoning output when supported
                by the provider.
            require_complete (bool): When True, a response the provider marked as cut
                off at the token cap (``finish_reason == "length"``) raises
                :class:`LLMOutputTruncatedError` instead of returning partial text.
                Callers that parse the result structurally should set this.

        Returns:
            str: The model response text with thinking blocks removed.

        Raises:
            LLMOutputTruncatedError: When *require_complete* is set and the provider
                reported ``finish_reason == "length"``.
        """
        self._publish_model_active(context, max_tokens=max_tokens, temperature=temperature)
        # E2E-Stub-Pfad für chat() — symmetrisch zum Stub-Pfad in chat_json().
        # Aktiviert ausschließlich via AGORA_E2E_LLM_MODE=stub.
        # Liefert deterministischen ReACT-Loop-String (Tool-Call oder Final Answer).
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            from app.utils.llm_e2e_stub import e2e_stub_chat_response
            logger.info(
                "LLMClient.chat: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
                context,
            )
            return e2e_stub_chat_response(messages=messages)
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        kwargs.update(self._completion_token_kwargs(max_tokens))

        if response_format:
            kwargs["response_format"] = response_format

        # For Ollama: pass num_ctx via extra_body to prevent prompt truncation,
        # plus think flag to control reasoning output on capable models.
        # force_no_thinking=True überschreibt self._think hart auf False —
        # verhindert, dass Reasoning-Profile den Token-Cap mit Thoughts belegen.
        if self._is_ollama():
            extra_body: Dict[str, Any] = {}
            if self._num_ctx:
                extra_body["options"] = {"num_ctx": self._num_ctx}
            extra_body["think"] = False if force_no_thinking else self._think
            kwargs["extra_body"] = extra_body
        elif self._is_minimax():
            # MiniMax-eigenes ``thinking``-Feld (Spec) statt Ollama-``think``.
            kwargs["extra_body"] = self._minimax_thinking_extra_body(
                force_no_thinking=force_no_thinking
            )

        # Force streaming for Ollama: the OpenAI-compatible endpoint in Ollama
        # 0.21.0 stalls on non-streaming completions for cloud models (e.g.
        # qwen3-coder-next:cloud, deepseek-v4-flash:cloud) — the call never
        # returns. Streaming bypasses the bug; we reassemble chunks below.
        # Configurable via LLM_FORCE_STREAM=false to opt out.
        force_stream = (
            self._is_ollama()
            and os.environ.get("LLM_FORCE_STREAM", "true").lower() in ("1", "true", "yes")
        )

        import time as _time
        _t0 = _time.monotonic()

        def _create(call_kwargs: Dict[str, Any]):
            """One-shot call mit transient-retry. KEINE 400-Behandlung — die macht der äußere Wrapper."""
            return llm_call_with_retry(
                self.client.chat.completions.create,
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
                **call_kwargs,
            )

        def _call_with_token_key_fallback(call_kwargs: Dict[str, Any]):
            """Fallback-Retry: bei 400 wg. max_tokens/max_completion_tokens-Inkompatibilität
            einmalig den anderen Schlüssel verwenden. Heuristik in
            ``_uses_max_completion_tokens`` deckt die bekannten Familien ab; der
            Fallback schützt vor neuen Modellen/Proxies, die wir noch nicht kennen.
            """
            try:
                return _create(call_kwargs)
            except Exception as exc:  # noqa: BLE001 — wir filtern selbst
                if not self._is_token_key_400(exc):
                    raise
                swapped = self._swap_token_kwargs(call_kwargs)
                if swapped is None:
                    raise
                logger.warning(
                    "LLM 400 on token-limit key — retrying once with swapped key (model=%s, msg=%s)",
                    self.model,
                    str(exc)[:200],
                )
                return _create(swapped)

        _usage_for_counter: Optional[Any] = None
        try:
            if force_stream:
                kwargs["stream"] = True
                stream = _call_with_token_key_fallback(kwargs)
                chunks: List[str] = []
                finish_reason = None
                completion_tokens = None
                for event in stream:
                    if not event.choices:
                        continue
                    delta = event.choices[0].delta
                    piece = getattr(delta, "content", None)
                    if piece:
                        chunks.append(piece)
                    if event.choices[0].finish_reason:
                        finish_reason = event.choices[0].finish_reason
                    usage = getattr(event, "usage", None)
                    if usage and getattr(usage, "completion_tokens", None) is not None:
                        completion_tokens = usage.completion_tokens
                        _usage_for_counter = usage
                content = "".join(chunks)
            else:
                response = _call_with_token_key_fallback(kwargs)
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                usage = getattr(response, "usage", None)
                completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
                _usage_for_counter = usage
                content = choice.message.content or ""
        except Exception as exc:  # noqa: BLE001
            elapsed = _time.monotonic() - _t0
            self._log_invocation_event(
                stage=context,
                latency_ms=elapsed * 1000,
                success=False,
                error_type=exc.__class__.__name__,
                http_status=getattr(exc, "status_code", None),
            )
            raise
        elapsed = _time.monotonic() - _t0
        logger.info(
            "LLM chat returned model=%s finish=%s tokens_out=%s elapsed=%.1fs max_tokens=%s stream=%s",
            self.model, finish_reason, completion_tokens, elapsed, max_tokens, force_stream,
        )
        if require_complete and finish_reason == "length":
            # Nicht als Erfolg verbuchen: der Caller kann mit dem Fragment nichts
            # anfangen, und ein "success" hier verzerrt die Telemetrie.
            self._log_invocation_event(
                stage=context,
                latency_ms=elapsed * 1000,
                success=False,
                error_type="LLMOutputTruncatedError",
            )
            raise LLMOutputTruncatedError(
                f"LLM output truncated at token cap: model={self.model}, "
                f"completion_tokens={completion_tokens}, max_tokens={max_tokens}"
            )
        self._log_invocation_event(
            stage=context,
            latency_ms=elapsed * 1000,
            success=True,
        )
        # Token-Counter — nur bei vorhandenen Integer-Usage-Daten, kein Log-Spam bei fehlendem Usage.
        # isinstance-Check schützt gegen MagicMock-Attribute in Tests (Mock gibt immer
        # einen Sub-Mock zurück, kein None) und gegen nicht-numerische Provider-Antworten.
        if _usage_for_counter is not None:
            _prompt_tokens = getattr(_usage_for_counter, "prompt_tokens", None)
            _completion_tokens = getattr(_usage_for_counter, "completion_tokens", None)
            _provider_label = self._detect_provider()
            _model_label = self.model or "unknown"
            from ..observability import llm_token_counter as _llm_token_counter  # noqa: PLC0415
            _attrs: Dict[str, str] = {"provider": _provider_label, "model": _model_label}
            if isinstance(_prompt_tokens, int):
                _llm_token_counter().add(_prompt_tokens, {**_attrs, "direction": "in"})
            if isinstance(_completion_tokens, int):
                _llm_token_counter().add(_completion_tokens, {**_attrs, "direction": "out"})
        # Some models (like MiniMax M2.5, DeepSeek-R1) include <think>thinking content in response, need to remove
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def describe_image(
        self,
        image_b64: str,
        prompt: str,
        model: Optional[str] = None,
        mime: str = "image/png",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a single image + prompt to a vision-capable model and return a
        plain-text description.

        Uses the OpenAI-compatible multimodal message shape:
            {"role": "user", "content": [
                {"type": "text", "text": ...},
                {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}}
            ]}

        Works against Ollama Cloud vision models (e.g. gemini-3-flash-preview:cloud).
        """
        vision_model = model or os.environ.get('VISION_MODEL_NAME') or self.model
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        }]
        kwargs: Dict[str, Any] = {
            "model": vision_model,
            "messages": messages,
            "temperature": temperature,
        }
        kwargs.update(self._completion_token_kwargs(max_tokens, model=vision_model))
        if self._is_ollama():
            extra_body: Dict[str, Any] = {"options": {"num_ctx": max(self._num_ctx, 8192)}}
            extra_body["think"] = False  # never want reasoning noise in vision output
            kwargs["extra_body"] = extra_body

        def _create_vision(call_kwargs: Dict[str, Any]):
            return llm_call_with_retry(
                self.client.chat.completions.create,
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
                **call_kwargs,
            )

        try:
            response = _create_vision(kwargs)
        except Exception as exc:  # noqa: BLE001
            if not self._is_token_key_400(exc):
                raise
            swapped = self._swap_token_kwargs(kwargs)
            if swapped is None:
                raise
            logger.warning(
                "Vision LLM 400 on token-limit key — retrying once with swapped key (model=%s)",
                vision_model,
            )
            response = _create_vision(swapped)
        content = response.choices[0].message.content or ""
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def _maybe_validate(
        self,
        parsed: Dict[str, Any],
        schema: Optional[JsonSchemaLike],
    ) -> Dict[str, Any]:
        """Validate *parsed* against *schema* if it is a Pydantic model.

        When *schema* is a plain JSON-Schema dict validation is the caller's
        responsibility — we return *parsed* unchanged.  When *schema* is a
        Pydantic model class we call ``model_validate`` and re-serialise via
        ``model_dump(mode='json')`` so the caller receives JSON-compatible
        Python types.  ``ValidationError`` propagates unchanged.
        """
        if schema is None:
            return parsed
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            # ValidationError propagates — do NOT swallow.
            return schema.model_validate(parsed).model_dump(mode="json")
        # Plain dict schema: no server-side re-validation.
        return parsed

    def _ollama_chat_with_schema(
        self,
        messages: List[Dict[str, Any]],
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        force_no_thinking: bool = False,
    ) -> str:
        """Direkter Aufruf gegen Ollamas /api/chat mit format=<schema>.

        Delegiert an ``app.llm.providers.ollama.chat_with_schema`` (native
        httpx-Call, Schema-Enforcement laut Ollama-Doku — siehe dort für
        Details/Fehlerverhalten).
        """
        think_flag = False if force_no_thinking else self._think
        return _provider_ollama.chat_with_schema(
            base_url=self.base_url,
            model=self.model,
            api_key=self.api_key,
            think=think_flag,
            num_ctx=self._num_ctx,
            messages=messages,
            schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        schema: Optional[JsonSchemaLike] = None,
        schema_name: str = "structured_response",
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ] = "chat_json",
        force_no_thinking: bool = False,
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON.

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            schema: Optional Pydantic model class or JSON-Schema dict.
                When provided, attempts strict ``response_format={"type":
                "json_schema", ...}``.  On providers that do not support this
                format a single fallback to ``json_object`` is attempted with a
                warning log.  When *schema* is a Pydantic model the returned
                dict is also validated against it so that callers can rely on
                field types matching the model.
            schema_name: Name embedded in the strict json_schema request
                (used by some providers for caching / routing).
            context: Logical call context label for observability (forwarded
                to :meth:`chat` which publishes it to the model event bus).
            force_no_thinking: Wird an chat() weitergereicht — bei Ollama wird
                ``think=False`` hart gesetzt, unabhaengig vom Profil.

        Returns:
            Parsed JSON object (dict).

        Raises:
            ValueError: JSON cannot be parsed after optional repair.
            pydantic.ValidationError: Parsed JSON does not match *schema*
                when *schema* is a Pydantic model.
        """
        # E2E-Stub-Pfad — nur aktiv wenn AGORA_E2E_LLM_MODE=stub gesetzt.
        # Muss VOR Cache-Lookup, Token-Counter, Retry und allen LLM-Calls liegen.
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            from app.utils.llm_e2e_stub import e2e_stub_response
            logger.info(
                "LLMClient.chat_json: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
                context,
            )
            # schema kann Pydantic-Klasse oder dict sein — Stub normalisiert intern
            schema_for_stub: Optional[Dict[str, Any]] = None
            if schema is not None:
                if isinstance(schema, type) and issubclass(schema, BaseModel):
                    schema_for_stub = schema.model_json_schema()
                elif isinstance(schema, dict):
                    schema_for_stub = schema
            return e2e_stub_response(
                schema=schema_for_stub,
                messages=list(messages),
            )

        # --- Env-Flag-Auswertung (Issue #593) -----------------------------------
        # LLM_DISABLE_JSON_OBJECT_MODE  → unterdrückt {type: "json_object"}
        # LLM_DISABLE_JSON_SCHEMA_MODE  → unterdrückt strict json_schema;
        #                                  fällt auf json_object + Pydantic zurück
        # LLM_DISABLE_JSON_MODE         → Legacy-Alias für OBJECT_MODE (Deprecation)
        disable_object_mode = _is_json_object_mode_disabled()
        disable_schema_mode = _is_json_schema_mode_disabled()

        # Legacy-Alias: Deprecation-Warning ausgeben, damit Betreiber migrieren können.
        if _env_flag('LLM_DISABLE_JSON_MODE') and not _env_flag('LLM_DISABLE_JSON_OBJECT_MODE'):
            import warnings as _warnings
            _warnings.warn(
                "LLM_DISABLE_JSON_MODE ist veraltet und wird in einer künftigen Version "
                "entfernt. Bitte LLM_DISABLE_JSON_OBJECT_MODE verwenden.",
                DeprecationWarning,
                stacklevel=2,
            )

        # schema=None + OBJECT_MODE disabled → kein response_format
        disable_json_mode = disable_object_mode and schema is None
        # schema=<Model> + SCHEMA_MODE disabled → json_object-Fallback statt strict
        schema_mode_fallback = schema is not None and disable_schema_mode

        if schema_mode_fallback:
            fallback_target = "Freitext" if disable_object_mode else "json_object"
            logger.info(
                "LLMClient.chat_json: LLM_DISABLE_JSON_SCHEMA_MODE aktiv — schema=%s "
                "fällt auf %s + Pydantic-Validierung zurück",
                schema.__name__ if isinstance(schema, type) else "dict",
                fallback_target,
            )

        if schema is not None:
            schema_label = schema.__name__ if isinstance(schema, type) else "dict"
            logger.info(
                "LLMClient.chat_json: schema=%s name=%s",
                schema_label,
                schema_name,
            )

        # Build response_format ---------------------------------------------------
        if disable_json_mode:
            response_format: Optional[Dict[str, Any]] = None
        elif schema_mode_fallback:
            # LLM_DISABLE_JSON_SCHEMA_MODE=true: Schema übergeben, aber strict-Mode
            # deaktiviert → json_object + post-hoc Pydantic-Validierung.
            # Falls auch OBJECT_MODE deaktiviert ist, fällt es auf Freitext (None) zurück.
            response_format = None if disable_object_mode else {"type": "json_object"}
        elif schema is not None:
            # OpenAI / Google strict-mode: $refs inline-resolven, $defs +
            # Meta-Keys droppen, additionalProperties:false + required-Liste
            # auf alle Object-Schemas erzwingen. Ollama nutzt den nativen
            # /api/chat::format-Pfad weiter unten und ist nicht betroffen.
            json_schema: Dict[str, Any] = _enforce_openai_strict_schema(schema)
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            }
        else:
            response_format = {"type": "json_object"}

        # Call --------------------------------------------------------------------
        if not disable_json_mode and not schema_mode_fallback and schema is not None:
            # NATIVE Ollama-Pfad: /api/chat mit format=<schema> ist die einzige
            # autoritativ dokumentierte Methode, ein Schema bei Ollama zu erzwingen.
            # Bei Netz-/4xx-Fehler fall-through zum OpenAI-SDK-Pfad mit
            # json_object-Fallback (Resilienz, kein Hard-Fail).
            if self._is_ollama() and isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    response = self._ollama_chat_with_schema(
                        messages=messages,
                        schema=schema,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        force_no_thinking=force_no_thinking,
                    )
                    cleaned_response = _strip_llm_json_envelope(response)
                    parsed: Dict[str, Any] = json.loads(cleaned_response)
                    return self._maybe_validate(parsed, schema)
                except LLMOutputTruncatedError:
                    # Kein Transportfehler: derselbe Request ueber den
                    # OpenAI-Wrapper wird am selben Limit wieder gekappt und
                    # kostet nur einen zweiten vollen Call. Durchreichen.
                    raise
                except Exception as exc:  # noqa: BLE001 — bewusst breit, Fallback ist sicher
                    logger.warning(
                        "LLMClient.chat_json: native Ollama /api/chat-Pfad fehlgeschlagen "
                        "(%s: %s), fallback auf OpenAI-Wrapper",
                        type(exc).__name__, exc,
                    )
                    # Fall through zum bestehenden Strict-OpenAI-Pfad
            # Strict-schema path: single fallback on unsupported-provider errors.
            try:
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    context=context,
                    force_no_thinking=force_no_thinking,
                    require_complete=True,
                )
            except Exception as exc:
                exc_lower = str(exc).lower()
                if any(hint in exc_lower for hint in _STRICT_UNSUPPORTED_HINTS):
                    logger.warning(
                        "LLMClient.chat_json: strict json_schema not supported by "
                        "provider, falling back to json_object (caller should not "
                        "rely on schema enforcement here)"
                    )
                    response = self.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                        context=context,
                        force_no_thinking=force_no_thinking,
                        require_complete=True,
                    )
                else:
                    raise
        else:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                context=context,
                force_no_thinking=force_no_thinking,
                require_complete=True,
            )
        # Codefences + Prosa-Envelope entfernen (Issue #556).
        cleaned_response = _strip_llm_json_envelope(response)

        try:
            parsed: Dict[str, Any] = json.loads(cleaned_response)
        except json.JSONDecodeError:
            repaired = _try_repair_truncated_json(cleaned_response)
            if repaired is not None:
                logger.warning(
                    "LLM JSON looked truncated; recovered with best-effort repair "
                    "(%d → %d chars). Consider raising the max_tokens budget for "
                    "this caller.",
                    len(cleaned_response), len(repaired),
                )
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    pass
                else:
                    return self._maybe_validate(parsed, schema)
            preview = cleaned_response[:400]
            tail = cleaned_response[-200:] if len(cleaned_response) > 600 else ""
            raise ValueError(
                "Invalid JSON format from LLM "
                f"(len={len(cleaned_response)}; likely truncated — "
                "try raising max_tokens). "
                f"Head: {preview}{'…' if tail else ''}"
                + (f" Tail: …{tail}" if tail else "")
            )
        return self._maybe_validate(parsed, schema)


# Methode in LLMClient einbinden (siehe app/llm/tool_calls.py — Kommentar dort)
LLMClient.chat_with_tools = _chat_with_tools  # type: ignore[attr-defined]
