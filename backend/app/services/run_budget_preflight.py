"""
Preflight-Schätzung für Runs (Issue #764).

Berechnet vor dem Start eine nachvollziehbare, ehrlich gekennzeichnete
Schätzung von Tokens, Kosten und Laufzeit. Keine Pseudoexaktheit:

- Ergebnisse sind Bereiche (low/high), gerundet auf 2 signifikante Stellen.
- Historische Verbrauchsdaten (usage_summary.json abgeschlossener Runs)
  schlagen konservative Heuristiken nur dann, wenn genügend Daten vorliegen.
- Unbekannte Preise führen zu cost_status=unknown, niemals zu 0.
- Lokale Modelle sind free (0 Micros, ehrlich bepreist).
"""
from __future__ import annotations

import math
import statistics
from typing import Optional

from app.contracts.run_budget_contract import (
    PreflightEstimate,
    PreflightModelRef,
)
from app.services.pricing_registry import PricingRegistry, get_pricing_registry
from app.services.run_usage_ledger import load_usage_summary
from app.utils.logger import get_logger

logger = get_logger("agora.run_budget_preflight")

# Heuristiken, wenn keine historischen Messwerte vorliegen. Bewusst
# konservativ und als solche in warnings dokumentiert.
_HEURISTIC_TOKENS_PER_CALL_LOW = 1_000
_HEURISTIC_TOKENS_PER_CALL_HIGH = 5_000
_HEURISTIC_LATENCY_S_PER_CALL_LOW = 2.0
_HEURISTIC_LATENCY_S_PER_CALL_HIGH = 8.0
# Anteil der Agenten, die pro Runde tatsächlich einen LLM-Call auslösen
# (OASIS aktiviert Agenten stundenbasiert; Erfahrungswert 30–100 %).
_ACTIVE_RATIO_LOW = 0.3
_ACTIVE_RATIO_HIGH = 1.0
# Effektive Parallelität der Calls (Semaphore im OASIS-Env).
_CONCURRENCY = 5
_MIN_HISTORY_RUNS = 3


def _round_sig(value: float, digits: int = 2) -> int:
    """Auf signifikante Stellen runden — gegen Pseudoexaktheit."""
    if value <= 0:
        return 0
    magnitude = math.floor(math.log10(value))
    factor = 10 ** (magnitude - digits + 1)
    return int(round(value / factor) * factor)


class _HistoryStats:
    def __init__(self) -> None:
        self.runs_used = 0
        self.tokens_per_call: list[float] = []
        self.latency_s_per_call: list[float] = []


def collect_historical_stats(limit: int = 30) -> _HistoryStats:
    """Pro-Call-Kennzahlen aus abgeschlossenen Runs mit Usage-Snapshot.

    Returns:
        Stats mit runs_used=0, wenn keine historischen Daten vorliegen.
    """
    from app.services.run_registry import RunRegistry

    stats = _HistoryStats()
    try:
        runs = RunRegistry().list_runs(
            run_type="simulation_run", status="completed", limit=limit
        )
    except Exception as exc:  # noqa: BLE001 — Historie ist optional
        logger.warning("preflight: history scan failed: %s", exc)
        return stats

    for run in runs:
        summary = load_usage_summary(run["run_id"])
        if summary is None:
            continue
        totals = summary.totals
        if totals.llm_calls <= 0:
            continue
        if totals.total_tokens:
            stats.tokens_per_call.append(totals.total_tokens / totals.llm_calls)
        if totals.duration_ms > 0:
            stats.latency_s_per_call.append(totals.duration_ms / 1000.0 / totals.llm_calls)
        stats.runs_used += 1
    return stats


