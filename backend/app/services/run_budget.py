"""
Run Budget Enforcement (Issue #764).

Weiche und harte Limits für Token, Kosten, Laufzeit und LLM-Aufrufe.

- Weiche Limits: Run läuft weiter, Warnung wird einmalig je Dimension
  erzeugt, in ``budget_warnings.json`` persistiert und als Manifest-Event
  auditiert.
- Harte Limits: :class:`BudgetExceededError` wird unmittelbar VOR dem
  nächsten planbaren Modellaufruf geworfen; der Aufruf findet nicht mehr
  statt (deterministisch). Bereits erzeugte Teilresultate bleiben erhalten,
  weil die Verbuchung nach jedem abgeschlossenen Aufruf erfolgt.

Race-Vermeidung: Der Verbrauch wird nach jedem Call in die JSONL-Ledger
geschrieben; Checks lesen denselben Ledger (mtime-Cache). Der Check liegt
direkt am Anfang von ``LLMClient.chat`` — zwischen Check und Call liegt
kein weiterer kostenrelevanter Schritt desselben Threads.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Optional

from app.contracts.run_budget_contract import (
    BudgetWarning,
    RunBudgetConfig,
    RunBudgetStatus,
    TerminationReason,
    UsageMetrics,
)
from app.services.run_usage_ledger import aggregate_usage, load_call_events_cached
from app.utils.artifact_locator import ArtifactLocator
from app.utils.logger import get_logger

logger = get_logger("agora.run_budget")

WARNINGS_FILENAME = "budget_warnings.json"

DIMENSION_TO_REASON: dict[str, TerminationReason] = {
    "tokens": "budget_tokens",
    "cost": "budget_cost",
    "time": "budget_time",
    "calls": "budget_calls",
}

_DIMENSION_LABELS = {
    "tokens": "Tokenbudget",
    "cost": "Kostenbudget",
    "time": "Zeitbudget",
    "calls": "Aufrufbudget",
}


class BudgetExceededError(RuntimeError):
    """Hartes Budget erreicht — weitere planbare Modellaufrufe verboten."""

    def __init__(self, dimension: str, observed: int, threshold: int):
        self.dimension = dimension
        self.observed = observed
        self.threshold = threshold
        super().__init__(
            f"{_DIMENSION_LABELS.get(dimension, dimension)} überschritten: "
            f"{observed} >= {threshold}"
        )

    @property
    def termination_reason(self) -> TerminationReason:
        return DIMENSION_TO_REASON.get(self.dimension, "error")  # type: ignore[return-value]


def _warnings_path(run_id: str) -> str:
    return os.path.join(ArtifactLocator.run_dir(run_id), WARNINGS_FILENAME)


def load_warnings(run_id: str) -> list[BudgetWarning]:
    path = _warnings_path(run_id)
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        return [BudgetWarning.model_validate(item) for item in raw]
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return []


def _persist_warnings(run_id: str, warnings: list[BudgetWarning]) -> None:
    path = _warnings_path(run_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump([w.model_dump(mode="json") for w in warnings], handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


def _parse_started_epoch(started_at: Optional[str]) -> Optional[float]:
    if not started_at:
        return None
    try:
        return datetime.fromisoformat(started_at).timestamp()
    except ValueError:
        return None


def get_run_budget_config(run_id: str) -> Optional[RunBudgetConfig]:
    """Budget-Config aus dem Run-Manifest lesen (None wenn keins gesetzt)."""
    from app.services.run_registry import RunRegistry

    manifest = RunRegistry().get_run(run_id)
    if not manifest:
        return None
    raw = (manifest.get("metadata") or {}).get("budget")
    if not raw:
        return None
    try:
        return RunBudgetConfig.model_validate(raw)
    except ValueError:
        logger.warning("run_budget: ungültige Budget-Config im Manifest %s ignoriert", run_id)
        return None


def set_run_budget_config(run_id: str, config: RunBudgetConfig) -> None:
    """Budget-Config ins Run-Manifest schreiben (metadata.budget, ohne Secrets)."""
    from app.services.run_registry import RunRegistry

    RunRegistry().update_run(
        run_id, metadata={"budget": config.model_dump(mode="json")}
    )


def set_termination_reason(run_id: str, reason: TerminationReason) -> None:
    """Abbruchgrund top-level ins Manifest schreiben (RunDetail-Contract)."""
    from app.services.run_registry import RunRegistry

    RunRegistry().update_run(run_id, termination_reason=reason)


def mark_budget_abort(run_id: str, dimension: str, observed: int, threshold: int) -> None:
    """Run als budgetbedingt beendet markieren (stopped + termination_reason).

    Wird von den Orchestrierungsstellen aufgerufen, die
    :class:`BudgetExceededError` fangen. Teilresultate bleiben erhalten —
    der Status ist „stopped", nicht „failed".
    """
    from app.services.run_registry import RunRegistry

    reason = DIMENSION_TO_REASON.get(dimension, "error")
    registry = RunRegistry()
    registry.update_run(
        run_id,
        status="stopped",
        termination_reason=reason,
        message=(
            f"Budgetabbruch: {_DIMENSION_LABELS.get(dimension, dimension)} "
            f"erreicht ({observed} >= {threshold})"
        ),
        event_type="budget_abort",
        event_details={"dimension": dimension, "observed": observed, "threshold": threshold},
    )


class RunBudgetEnforcer:
    """Prüft und verbucht Budgets für einen Run."""

    def __init__(
        self,
        run_id: str,
        config: RunBudgetConfig,
        started_at_epoch: Optional[float] = None,
    ):
        self.run_id = run_id
        self.config = config
        self._started_at_epoch = started_at_epoch

    @classmethod
    def for_run(cls, run_id: str) -> Optional["RunBudgetEnforcer"]:
        """Enforcer aus dem Manifest aufbauen; None wenn kein Budget gesetzt."""
        from app.services.run_registry import RunRegistry

        config = get_run_budget_config(run_id)
        if config is None:
            return None
        manifest = RunRegistry().get_run(run_id) or {}
        return cls(
            run_id=run_id,
            config=config,
            started_at_epoch=_parse_started_epoch(manifest.get("started_at")),
        )

    # -- Verbrauch -----------------------------------------------------------

    def consumed(self) -> UsageMetrics:
        """Aktueller Gesamtverbrauch aus dem Ledger."""
        events = load_call_events_cached(self.run_id)
        return aggregate_usage(self.run_id, events=events).totals

    def _elapsed_seconds(self) -> Optional[float]:
        if self._started_at_epoch is None:
            return None
        return max(0.0, time.time() - self._started_at_epoch)

    def _observed(self, consumed: UsageMetrics) -> dict[str, Optional[int]]:
        elapsed = self._elapsed_seconds()
        return {
            "tokens": consumed.total_tokens,
            "cost": consumed.cost_micros,
            "time": int(elapsed) if elapsed is not None else None,
            "calls": consumed.llm_calls,
        }

    def _limits(self) -> dict[str, Optional[int]]:
        return {
            "tokens": self.config.max_tokens,
            "cost": self.config.max_cost_micros,
            "time": self.config.max_duration_seconds,
            "calls": self.config.max_llm_calls,
        }

    # -- Prüfung -------------------------------------------------------------

    def check_before_call(self) -> None:
        """Harte Limits prüfen — wirft BudgetExceededError VOR dem Call.

        Unbekannte Werte (z. B. Kosten ohne Preisdaten) können ein Limit
        nicht auslösen; sie werden als None behandelt.
        """
        if self.config.enforcement != "hard":
            return
        consumed = self.consumed()
        observed = self._observed(consumed)
        for dimension, limit in self._limits().items():
            if limit is None:
                continue
            value = observed[dimension]
            if value is not None and value >= limit:
                self._record_warning(dimension, "hard", threshold=limit, observed=value)
                raise BudgetExceededError(dimension, observed=value, threshold=limit)

    def record_after_call(self) -> None:
        """Weiche Limits nach einem abgeschlossenen Call prüfen + auditieren."""
        consumed = self.consumed()
        observed = self._observed(consumed)
        severity = self.config.enforcement
        for dimension, limit in self._limits().items():
            if limit is None:
                continue
            value = observed[dimension]
            if value is not None and value >= limit:
                self._record_warning(dimension, severity, threshold=limit, observed=value)

    # -- Warnungen -----------------------------------------------------------

    def _record_warning(
        self, dimension: str, severity: str, *, threshold: int, observed: int
    ) -> None:
        """Warnung einmalig je (dimension, severity) persistieren + auditieren."""
        warnings = load_warnings(self.run_id)
        if any(
            w.dimension == dimension and w.severity == severity for w in warnings
        ):
            return
        warning = BudgetWarning(
            dimension=dimension,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            threshold=threshold,
            observed=observed,
            message=(
                f"{_DIMENSION_LABELS.get(dimension, dimension)} "
                f"{'hart' if severity == 'hard' else 'weich'} überschritten: "
                f"{observed} >= {threshold}"
            ),
            ts=datetime.now().isoformat(),
        )
        warnings.append(warning)
        try:
            _persist_warnings(self.run_id, warnings)
        except OSError as exc:
            logger.warning("run_budget: Warnung konnte nicht persistiert werden: %s", exc)
        try:
            from app.services.run_registry import RunRegistry

            RunRegistry().append_event(
                self.run_id,
                event_type="budget_warning",
                message=warning.message,
                details=warning.model_dump(mode="json"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_budget: Manifest-Event fehlgeschlagen: %s", exc)


def get_run_budget_status(run_id: str) -> Optional[RunBudgetStatus]:
    """Aktuellen Budget-Zustand für die API zusammensetzen (None ohne Budget)."""
    config = get_run_budget_config(run_id)
    if config is None:
        return None
    enforcer = RunBudgetEnforcer.for_run(run_id)
    assert enforcer is not None
    consumed = enforcer.consumed()
    # Warnungen auch leseseitig materialisieren: so werden weiche
    # Überschreitungen aus Subprozess-Stages (simulation_rounds) sichtbar,
    # ohne dass der Subprozess selbst Warnlogik braucht. Idempotent (Dedupe).
    enforcer.record_after_call()
    warnings = load_warnings(run_id)

    from app.services.run_registry import RunRegistry

    manifest = RunRegistry().get_run(run_id) or {}
    termination = manifest.get("termination_reason")

    exceeded_dimension: Optional[str] = None
    if isinstance(termination, str) and termination.startswith("budget_"):
        exceeded_dimension = {
            "budget_tokens": "tokens",
            "budget_cost": "cost",
            "budget_time": "time",
            "budget_calls": "calls",
        }.get(termination)

    status = "ok"
    if exceeded_dimension or any(w.severity == "hard" for w in warnings):
        status = "exceeded"
    elif warnings:
        status = "warning"

    return RunBudgetStatus(
        config=config,
        consumed=consumed,
        warnings=warnings,
        status=status,  # type: ignore[arg-type]
        exceeded_dimension=exceeded_dimension,  # type: ignore[arg-type]
    )


def serialize_for_manifest(data: Any) -> Any:
    """Defensive Secret-Hygiene: Budget-/Usage-Payloads dürfen nie Keys enthalten."""
    text = json.dumps(data, default=str)
    for forbidden in ("api_key", "apiKey", "secret", "authorization", "Bearer "):
        if forbidden in text:
            raise ValueError(
                f"run_budget: verbotenes Feld '{forbidden}' in Budget-Payload erkannt"
            )
    return data


def inherit_budget_from_simulation(run_id: str, simulation_id: str) -> bool:
    """Budget des zugehörigen simulation_run auf einen Folge-Run vererben.

    Report-Runs erben so das beim Simulationsstart gesetzte Budget (Issue
    #764), ohne dass das UI es erneut senden muss. Setzt kein Budget, wenn
    der Run bereits eines hat oder die Simulation keines besitzt.
    """
    from app.services.run_registry import RunRegistry

    if get_run_budget_config(run_id) is not None:
        return False
    source = RunRegistry().get_latest_by_linked_id(
        "simulation_id", simulation_id, run_type="simulation_run"
    )
    if not source:
        return False
    config = get_run_budget_config(source["run_id"])
    if config is None:
        return False
    set_run_budget_config(run_id, config)
    return True
