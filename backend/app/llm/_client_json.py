"""Structured JSON / schema chat mixin for LLMClient."""

import os
import time as _time_mod
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel

from .errors import LLMOutputTruncatedError
from .json_mode import (
    JsonSchemaLike,
    _STRICT_UNSUPPORTED_HINTS,
    _enforce_openai_strict_schema,
    _env_flag,
    _is_json_object_mode_disabled,
    _is_json_schema_mode_disabled,
    _parse_llm_json,
    _strip_llm_json_envelope,
)
from .providers import ollama as _provider_ollama
from ..utils.logger import get_logger

logger = get_logger("agora.llm_client")


class LLMClientJsonMixin:
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

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
    ) -> Tuple[str, Dict[str, Optional[int]]]:
        """Direkter Aufruf gegen Ollamas /api/chat mit format=<schema>.

        Delegiert an ``app.llm.providers.ollama.chat_with_schema`` (native
        httpx-Call, Schema-Enforcement laut Ollama-Doku — siehe dort für
        Details/Fehlerverhalten). Liefert ``(content, usage)`` mit
        ``usage`` = ``{prompt_eval_count, eval_count, total_duration_ns}``
        oder None-Werten, wenn Ollama keine Usage mitschickt.
        """
        think_flag = False if force_no_thinking else self._think
        return _provider_ollama.chat_with_schema(
            base_url=self.base_url,
            model=self.model,
            api_key=self.api_key,
            think=think_flag,
            num_ctx=self._ollama_num_ctx_for(max_tokens) or self._num_ctx,
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
        enforce_token_floor: bool = True,
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON.

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Angefordertes Token-Limit. Wird wie in :meth:`chat`
                auf den Boden angehoben und am Ausgabelimit gedeckelt — hier
                einmal zentral, damit auch der native Ollama-Schema-Pfad
                denselben Wert sieht wie der OpenAI-kompatible.
            schema: Optional Pydantic model class or JSON-Schema dict.
                When provided, attempts strict ``response_format={"type":
                "json_schema", ...}``.  On providers that do not support this
                format a single fallback to ``json_object`` is attempted with a
                warning log.  When *schema* is a Pydantic model the returned
                dict is also validated against it so that callers can rely on
                field types matching the model. A 400 caused by the GPT-5-/o-
                reasoning-family ``temperature`` quirk (#1096) is NOT treated
                as unsupported-schema: it retries once without ``temperature``
                in the same response_format mode instead of degrading to
                ``json_object``.
            schema_name: Name embedded in the strict json_schema request
                (used by some providers for caching / routing).
            context: Logical call context label for observability (forwarded
                to :meth:`chat` which publishes it to the model event bus).
            force_no_thinking: Wird an chat() weitergereicht — bei Ollama wird
                ``think=False`` hart gesetzt, unabhaengig vom Profil.
            enforce_token_floor: Auf ``False`` setzen, wenn das enge
                ``max_tokens`` Absicht ist (Klassifikation, Label-Ausgabe).

        Returns:
            Parsed JSON object (dict).

        Raises:
            ValueError: JSON cannot be parsed after optional repair.
            pydantic.ValidationError: Parsed JSON does not match *schema*
                when *schema* is a Pydantic model.
        """
        max_tokens = self._effective_max_tokens(
            max_tokens, enforce_floor=enforce_token_floor
        )
        # Budget-Gate (Issue #764, Codex P1): jeder physische Providerrequest
        # bekommt GENAU EINEN ``_budget_check`` unmittelbar vor dem Call.
        # Pfade, die an ``chat()`` delegieren (OpenAI-kompatibel), erhalten
        # dort ihren Check — ``chat_json`` ruft hier KEINEN Check mehr auf.
        # E2E-Stub und nativer Ollama-Schema-Pfad hingegen umgehen ``chat()``
        # und brauchen daher einen eigenen Check.
        # E2E-Stub-Pfad — nur aktiv wenn AGORA_E2E_LLM_MODE=stub gesetzt.
        # Muss VOR Cache-Lookup, Token-Counter, Retry und allen LLM-Calls liegen.
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            self._budget_check()
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
            self._log_invocation_event(stage=context, latency_ms=0.0, success=True)
            self._budget_record()
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
                # Issue #764 (Codex P1, Codex P2): Der native Ollama-Pfad
                # umgeht ``chat()`` und damit dessen Budget-Gates. Hier daher
                # der eigene ``_budget_check`` unmittelbar vor dem Transport-
                # Call, und je genau EIN Invocation-Event + ``_budget_record``
                # je nach Outcome:
                #   * Erfolg → success=True Event + record + lokales Parsen
                #   * LLMOutputTruncatedError → success=False Event + record,
                #     kein Fallback (gleiches Cap, sonst 2. verschwendeter Call)
                #   * Sonstiger Provider-/Transportfehler → success=False
                #     Event + record + Fall-through zum OpenAI-Wrapper (auch
                #     der hat seinen eigenen Check in chat()).
                # Rein lokale Fehler (JSON-Parsing, Pydantic-Validation) NACH
                # erfolgreicher Providerantwort erzeugen KEIN zusaetzliches
                # Providerevent — der Attempt war erfolgreich, nur die
                # Weiterverarbeitung ist gescheitert.
                self._budget_check()
                _ollama_call_started = _time_mod.monotonic()
                try:
                    ollama_response, ollama_usage = self._ollama_chat_with_schema(
                        messages=messages,
                        schema=schema,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        force_no_thinking=force_no_thinking,
                    )
                except LLMOutputTruncatedError:
                    ollama_latency_ms = (
                        _time_mod.monotonic() - _ollama_call_started
                    ) * 1000.0
                    self._log_invocation_event(
                        stage=context,
                        latency_ms=ollama_latency_ms,
                        success=False,
                        error_type="LLMOutputTruncatedError",
                    )
                    self._budget_record()
                    # Kein Fallback: dasselbe Cap, zweiter Call waere
                    # verschwendet. Hart durchreichen.
                    raise
                except Exception as exc:  # noqa: BLE001 — bewusst breit, Fallback ist sicher
                    ollama_latency_ms = (
                        _time_mod.monotonic() - _ollama_call_started
                    ) * 1000.0
                    logger.warning(
                        "LLMClient.chat_json: native Ollama /api/chat-Pfad fehlgeschlagen "
                        "(%s: %s), fallback auf OpenAI-Wrapper",
                        type(exc).__name__, exc,
                    )
                    self._log_invocation_event(
                        stage=context,
                        latency_ms=ollama_latency_ms,
                        success=False,
                        error_type=type(exc).__name__,
                        http_status=getattr(exc, "status_code", None),
                    )
                    # Fehlversuch zaehlt als Providerattempt — der nachfolgende
                    # OpenAI-Wrapper fuehrt seinen eigenen ``_budget_check``
                    # in ``chat()`` durch, daher KEIN doppelter Check hier.
                    self._budget_record()
                    # Fall through zum bestehenden Strict-OpenAI-Pfad
                else:
                    ollama_latency_ms = (
                        _time_mod.monotonic() - _ollama_call_started
                    ) * 1000.0
                    self._log_invocation_event(
                        stage=context,
                        latency_ms=ollama_latency_ms,
                        success=True,
                        prompt_tokens=ollama_usage.get("prompt_eval_count"),
                        completion_tokens=ollama_usage.get("eval_count"),
                    )
                    self._budget_record()
                    cleaned_response = _strip_llm_json_envelope(ollama_response)
                    # Gleicher Parse-/Repair-/Diagnose-Pfad wie unten — sonst
                    # kaeme aus dem nativen Pfad ein nackter JSONDecodeError.
                    return self._maybe_validate(
                        _parse_llm_json(cleaned_response), schema
                    )
            # Strict-schema path: single fallback on unsupported-provider errors.
            # ``enforce_token_floor`` wird durchgereicht, nicht unterdrückt:
            # ``max_tokens`` ist oben bereits aufgelöst, und die Auflösung ist
            # idempotent — ein zweiter Durchlauf mit derselben Flagge ändert
            # den Wert nicht, ein Durchlauf mit der falschen schon.
            try:
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    context=context,
                    force_no_thinking=force_no_thinking,
                    require_complete=True,
                    enforce_token_floor=enforce_token_floor,
                )
            except Exception as exc:
                # #1096: ein 400 auf param=temperature ist KEIN Hinweis auf
                # fehlenden strict-json_schema-Support — die Wortlaut-Hints
                # unten ("unsupported", "not supported") matchen ihn aber
                # faelschlich, weil OpenAIs unsupported_value-Fehlertext
                # dieselben Woerter enthaelt. Ohne diese Weiche waere die
                # Warnung "strict json_schema not supported by provider"
                # irrefuehrend, und der Retry wuerde grundlos auf
                # json_object statt auf denselben Schema-Modus wechseln.
                # ``chat()`` faengt den Quirk bereits proaktiv (Shaping) und
                # per eigenem Retry ab — dieser Zweig ist das Netz fuer den
                # Fall, dass die Ausnahme trotzdem bis hierher durchreicht.
                if self._is_temperature_400(exc):
                    response = self.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                        context=context,
                        force_no_thinking=force_no_thinking,
                        require_complete=True,
                        enforce_token_floor=enforce_token_floor,
                    )
                else:
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
                            enforce_token_floor=enforce_token_floor,
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
                enforce_token_floor=enforce_token_floor,
            )
        # Codefences + Prosa-Envelope entfernen (Issue #556).
        cleaned_response = _strip_llm_json_envelope(response)

        return self._maybe_validate(_parse_llm_json(cleaned_response), schema)
