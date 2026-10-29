"""Chat completion execution mixin for LLMClient."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

from ..utils.logger import get_logger
from ..utils.retry import llm_call_with_retry
from ._client_shim import get_client_attr as _get_client_attr
from .errors import LLMOutputTruncatedError
from .request_plan import (
    REASONING_EFFORT_QUIRK,
    TEMPERATURE_QUIRK,
    TOKEN_KEY_QUIRK,
    build_request,
    execute,
    thinking_extra_body,
)

logger = get_logger("agora.llm_client")


class LLMClientChatMixin:
    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

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
        enforce_token_floor: bool = True,
    ) -> str:
        """
        Send a chat request and return the cleaned model response.

        Parameters:
            messages (List[Dict[str, str]]): Chat messages to send.
            temperature (float): Sampling temperature.
            max_tokens (int): Requested completion-token limit. Wird über
                :meth:`_effective_max_tokens` auf den konfigurierten Boden
                angehoben und am Ausgabelimit des Modells gedeckelt.
            response_format (Optional[Dict]): Optional requested response format.
            context (Literal): Logical context label for observability.
            force_no_thinking (bool): Whether to disable reasoning output when supported
                by the provider.
            require_complete (bool): When True, a response the provider marked as cut
                off at the token cap (``finish_reason == "length"``) raises
                :class:`LLMOutputTruncatedError` instead of returning partial text.
                Callers that parse the result structurally should set this.
            enforce_token_floor (bool): Auf ``False`` setzen, wenn das enge
                ``max_tokens`` Absicht ist — Klassifikation, Label-Ausgabe,
                Ein-Wort-Antworten. Der Deckel am Ausgabelimit greift auch dann.

        Returns:
            str: The model response text with thinking blocks removed.

        Raises:
            LLMOutputTruncatedError: When *require_complete* is set and the provider
                reported ``finish_reason == "length"``.
        """
        max_tokens = self._effective_max_tokens(
            max_tokens, enforce_floor=enforce_token_floor
        )
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
            # Budget-Gate fuer den Stub: ein Stub-Aufruf = ein Providerattempt
            # (Issue #764, Codex P1). Symmetrisch zum OpenAI-Pfad, der seinen
            # Check in ``_provider_attempt`` erhaelt.
            self._budget_check()
            self._log_invocation_event(stage=context, latency_ms=0.0, success=True)
            self._budget_record()
            return e2e_stub_chat_response(messages=messages)
        # Force streaming for Ollama: the OpenAI-compatible endpoint in Ollama
        # 0.21.0 stalls on non-streaming completions for cloud models (e.g.
        # qwen3-coder-next:cloud, deepseek-v4-flash:cloud) — the call never
        # returns. Streaming bypasses the bug; we reassemble chunks below.
        # Configurable via LLM_FORCE_STREAM=false to opt out.
        force_stream = (
            self._is_ollama()
            and os.environ.get("LLM_FORCE_STREAM", "true").lower() in ("1", "true", "yes")
        )
        # force_no_thinking=True überschreibt self._think hart auf False —
        # verhindert, dass Reasoning-Profile den Token-Cap mit Thoughts belegen.
        plan = build_request(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=thinking_extra_body(
                ollama=self._is_ollama(),
                minimax=self._is_minimax(),
                num_ctx=self._ollama_num_ctx_for(max_tokens),
                think=False if force_no_thinking else self._think,
            ),
            stream=force_stream,
            extra=self._reasoning_effort_extra(force_no_thinking=force_no_thinking),
        )

        def _create(call_kwargs: Dict[str, Any]) -> Tuple[Any, float]:
            """Ein physischer Providerattempt mit transient-retry.

            Budget-Check, Failure-Telemetrie und -Record laufen INNERHALB des
            Wrappers — jeder Retried-Attempt erzeugt damit genau eine
            Check/Event/Record-Triplet.

            KEINE 400-Behandlung: die machen die Quirks in ``execute``.
            """
            return _get_client_attr("llm_call_with_retry", llm_call_with_retry)(
                lambda: self._provider_attempt(call_kwargs, context),
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
            )

        def _call() -> Tuple[Any, float]:
            """Der abgesicherte Call: Token-Key-Quirk innen, Temperature aussen.

            Beide Quirks greifen unabhaengig voneinander — der aeussere setzt
            auf dem Originalrequest auf, und der innere steht dem korrigierten
            Lauf wieder zur Verfuegung. Jeder Neuversuch zaehlt als eigener
            Providerattempt mit eigener Check/Event/Record-Triplet.
            """
            return execute(
                plan,
                _create,
                quirks=(TOKEN_KEY_QUIRK, TEMPERATURE_QUIRK, REASONING_EFFORT_QUIRK),
            )

        # Provider-Pfad: jeder physische Request (erster Call, jeder Retry,
        # Token-Key-Fallback, Temperature-Fallback) erhaelt GENAU EINE
        # _budget_check / _log_invocation_event / _budget_record-Triplet.
        # ``_provider_attempt`` kuemmert sich um Check + Failure-Telemetrie;
        # ``_record_provider_success`` finalisiert die Success-Telemetrie
        # (nach Usage-Extraktion, sodass auch der Streaming-Pfad mit einem
        # einzigen Event auskommt).
        _usage_for_counter: Optional[Any] = None
        _response: Any = None
        _latency_ms: float = 0.0
        finish_reason: Optional[str] = None
        completion_tokens: Optional[int] = None
        try:
            if force_stream:
                _response, _latency_ms = _call()
                chunks: List[str] = []
                try:
                    for event in _response:  # type: ignore[union-attr]
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
                except Exception as exc:  # noqa: BLE001
                    # Streaming-Iteration-Fehler (Mid-Stream-Network-Reset o.ae.)
                    # zaehlt als fehlgeschlagener Providerattempt — Telemetrie
                    # + Record, dann durchreichen. ``_provider_attempt`` hat
                    # fuer den HTTP-Connect bereits geloggt; hier geht es um
                    # den Datenempfang nach erfolgreichem 200.
                    self._log_invocation_event(
                        stage=context,
                        latency_ms=_latency_ms,
                        success=False,
                        error_type=type(exc).__name__,
                        http_status=getattr(exc, "status_code", None),
                    )
                    self._budget_record()
                    raise
                content = "".join(chunks)
            else:
                _response, _latency_ms = _call()
                # Issue #764 (Review): die lokale Verarbeitung einer
                # HTTP-erfolgreichen Antwort kann fehlschlagen (leeres
                # ``choices``, ``message`` ohne ``content``, fehlende
                # ``usage``-Attribute). Damit der fehlgeschlagene
                # lokale Schritt trotzdem als ein Providerattempt
                # sichtbar wird, muss GENAU EIN Failure-Event + GENAU
                # EIN ``_budget_record`` entstehen — sonst zaehlt der
                # weiche ``max_llm_calls``-Limit diesen Call nicht und
                # die Telemetrie verliert ihn. ``BudgetExceededError`` ist
                # hier nicht erreichbar (Check liegt VOR ``create()`` in
                # ``_provider_attempt``).
                #
                # Issue #764 (Codex P2): ``usage`` wird VOR dem
                # ``choices``-Zugriff gelesen. Eine malformed Antwort kann
                # trotzdem abgerechnete Prompt-/Completion-Tokens tragen
                # (``choices=[]`` neben gefuellten Totals).
                # ``run_usage_ledger._Bucket.add`` leitet Verbrauch und Kosten
                # ausschliesslich aus den Event-Feldern ab — fehlen sie, ist
                # der Call zwar gezaehlt, sein Verbrauch aber unbekannt, und
                # nachfolgende harte Token-/Kostenchecks lassen zu viele
                # Folgecalls durch.
                usage = None
                try:
                    usage = getattr(_response, "usage", None)
                    completion_tokens = (
                        getattr(usage, "completion_tokens", None) if usage else None
                    )
                    _usage_for_counter = usage
                    choice = _response.choices[0]
                    finish_reason = getattr(choice, "finish_reason", None)
                    content = choice.message.content or ""
                except Exception as exc:  # noqa: BLE001 — Failure-Telemetrie, weiterreichen
                    # isinstance-Guard wie im Erfolgspfad: MagicMock-Attribute
                    # in Tests und nicht-numerische Providerwerte duerfen nicht
                    # als Tokenzahl ins Ledger.
                    _p = getattr(usage, "prompt_tokens", None)
                    _c = getattr(usage, "completion_tokens", None)
                    self._log_invocation_event(
                        stage=context,
                        latency_ms=_latency_ms,
                        success=False,
                        error_type=type(exc).__name__,
                        prompt_tokens=_p if isinstance(_p, int) else None,
                        completion_tokens=_c if isinstance(_c, int) else None,
                    )
                    self._budget_record()
                    raise
        except Exception:
            # ``_provider_attempt`` hat fuer create()-Fehler bereits geloggt +
            # recordet. Streaming-Iterationsfehler wurden im inneren try-Block
            # behandelt. Hier nur sauber durchreichen.
            raise
        logger.info(
            "LLM chat returned model=%s finish=%s tokens_out=%s max_tokens=%s stream=%s",
            self.model, finish_reason, completion_tokens, max_tokens, force_stream,
        )
        if require_complete and finish_reason == "length":
            # Nicht als Erfolg verbuchen: der Caller kann mit dem Fragment nichts
            # anfangen, und ein "success" hier verzerrt die Telemetrie.
            self._log_invocation_event(
                stage=context,
                latency_ms=_latency_ms,
                success=False,
                error_type="LLMOutputTruncatedError",
            )
            # Issue #764 (Codex P2): record_after_call auch im Truncation-Pfad
            # — sonst zaehlt der fehlgeschlagene Call nicht in den weichen
            # Budget-Limits (calls) und der Enforcer verliert einen Eintrag.
            self._budget_record()
            raise LLMOutputTruncatedError(
                f"LLM output truncated at token cap: model={self.model}, "
                f"completion_tokens={completion_tokens}, max_tokens={max_tokens}"
            )
        # Erfolgreicher Providerattempt: Success-Event + Record (genau einmal).
        self._record_provider_success(
            _response, _latency_ms, context, usage=_usage_for_counter
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
