"""
Budget-Guard für den OASIS-Simulations-Subprozess (Issue #764).

Der Subprozess ruft LLMs über CAMEL (ModelFactory), nicht über den
backend-internen LLMClient. Dieser Guard schließt die Lücke:

1. Usage-Recording: ein transparenter Proxy um das CAMEL-Modell extrahiert
   Token-Usage aus jeder ChatCompletion und hängt sie als Event an denselben
   Ledger (``llm_call_events.jsonl``, Stage ``simulation_rounds``) an, den
   auch das Backend liest. JSONL-Appends kleiner Zeilen sind auf POSIX
   O_APPEND-atomar; pro run_id schreibt in der Regel genau ein Subprozess
   in diese Stage.
2. Harte Limits an Runden-Grenzen: vor jeder neuen Simulationsrunde prüft
   der Guard Token-, Kosten-, Aufruf- und Zeitbudget. Bei Überschreitung
   schreibt er ``budget_abort.json`` ins Simulationsverzeichnis und die
   Runde wird nicht mehr gestartet — deterministisch, bevor weitere
   planbare Modellaufrufe entstehen. Laufende Aufrufe der aktuellen Runde
   werden sauber zu Ende geführt; die SQLite-DB mit Teilresultaten bleibt
   erhalten.

Aktivierung: ``budget_config.json`` im Simulationsverzeichnis (vom Backend
beim Run-Start geschrieben). Usage-Recording läuft immer, sobald
``AGORA_RUN_ID`` gesetzt ist — auch ohne Budget, damit der Verbrauch pro
Stage ehrlich ausgewiesen werden kann.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional

STAGE_ID = "simulation_rounds"
# Stage fuer physische Modellaufruf-Versuche, die im Auftrag eines Report-Runs
# ueber ein IPC-Interview-Kommando ausgeloest werden (#1478 Codex P1, Runde 6).
REPORT_INTERVIEW_STAGE_ID = "report_interview"
BUDGET_CONFIG_FILENAME = "budget_config.json"
BUDGET_ABORT_FILENAME = "budget_abort.json"


def _sanitize_base_url(url: Optional[str]) -> Optional[str]:
    """Userinfo/Query aus URL entfernen (keine Secrets in den Ledger)."""
    if not url:
        return url
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    host = parsed.hostname or ""
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    return urlunparse(parsed._replace(netloc=netloc, query="", fragment=""))


class SubprocessBudgetGuard:
    """Usage-Recorder + Hard-Limit-Prüfung für den Simulations-Subprozess."""

    def __init__(
        self,
        simulation_dir: str,
        run_id: str,
        budget_config: Optional[dict] = None,
    ):
        self.simulation_dir = simulation_dir
        self.run_id = run_id
        self.budget_config = budget_config or {}
        self.enforcement = self.budget_config.get("enforcement", "soft")
        self._started_monotonic = time.monotonic()
        self._calls = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._loggers: dict[str, Any] = {}
        # Report-Attribution (#1478 Codex P1, Runde 6): waehrend eines mit
        # ``attribute_to`` markierten Blocks gehen physische Modellaufrufe an
        # ein FREMDES Budget (den Report-Run), nicht an ``self.run_id``/
        # ``STAGE_ID``. ``None`` = Standardpfad, unveraendertes Verhalten.
        self._attribution_override: Optional[tuple[str, str]] = None

    # -- Setup ---------------------------------------------------------------

    @classmethod
    def from_environment(cls, simulation_dir: str) -> Optional["SubprocessBudgetGuard"]:
        """Guard aus Umgebung aufbauen; None wenn kein run_id-Kontext."""
        run_id = os.environ.get("AGORA_RUN_ID")
        if not run_id:
            return None
        config: Optional[dict] = None
        config_path = os.path.join(simulation_dir, BUDGET_CONFIG_FILENAME)
        try:
            with open(config_path, encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                config = raw
        except FileNotFoundError:
            config = None
        except (json.JSONDecodeError, OSError):
            config = None
        return cls(simulation_dir, run_id, config)

    def _invocation_logger(self, run_id: str):
        logger = self._loggers.get(run_id)
        if logger is None:
            from app.services.llm_invocation_logger import LlmInvocationLogger

            logger = LlmInvocationLogger(run_id)
            self._loggers[run_id] = logger
        return logger

    # -- Report-Attribution (#1478 Codex P1, Runde 6) -------------------------

    @contextmanager
    def attribute_to(self, run_id: str, stage: str) -> Iterator[None]:
        """Physische Modellaufrufe waehrend dieses Blocks einem anderen Run zuordnen.

        Der physische LLM-Call fuer ein IPC-Interview laeuft ueber denselben
        ``_UsageTrackingModelProxy`` wie jede Simulationsrunde, traegt aber ein
        ANDERES Budget: den Report-Run, dessen ``run_id`` das Interview-Kommando
        mitbringt (``report_run_id`` in ``sim_runtime.ipc.IPCHandler``), statt
        ``self.run_id`` (das simulationszeitliche ``AGORA_RUN_ID``). Ohne diese
        Zuordnung landete der physische Call im falschen Ledger, und der Report-
        Run sah trotz erfolgreichem Interview nie einen gestiegenen Verbrauch.

        Die Wait-Mode-Kommandoschleife in ``platform_runner.py`` verarbeitet
        IPC-Kommandos sequentiell (``await self.ipc_handler.process_commands()``
        in einer einzigen Coroutine) — es gibt daher keine Nebenlaeufigkeit
        zwischen zwei Zuordnungen, ein einfaches Instanzattribut genuegt.
        """
        previous = self._attribution_override
        self._attribution_override = (run_id, stage)
        try:
            yield
        finally:
            self._attribution_override = previous

    def _enforce_before_physical_call(self) -> None:
        """Hartes Report-Budget UNMITTELBAR vor jedem physischen Call pruefen.

        Nur aktiv unter :meth:`attribute_to`. Der Standardpfad des
        Simulations-Runs bleibt bei der bestehenden Runden-Grenzen-Pruefung
        (:meth:`check_round_boundary`) — unbeteiligte Aufrufer aendern ihr
        Verhalten nicht. Nutzt denselben zentralen Mechanismus wie das
        Flask-seitige Vorab-Gate (``_report_budget_guard`` in
        ``interview_client.py``): ``RunBudgetEnforcer.check_before_call()``.
        Kein zweiter Budget-Mechanismus neben ``RunBudgetEnforcer``.
        """
        override = self._attribution_override
        if override is None:
            return
        report_run_id, _stage = override
        from app.services.run_budget import BudgetExceededError, RunBudgetEnforcer

        try:
            enforcer = RunBudgetEnforcer.for_run(report_run_id)
        except Exception as exc:  # noqa: BLE001 — Aufbaufehler blockiert den Call nicht
            print(f"[budget-guard] report enforcer unavailable: {exc}", flush=True)
            return
        if enforcer is None:
            return
        try:
            enforcer.check_before_call()
        except BudgetExceededError:
            raise
        except Exception as exc:  # noqa: BLE001 — Budget ist Zusatz, kein Hotpath-Risiko
            print(f"[budget-guard] report budget check failed (call proceeds): {exc}", flush=True)

    def _release_report_reservation(self, report_run_id: str) -> None:
        """Reservierung aus :meth:`_enforce_before_physical_call` freigeben.

        Dasselbe Check/Record-Paar wie ``LLMClient._provider_attempt`` /
        ``_record_provider_success`` (``_budget_check`` + ``_budget_record``):
        ``check_before_call()`` reserviert einen Slot, der erst nach dem
        abgeschlossenen physischen Call wieder frei wird — sonst haelt jeder
        Report-Interview-Call sein Reservierungs-Slot bis zum TTL-Ablauf
        (900s) besetzt und blockiert nachfolgende Calls faelschlich.
        """
        from app.services.run_budget import RunBudgetEnforcer

        try:
            enforcer = RunBudgetEnforcer.for_run(report_run_id)
        except Exception as exc:  # noqa: BLE001
            print(
                f"[budget-guard] report enforcer unavailable (reservation not released): {exc}",
                flush=True,
            )
            return
        if enforcer is None:
            return
        try:
            enforcer.record_after_call()
        except Exception as exc:  # noqa: BLE001 — Budget ist Zusatz, kein Hotpath-Risiko
            print(f"[budget-guard] report record_after_call failed: {exc}", flush=True)

    # -- Usage-Recording -----------------------------------------------------

    def record_call(
        self,
        *,
        latency_ms: float,
        success: bool,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """Einen CAMEL-Call in den gemeinsamen Ledger verbuchen.

        Ohne aktive :meth:`attribute_to`-Zuordnung geht der Call wie bisher an
        ``self.run_id``/``STAGE_ID`` und zaehlt in die lokalen Runden-Zaehler
        (``check_round_boundary``). Unter einer aktiven Report-Zuordnung
        (#1478 Codex P1, Runde 6) geht der Call an den Report-Run/dessen Stage;
        die lokalen Simulations-Zaehler bleiben unberuehrt, weil dieser Call
        ein fremdes Budget traegt und sonst das Simulations-Budget faelschlich
        mitbelasten wuerde.
        """
        override = self._attribution_override
        target_run_id, stage = override if override is not None else (self.run_id, STAGE_ID)

        if override is None:
            self._calls += 1 if success else 0
            if isinstance(prompt_tokens, int):
                self._prompt_tokens += prompt_tokens
            if isinstance(completion_tokens, int):
                self._completion_tokens += completion_tokens

        try:
            from app.llm.providers.registry import detect_provider

            base_url = os.environ.get("LLM_BASE_URL", "")
            model = os.environ.get("LLM_MODEL_NAME", "") or "unknown"
            self._invocation_logger(target_run_id).log_event(
                stage=stage,
                provider_id=detect_provider(base_url, model),
                model=model,
                base_url=base_url,
                routing_version=0,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — Recording darf die Sim nicht stören
            print(f"[budget-guard] usage recording failed: {exc}", flush=True)

        if override is not None:
            # Reservierung aus ``_enforce_before_physical_call`` erst NACH dem
            # Ledger-Write freigeben — dieselbe Reihenfolge wie
            # ``LLMClient._record_provider_success``/``_provider_attempt``
            # (Event zuerst, dann ``_budget_record``/``record_after_call``).
            self._release_report_reservation(target_run_id)

    def wrap_model(self, model: Any) -> Any:
        """CAMEL-Modell mit Usage-Tracking-Proxy umgeben."""
        return _UsageTrackingModelProxy(model, self)

    # -- Hard Limits ---------------------------------------------------------

    def _observed(self) -> dict[str, Optional[int]]:
        observed: dict[str, Optional[int]] = {
            "tokens": self._prompt_tokens + self._completion_tokens,
            "calls": self._calls,
            "time": int(time.monotonic() - self._started_monotonic),
            "cost": None,
        }
        try:
            from app.llm.providers.registry import detect_provider
            from app.services.pricing_registry import get_pricing_registry

            base_url_raw = os.environ.get("LLM_BASE_URL", "")
            model_name = os.environ.get("LLM_MODEL_NAME", "")
            provider = detect_provider(base_url_raw, model_name)
            quote = get_pricing_registry().resolve(
                provider, model_name, _sanitize_base_url(base_url_raw)
            )
            observed["cost"] = quote.cost_micros(
                self._prompt_tokens, self._completion_tokens
            )
        except Exception:  # noqa: BLE001 — unbekannte Preise lösen nie aus
            observed["cost"] = None
        return observed

    def check_round_boundary(self, round_num: int) -> Optional[dict]:
        """Vor einer neuen Runde harte Limits prüfen.

        Returns:
            Abort-Info dict bei Überschreitung (schreibt budget_abort.json),
            sonst None.
        """
        if self.enforcement != "hard" or not self.budget_config:
            return None
        limits = {
            "tokens": self.budget_config.get("max_tokens"),
            "cost": self.budget_config.get("max_cost_micros"),
            "time": self.budget_config.get("max_duration_seconds"),
            "calls": self.budget_config.get("max_llm_calls"),
        }
        observed = self._observed()
        for dimension, limit in limits.items():
            if limit is None:
                continue
            value = observed.get(dimension)
            if value is not None and value >= limit:
                abort_info = {
                    "dimension": dimension,
                    "observed": value,
                    "threshold": limit,
                    "round": round_num,
                    "ts": time.time(),
                }
                self._write_abort_marker(abort_info)
                return abort_info
        return None

    def _write_abort_marker(self, abort_info: dict) -> None:
        """First-writer-wins: Backend-Monitor und Guard dürfen nicht racen."""
        path = os.path.join(self.simulation_dir, BUDGET_ABORT_FILENAME)
        if os.path.exists(path):
            return
        try:
            os.makedirs(self.simulation_dir, exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(abort_info, handle)
                handle.write("\n")
            os.replace(tmp_path, path)
        except OSError as exc:
            print(f"[budget-guard] abort marker write failed: {exc}", flush=True)


class _UsageTrackingModelProxy:
    """Transparenter Proxy um ein CAMEL-ModelBackend.

    Fängt run/_run/arun/_arun ab, misst Latenz und extrahiert Token-Usage
    aus ChatCompletion-Resultaten (falls der Provider sie liefert — sonst
    bleibt die Messung ehrlich unbekannt).

    Issue #764 (Review) — Protokoll-Audit:
        CAMEL/OASIS ruft ModelBackends ausschließlich über die vier
        Methoden ``run`` / ``_run`` / ``arun`` / ``_arun`` auf
        (siehe ``camel.models.base_model.BaseModelBackend``).
        Es gibt keine ``__call__``-, ``__deepcopy__``-, ``__reduce__``-
        oder sonstigen Dunder-Hooks, die CAMEL erwartet. Wir leiten nur
        die vier Methoden explizit durch und reichen alles andere via
        ``__getattr__`` / ``__setattr__`` an das Target durch. Copy,
        Pickle und ``__call__`` werden absichtlich NICHT implementiert —
        wäre das nötig, würden die Tests
        ``test_proxy_has_no_copy_or_reduce_protocol`` und
        ``test_proxy_does_not_implement_call`` fehlschlagen.

    PR #975 (CodeRabbit) — Typ-Transparenz:
        Der Aufruf-Audit oben war unvollständig: CAMEL prüft das
        übergebene Backend in ``ChatAgent._resolve_models`` per
        ``isinstance(model, BaseModelBackend)`` und wirft sonst
        ``TypeError: Unsupported type for model parameter``. Da
        ``__getattr__`` erst nach der regulären Attributsuche greift,
        liefert ein nackter Proxy sein eigenes ``__class__`` und fällt
        durch den Check — die Simulation stirbt beim Agent-Graph-Aufbau,
        sobald ``AGORA_RUN_ID`` gesetzt ist. Deshalb delegiert
        ``__class__`` an das Target: ``isinstance`` prüft nach dem
        ``type()``-Treffer auch ``obj.__class__``. Der reale Typ bleibt
        der Proxy, die Instrumentierung damit erhalten.
    """

    def __init__(self, target: Any, guard: SubprocessBudgetGuard):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_guard", guard)

    @property  # type: ignore[misc]
    def __class__(self) -> Any:  # type: ignore[override]
        return object.__getattribute__(self, "_target").__class__

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_target"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_target"), name, value)

    @staticmethod
    def _extract_usage(result: Any) -> tuple[Optional[int], Optional[int]]:
        usage = getattr(result, "usage", None)
        if usage is None:
            return None, None
        # Issue #764 (Codex P1): provider, die usage als Mapping/dict
        # liefern (z.B. Roh-OpenAI-kompatible Clients ohne pydantic-Model),
        # sollen ebenfalls ausgewertet werden. Mapping-Lookup vor
        # Attribut-Lookup — letzterer ist strenger typisiert und dominiert.
        if isinstance(usage, Mapping):
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
        else:
            prompt = getattr(usage, "prompt_tokens", None)
            completion = getattr(usage, "completion_tokens", None)
        return (
            prompt if isinstance(prompt, int) else None,
            completion if isinstance(completion, int) else None,
        )

    def run(self, messages, *args, **kwargs):
        target = object.__getattribute__(self, "_target")
        guard = object.__getattribute__(self, "_guard")
        guard._enforce_before_physical_call()
        started = time.monotonic()
        try:
            result = target.run(messages, *args, **kwargs)
        except Exception as exc:
            guard.record_call(
                latency_ms=(time.monotonic() - started) * 1000,
                success=False,
                error_type=exc.__class__.__name__,
            )
            raise
        prompt, completion = self._extract_usage(result)
        guard.record_call(
            latency_ms=(time.monotonic() - started) * 1000,
            success=True,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )
        return result

    def _run(self, messages, *args, **kwargs):
        target = object.__getattribute__(self, "_target")
        guard = object.__getattribute__(self, "_guard")
        guard._enforce_before_physical_call()
        started = time.monotonic()
        try:
            result = target._run(messages, *args, **kwargs)
        except Exception as exc:
            guard.record_call(
                latency_ms=(time.monotonic() - started) * 1000,
                success=False,
                error_type=exc.__class__.__name__,
            )
            raise
        prompt, completion = self._extract_usage(result)
        guard.record_call(
            latency_ms=(time.monotonic() - started) * 1000,
            success=True,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )
        return result

    async def arun(self, messages, *args, **kwargs):
        target = object.__getattribute__(self, "_target")
        guard = object.__getattribute__(self, "_guard")
        guard._enforce_before_physical_call()
        started = time.monotonic()
        try:
            result = await target.arun(messages, *args, **kwargs)
        except Exception as exc:
            guard.record_call(
                latency_ms=(time.monotonic() - started) * 1000,
                success=False,
                error_type=exc.__class__.__name__,
            )
            raise
        prompt, completion = self._extract_usage(result)
        guard.record_call(
            latency_ms=(time.monotonic() - started) * 1000,
            success=True,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )
        return result

    async def _arun(self, messages, *args, **kwargs):
        target = object.__getattribute__(self, "_target")
        guard = object.__getattribute__(self, "_guard")
        guard._enforce_before_physical_call()
        started = time.monotonic()
        try:
            result = await target._arun(messages, *args, **kwargs)
        except Exception as exc:
            guard.record_call(
                latency_ms=(time.monotonic() - started) * 1000,
                success=False,
                error_type=exc.__class__.__name__,
            )
            raise
        prompt, completion = self._extract_usage(result)
        guard.record_call(
            latency_ms=(time.monotonic() - started) * 1000,
            success=True,
            prompt_tokens=prompt,
            completion_tokens=completion,
        )
        return result
