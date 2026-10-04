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
from typing import Any, Optional

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
#
# Issue #1772: Die frueheren pauschalen 1.000-5.000 Tokens je Aufruf galten fuer
# kurze Einzelprompts (Graph, Persona, Bericht), nicht fuer die Simulation. Dort
# waechst der Kontext je Agentenschritt mit der Runde, solange das Agenten-
# Gedaechtnis nicht begrenzt ist. Gemessen am Lauf ``sim_cc6067a70603``
# (2026-10-04, ``gpt-6-luna``, 24 Runden, 52 Agenten, Twitter+Reddit, 1.059
# erfolgreiche Aufrufe): Mittel 33.700 Eingabe-Tokens je erfolgreichem Aufruf
# (Median 20.600; Median der ersten Laufphase 3.800, der letzten 91.900),
# rund 50 Ausgabe-Tokens. Das lineare Modell
#     Eingabe-Tokens(Runde r) = BASE + GROWTH * r      (r = 1..Runden)
# ist darauf kalibriert: Runde 1 ~5.200 (gemessen 3.800), Mittel bei 24 Runden
# 2.000 + 3.200 * 12,5 = 42.000 (gemessen 33.700, bewusst konservativ ueber dem
# Mittel), Runde 24 ~78.800 (gemessen 91.900 in der letzten Phase -- das
# lineare Modell unterschaetzt das Ende, ueberschaetzt dafuer die Mitte).
_SIM_CONTEXT_BASE_TOKENS = 2_000
_SIM_CONTEXT_GROWTH_PER_ROUND = 3_200
_SIM_OUTPUT_TOKENS_PER_CALL = 50
# Fallback fuer andere Stages ohne eigenes Modell (nicht mehr fuer die Simulation).
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


def _fmt(value: float) -> str:
    """Ganzzahl mit Punkt als Tausendertrenner (deutsche Schreibweise)."""
    return f"{round(value):,}".replace(",", ".")


def simulation_tokens_per_agent_step(
    rounds: int, memory_context_cap_tokens: Optional[int] = None
) -> float:
    """Mittlere Eingabe-Tokens je Agentenschritt ueber ``rounds`` Runden.

    Modell siehe Konstanten oben: Kontext je Schritt waechst linear mit der
    Runde. ``memory_context_cap_tokens`` ist die Kontext-Obergrenze eines
    begrenzten Agenten-Gedaechtnisses (``None`` = unbegrenzt, Standard): ab
    der Runde, in der die Kurve die Obergrenze erreicht, bleibt der Kontext
    konstant, die Gesamtsumme waechst danach linear in den Runden.
    """
    if rounds <= 0:
        return 0.0
    cap = memory_context_cap_tokens
    total = 0.0
    for round_number in range(1, rounds + 1):
        context = _SIM_CONTEXT_BASE_TOKENS + _SIM_CONTEXT_GROWTH_PER_ROUND * round_number
        total += min(context, cap) if cap is not None else context
    return total / rounds


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


def _tokens_per_call_estimate(
    history: _HistoryStats,
    *,
    has_history: bool,
    max_rounds: int,
    memory_context_cap_tokens: Optional[int],
) -> tuple[float, float, float, list[str]]:
    """Tokens je Aufruf (untere/obere Schaetzung), Eingabeanteil und Warnungen.

    Mit Verlaufsdaten gilt deren Median, sonst das Messwertmodell der Simulation.
    """
    warnings: list[str] = []
    # ``input_share``: Anteil der Eingabe-Tokens an der Tokensumme (Kostenmodell).
    input_share = 2 / 3
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
        input_per_call = simulation_tokens_per_agent_step(
            max_rounds, memory_context_cap_tokens
        )
        modelled_tokens_per_call = input_per_call + _SIM_OUTPUT_TOKENS_PER_CALL
        tokens_per_call_low = modelled_tokens_per_call
        tokens_per_call_high = modelled_tokens_per_call
        input_share = input_per_call / modelled_tokens_per_call
        if memory_context_cap_tokens is None:
            memory_note = (
                "Gedächtnis unbegrenzt angenommen: der Kontext wächst mit jeder Runde"
            )
        else:
            memory_note = (
                f"Gedächtnis auf {_fmt(memory_context_cap_tokens)} Kontext-Tokens begrenzt"
            )
        warnings.append(
            "Keine historischen Verbrauchsdaten — Tokenschätzung basiert auf einer "
            "Heuristik aus Messwerten (Lauf sim_cc6067a70603, 24 Runden, 52 Agenten, "
            "2 Plattformen; Mittel 33.700 Eingabe-Tokens je Aufruf). "
            f"{memory_note}; Schätzung ≈ {_fmt(input_per_call)} Eingabe-Tokens "
            "je Agentenschritt."
        )
    return tokens_per_call_low, tokens_per_call_high, input_share, warnings