def estimate_run(
    *,
    num_agents: int,
    max_rounds: int,
    models: Optional[list[PreflightModelRef]] = None,
    pricing: Optional[PricingRegistry] = None,
    history: Optional[_HistoryStats] = None,
) -> PreflightEstimate:
    """Preflight-Schätzung für einen Simulations-Run berechnen."""
    pricing = pricing or get_pricing_registry()
    models = models or []
    warnings: list[str] = []

    if num_agents <= 0 or max_rounds <= 0:
        return PreflightEstimate(
            models=models,
            pricing_version=pricing.pricing_version,
            pricing_source=pricing.pricing_source,
            data_quality="unknown",
            warnings=["Keine Agenten oder Runden konfiguriert — Schätzung unmöglich."],
        )

    if history is None:
        history = collect_historical_stats()

    has_history = history.runs_used >= _MIN_HISTORY_RUNS and bool(
        history.tokens_per_call or history.latency_s_per_call
    )

    # --- Tokens pro Call -----------------------------------------------------
    if history.tokens_per_call:
        median_tokens = statistics.median(history.tokens_per_call)
        tokens_per_call_low = median_tokens * 0.5
        tokens_per_call_high = median_tokens * 2.0
        if not has_history:
            warnings.append(
                f"Wenig historische Daten ({history.runs_used} Runs) — "
                "Tokenschätzung unsicher."
            )
    else:
        tokens_per_call_low = _HEURISTIC_TOKENS_PER_CALL_LOW
        tokens_per_call_high = _HEURISTIC_TOKENS_PER_CALL_HIGH
        warnings.append(
            "Keine historischen Verbrauchsdaten — Tokenschätzung basiert auf "
            "konservativen Heuristiken."
        )

    # --- Latenz pro Call -----------------------------------------------------
    if history.latency_s_per_call:
        median_latency = statistics.median(history.latency_s_per_call)
        latency_low = median_latency * 0.5
        latency_high = median_latency * 2.0
    else:
        latency_low = _HEURISTIC_LATENCY_S_PER_CALL_LOW
        latency_high = _HEURISTIC_LATENCY_S_PER_CALL_HIGH

    # --- Geplante Calls ------------------------------------------------------
    calls_low = num_agents * max_rounds * _ACTIVE_RATIO_LOW
    calls_high = num_agents * max_rounds * _ACTIVE_RATIO_HIGH
    warnings.append(
        "LLM-Aufrufe pro Runde sind lastabhängig (Aktivierungsrate der "
        "Agenten) — berechnet mit 30–100 % aktiven Agenten pro Runde."
    )

    tokens_low = _round_sig(calls_low * tokens_per_call_low)
    tokens_high = _round_sig(calls_high * tokens_per_call_high)

    duration_low = _round_sig(calls_low * latency_low / _CONCURRENCY)
    duration_high = _round_sig(calls_high * latency_high / _CONCURRENCY)

    # --- Kosten ---------------------------------------------------------------
    quotes = [
        pricing.resolve(model.provider_id, model.model_id, model.base_url_sanitized)
        for model in models
    ]
    cost_micros_low: Optional[int] = None
    cost_micros_high: Optional[int] = None
    cost_status = "unknown"
    if not models:
        warnings.append(
            "Kein Modell aufgelöst — Kosten können nicht geschätzt werden."
        )
        cost_status = "unknown"
    elif all(q.status == "free" for q in quotes):
        cost_micros_low = 0
        cost_micros_high = 0
        cost_status = "free"
    elif any(q.status == "unknown" for q in quotes):
        warnings.append(
            "Für mindestens ein Modell liegt kein Richtpreis vor — "
            "Kosten unbekannt (nicht 0)."
        )
        cost_status = "unknown"
    else:
        # Alle Modelle bepreist: gewichteter Mittelpreis über Modelle.
        input_rate = statistics.mean(
            q.input_per_mtok_micros for q in quotes if q.input_per_mtok_micros is not None
        )
        output_rate = statistics.mean(
            q.output_per_mtok_micros for q in quotes if q.output_per_mtok_micros is not None
        )
        # Annahme: 2/3 Input, 1/3 Output (lange Agent-Kontexte).
        blended = (2 * input_rate + output_rate) / 3
        cost_micros_low = _round_sig(tokens_low * blended / 1_000_000)
        cost_micros_high = _round_sig(tokens_high * blended / 1_000_000)
        cost_status = "estimated"
        warnings.append(
            f"Kosten basieren auf statischen Richtpreisen "
            f"(Version {pricing.pricing_version}) — keine Preisgarantie."
        )

    if has_history:
        data_quality = "medium" if cost_status == "unknown" else "high"
    elif history.runs_used > 0:
        data_quality = "low"
    else:
        data_quality = "low" if models else "unknown"

    return PreflightEstimate(
        estimated_tokens_low=tokens_low,
        estimated_tokens_high=tokens_high,
        estimated_cost_micros_low=cost_micros_low,
        estimated_cost_micros_high=cost_micros_high,
        estimated_duration_seconds_low=duration_low,
        estimated_duration_seconds_high=duration_high,
        cost_status=cost_status,  # type: ignore[arg-type]
        models=models,
        pricing_version=pricing.pricing_version,
        pricing_source=pricing.pricing_source,
        data_quality=data_quality,  # type: ignore[arg-type]
        warnings=warnings,
    )
