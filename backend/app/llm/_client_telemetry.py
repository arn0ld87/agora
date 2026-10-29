"""Telemetry, event bus, and budget gate mixin for LLMClient."""

import time as _time_mod
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Tuple
from ..utils.logger import get_logger
from .request_plan import extract_int_token_usage

logger = get_logger("agora.llm_client")


class LLMClientTelemetryMixin:
    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _publish_model_active(
        self,
        context: Literal["chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"],
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

            # ``openrouter`` ist ein Detection-Wert, keine Verbindungsart im
            # Vertrag ``ProviderType``; das Ereignis fuehrt die Route wie
            # bisher als ``unknown``.
            detected = self._detect_provider()
            event = ModelActiveEvent(
                model=self.model or "unknown",
                context=context,
                provider="unknown" if detected == "openrouter" else detected,
                ts=_time_mod.time(),
                extra=extra if extra else None,
            )
            model_event_bus.publish(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning("model_event_bus.publish failed (LLM call proceeds): %s", exc)

    def _budget_enforcer(self):
        """RunBudgetEnforcer für diesen Run (None ohne Budget oder run_id).

        Lazy + gecacht pro Client-Instanz. Fehler beim Aufbau werden geloggt
        und blockieren den LLM-Call nicht (Budget ist Zusatz, kein Hotpath-
        Risiko).
        """
        cached = getattr(self, "_budget_enforcer_cache", "unset")
        if cached != "unset":
            return cached
        enforcer = None
        run_id = getattr(self, "run_id", None)
        if run_id:
            try:
                from ..services.run_budget import RunBudgetEnforcer

                enforcer = RunBudgetEnforcer.for_run(run_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("budget enforcer unavailable (LLM call proceeds): %s", exc)
        self._budget_enforcer_cache = enforcer
        return enforcer

    def _budget_check(self) -> None:
        """Hard-Limit-Prüfung VOR dem Call.

        :class:`BudgetExceededError` wird absichtlich durchgereicht — harte
        Limits müssen weiterhin greifen. Alle anderen Fehler (Datei-,
        Ledger-, Parsing-Probleme etc.) werden geloggt und führen nicht zum
        Blockieren des eigentlichen LLM-Calls (Budget ist Zusatz, nicht
        Hotpath-Risiko).
        """
        from ..services.run_budget import BudgetExceededError

        enforcer = self._budget_enforcer()
        if enforcer is None:
            return
        try:
            enforcer.check_before_call()
        except BudgetExceededError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("budget check_before_call failed (LLM call proceeds): %s", exc)

    def remaining_hard_call_budget(self) -> Optional[int]:
        """Verbleibende Calls unter einem harten ``max_llm_calls``-Budget.

        Duenne Weiterreichung an
        :meth:`RunBudgetEnforcer.remaining_hard_calls` — die Rechnung liegt
        beim Enforcer, damit Aufrufer ohne LLMClient (etwa die
        Persona-Generierung, die ihre Clients pro Persona baut) dieselbe
        Quelle nutzen koennen, statt eine Wegwerf-Instanz nur zum Auslesen
        zu konstruieren.

        ``None`` heisst: kein hartes Aufrufbudget aktiv (kein Run, kein
        Budget, weiche Durchsetzung oder Limit ohne Aufrufgrenze).
        """
        enforcer = self._budget_enforcer()
        if enforcer is None:
            return None
        return enforcer.remaining_hard_calls()

    def _budget_record(self) -> None:
        """Weiche-Limit-Prüfung NACH dem Call.

        Darf einen erfolgreich abgeschlossenen LLM-Call NICHT nachträglich
        in einen Fehler verwandeln — interne Budget-Fehler werden geloggt
        und geschluckt.
        """
        enforcer = self._budget_enforcer()
        if enforcer is None:
            return
        try:
            enforcer.record_after_call()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "budget record_after_call failed (recorded call stays successful): %s",
                exc,
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
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> None:
        """Persist LLM call telemetry for routed runs without blocking execution.

        ``model`` ueberschreibt ``self.model`` fuer diesen einen Event —
        noetig fuer Pfade, die pro Aufruf ein abweichendes Modell waehlen
        (``describe_image`` mit ``model=``-Override oder ``VISION_MODEL_NAME``).
        Default bleibt ``self.model``, damit alle bestehenden Aufrufer
        unveraendertes Verhalten behalten (#1478 Codex P1, Runde 4).

        ``provider_id`` wird aus demselben effektiven Modell abgeleitet wie
        ``model`` (ueber ``_detect_provider(model=...)``, das zentrale
        ``registry.py::detect_provider`` bleibt die einzige Detection-
        Heuristik) — sonst klassifiziert ein ``describe_image(model=...:cloud)``
        gegen einen lokalen Ollama-Endpoint faelschlich als ``ollama`` statt
        ``cloud`` und die Kostenberechnung im ``PricingRegistry`` haelt den
        Call faelschlich fuer kostenlos (#1478 Codex P1, Runde 5).
        ``route_provider_id`` hat weiterhin Vorrang, wo es gesetzt ist.
        """
        if not getattr(self, "run_id", None):
            return

        effective_model = model if model is not None else self.model

        try:
            from ..services.llm_invocation_logger import LlmInvocationLogger

            logger_service = LlmInvocationLogger(self.run_id)
            logger_service.log_event(
                stage=getattr(self, "route_stage", None) or stage,
                provider_id=getattr(self, "route_provider_id", None)
                or self._detect_provider(model=effective_model),
                model=effective_model or "unknown",
                base_url=self.base_url,
                routing_version=getattr(self, "routing_version", None) or 0,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                http_status=http_status,
                remote_request_id=remote_request_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm invocation logging failed (LLM call proceeds): %s", exc)

    def _provider_attempt(
        self,
        call_kwargs: Dict[str, Any],
        context: str,
        *,
        model: Optional[str] = None,
    ) -> Tuple[Any, float]:
        """Run a SINGLE physical provider request with budget gate + failure telemetry.

        Pro Aufruf:
            1. ``_budget_check`` (BudgetExceededError passiert sauber durch, ohne
               Event/Record — der Hard-Limit ist bereits entschieden).
            2. ``self.client.chat.completions.create(**call_kwargs)``.
            3. Bei Exception: log failed Invocation-Event + ``_budget_record``
               + re-raise.
            4. Bei Erfolg: return ``(response, latency_ms)``; der Aufrufer
               loggt das Success-Event und führt ``_budget_record`` aus, sobald
               Usage-Informationen verfügbar sind (Streaming sammelt Usage
               erst während der Iteration).

        ``model`` ist das tatsaechlich angefragte Modell, falls es von
        ``self.model`` abweicht (z. B. ``describe_image`` mit ``model=``-
        Override oder ``VISION_MODEL_NAME``). Wird an die Failure-Telemetrie
        durchgereicht, damit die Usage nicht dem Text-Modell des Clients
        zugerechnet wird (#1478 Codex P1, Runde 4). Default ``None`` laesst
        ``_log_invocation_event`` auf ``self.model`` zurueckfallen.

        Wird absichtlich INNERHALB von ``llm_call_with_retry`` aufgerufen, damit
        jeder Retried-Attempt eine eigene Check/Event/Record-Triplet erhält.
        """
        from ..services.run_budget import BudgetExceededError

        self._budget_check()
        started = _time_mod.monotonic()
        try:
            response = self.client.chat.completions.create(**call_kwargs)
        except BudgetExceededError:
            # Sollte nicht passieren (Budget-Check liegt VOR dem Call),
            # aber wenn doch: kein doppelter Event/Record.
            raise
        except Exception as exc:  # noqa: BLE001 — Failure-Telemetrie, weiterreichen
            latency_ms = (_time_mod.monotonic() - started) * 1000.0
            # #1096: bei einem BadRequestError liefert das OpenAI-SDK den
            # entpackten Fehlerbody (message/code/param) ueber ``exc.body`` —
            # ohne das landete bisher nur "error_type=BadRequestError" im
            # Log, was 400s wie den temperature-unsupported_value-Quirk
            # ununterscheidbar von jedem anderen 400 macht.
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                logger.warning(
                    "LLM provider 400 detail model=%s message=%s code=%s param=%s",
                    self.model,
                    body.get("message"),
                    body.get("code"),
                    body.get("param"),
                )
            self._log_invocation_event(
                stage=context,
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
                http_status=getattr(exc, "status_code", None),
                model=model,
            )
            # Issue #764 (Codex P2): Fehlgeschlagener OpenAI-kompatibler
            # Call zaehlt ebenfalls als Providerattempt — ``_budget_record``
            # muss auch im Failure-Pfad laufen, sonst unterlaeuft der Call
            # das weiche ``max_llm_calls``-Limit (Fail-open ist hier explizit
            # erwuenscht — Hard-Limits greifen bereits vor dem Call).
            self._budget_record()
            raise
        latency_ms = (_time_mod.monotonic() - started) * 1000.0
        return response, latency_ms

    def _record_provider_success(
        self,
        response: Any,
        latency_ms: float,
        context: str,
        usage: Any = None,
        *,
        model: Optional[str] = None,
    ) -> None:
        """Log Success-Invocation-Event + ``_budget_record`` nach erfolgreichem Provider-Attempt.

        ``usage`` ist optional: bei regulären Responses wird es aus
        ``response.usage`` abgeleitet, bei Streams wird die Usage des letzten
        Chunks uebergeben.

        ``model`` ist das tatsaechlich angefragte Modell (siehe
        ``_provider_attempt``) — Default ``None`` faellt auf ``self.model``
        zurueck (#1478 Codex P1, Runde 4).
        """
        if usage is None:
            usage = getattr(response, "usage", None)
        prompt_tokens, completion_tokens = extract_int_token_usage(usage)
        self._log_invocation_event(
            stage=context,
            latency_ms=latency_ms,
            success=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )
        # Weiche Budget-Limits nach dem abgeschlossenen Call pruefen (#764).
        self._budget_record()