def estimate_run(
    *,
    num_agents: int,
    max_rounds: int,
    models: Optional[list[PreflightModelRef]] = None,
    pricing: Optional[PricingRegistry] = None,
    history: Optional[_HistoryStats] = None,
    platforms: int = 2,
    memory_context_cap_tokens: Optional[int] = None,
    default_token_cap: Optional[int] = None,
) -> PreflightEstimate:
    """Preflight-Schätzung für einen Simulations-Run berechnen.

    ``platforms``: Zahl der Plattformen, auf denen jeder Agent handelt (Standard
    2 = Twitter+Reddit im Parallelrunner; 1 bei ``twitter_only``/``reddit_only``).
    ``memory_context_cap_tokens``: Kontext-Obergrenze bei begrenztem
    Agenten-Gedaechtnis; ``None`` (Standard) = unbegrenzt, Kontext waechst mit
    der Runde (siehe ``simulation_tokens_per_agent_step``).
    ``default_token_cap``: ein ggf. greifender Standard-Tokendeckel; liegt die
    untere Schaetzung darueber, steht eine Warnung in der Antwort.

    Annahme (kein Fehler): Der Budget-Zaehler ``budget_guard.record_call`` zaehlt
    nur ERFOLGREICHE Aufrufe. Mit ``RateLimitError`` gescheiterte Versuche
    verbrauchen real Eingabe-Tokens beim Anbieter, gehen aber nicht in die
    Tokensumme ein -- Schaetzung und Deckel beziehen sich auf erfolgreiche Aufrufe.
    """
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
    tokens_per_call_low, tokens_per_call_high, input_share, token_warnings = (
        _tokens_per_call_estimate(
            history,
            has_history=has_history,
            max_rounds=max_rounds,
            memory_context_cap_tokens=memory_context_cap_tokens,
        )
    )
    warnings.extend(token_warnings)
    warnings.append(
        "Der Budget-Zähler zählt nur erfolgreiche Modellaufrufe; mit "
        "RateLimitError gescheiterte Versuche verbrauchen beim Anbieter "
        "Eingabe-Tokens, erscheinen aber nicht in der Tokensumme."
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
    platform_count = max(1, int(platforms))
    calls_low = num_agents * platform_count * max_rounds * _ACTIVE_RATIO_LOW
    calls_high = num_agents * platform_count * max_rounds * _ACTIVE_RATIO_HIGH
    warnings.append(
        "LLM-Aufrufe pro Runde sind lastabhängig (Aktivierungsrate der "
        f"Agenten) — berechnet mit 30–100 % aktiven Agenten pro Runde auf "
        f"{platform_count} Plattform(en)."
    )

    tokens_low = _round_sig(calls_low * tokens_per_call_low)
    tokens_high = _round_sig(calls_high * tokens_per_call_high)

    duration_low = _round_sig(calls_low * latency_low / _CONCURRENCY)
    duration_high = _round_sig(calls_high * latency_high / _CONCURRENCY)

    # --- Kosten ---------------------------------------------------------------
    # Issue #764 (Review): jedes konfigurierte Modell trägt seinen eigenen
    # Token-Anteil — free Modelle mit 0, priced mit ihrem jeweiligen Tarif,
    # unknown mit "wir wissen es nicht" (cost_status="unknown"). Ohne
    # explizite Per-Modell-Gewichtung verteilen wir die geschätzten Tokens
    # gleichmäßig über alle Modelle (deterministisch, dokumentiert).
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
    else:
        priced = [q for q in quotes if q.status == "priced"]
        free = [q for q in quotes if q.status == "free"]
        unknown = [q for q in quotes if q.status == "unknown"]
        n_models = len(quotes)
        # Gleichverteilung der geschätzten Tokens: jedes Modell bekommt 1/n.
        share_low = 1.0 / n_models
        share_high = 1.0 / n_models

        def _sum_cost_contribution(
            priced_quotes: list[Any],
            share: float,
            tokens: int,
        ) -> int:
            """Summenbildung über die bepreisten Modelle mit gemeinsamem Anteil.

            Annahme: ``input_share`` Input (Standard 2/3, bei der Simulation aus
            dem Messwertmodell ~99,9 %), der Rest Output. Defensive
            Validierung statt ``assert``: ``assert`` wird unter ``python -O``
            wegoptimiert, und die PricingRegistry-Quotes können theoretisch
            halbierte Felder liefern. Fehlende Preise fuehren zu ``0`` (kein
            erfundener Beitrag), was der Aufrufer bereits durch das Filtern
            auf ``status == "priced"`` ausschliesst — wenn doch, ist das ein
            Datenmodell-Bug, kein Preflight-Fehler.
            """
            total = 0
            for q in priced_quotes:
                in_mtok = q.input_per_mtok_micros
                out_mtok = q.output_per_mtok_micros
                if not isinstance(in_mtok, (int, float)) or not isinstance(out_mtok, (int, float)):
                    continue
                blended = input_share * in_mtok + (1 - input_share) * out_mtok
                total += int(round(tokens * share * blended / 1_000_000))
            return total

        if not unknown:
            # Alle Preise bekannt: free-Modelle tragen 0, priced-Modelle
            # tragen ihren Tarif × ihren Anteil.
            cost_micros_low = _sum_cost_contribution(priced, share_low, tokens_low)
            cost_micros_high = _sum_cost_contribution(priced, share_high, tokens_high)
            if free and not priced:
                cost_status = "free"
            else:
                cost_status = "estimated"
                warnings.append(
                    f"Kosten basieren auf statischen Richtpreisen "
                    f"(Version {pricing.pricing_version}) — keine Preisgarantie."
                )
        elif priced or free:
            # Mindestens ein Modell ohne bekannten Preis. Wir können den
            # Anteil der bepreisten/free Modelle ehrlich ausweisen, aber
            # nicht sagen, wie viel auf die unbekannten Modelle entfällt —
            # daher "estimated" mit der bekannten Teilsumme und Warnung.
            cost_micros_low = _sum_cost_contribution(priced, share_low, tokens_low)
            cost_micros_high = _sum_cost_contribution(priced, share_high, tokens_high)
            cost_status = "estimated"
            warnings.append(
                "Für mindestens ein Modell liegt kein Richtpreis vor — "
                "Kosten nur als Teilsumme aus bepreisten Modellen ausgewiesen."
            )
        else:
            # Nur unbekannte Preise — keine Aussage möglich.
            cost_status = "unknown"
            cost_micros_low = None
            cost_micros_high = None
            warnings.append(
                "Für mindestens ein Modell liegt kein Richtpreis vor — "
                "Kosten unbekannt (nicht 0)."
            )

    if default_token_cap is not None and tokens_low > default_token_cap:
        warnings.append(
            f"Der Standard-Tokendeckel von {_fmt(default_token_cap)} würde diesen "
            f"Lauf voraussichtlich abbrechen (untere Schätzung {_fmt(tokens_low)}); "
            "ohne begrenztes Gedächtnis oder einen höheren Deckel endet er mit "
            "budget_tokens."
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
