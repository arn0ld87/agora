"""
Run Usage Ledger (Issue #764).

Aggregiert den tatsächlichen Verbrauch eines Runs aus den strukturierten
LLM-Call-Events (``instance/runs/<run_id>/llm_call_events.jsonl``) zu einem
``RunUsage``-Vertrag: gesamt, pro Stage, pro Provider, pro Modell.

Ehrlichkeitsregeln:
  - Events ohne Token-Usage führen zu tokens_status=partial/unknown, nie zu 0.
  - Kosten werden nur aus gemessenen Tokens + versionierter Preistabelle
    berechnet; unbekannte Preise bleiben unknown.
  - Lokale Modelle werden als free (0 Micros, ehrlich bepreist) geführt.
  - Fehlerhafte oder alte Event-Zeilen (ohne Token-Felder, Schema v0) werden
    tolerant gelesen und als unknown gewertet.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Iterable, Optional

from app.contracts.run_budget_contract import RunUsage, UsageMetrics
from app.services.pricing_registry import PricingRegistry, get_pricing_registry
from app.utils.artifact_locator import ArtifactLocator

EVENTS_FILENAME = "llm_call_events.jsonl"
USAGE_SUMMARY_FILENAME = "usage_summary.json"


def _events_path(run_id: str) -> str:
    return os.path.join(ArtifactLocator.run_dir(run_id), EVENTS_FILENAME)


def load_call_events(run_id: str) -> list[dict[str, Any]]:
    """JSONL-Events tolerant lesen (korrupte Zeilen werden übersprungen)."""
    path = _events_path(run_id)
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except FileNotFoundError:
        return []
    return events


class _Bucket:
    """Mutable Akkumulation, die am Ende in ehrliche UsageMetrics überführt wird."""

    __slots__ = (
        "llm_calls",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "events_with_tokens",
        "events_without_tokens",
        "cost_micros_known",
        "saw_priced",
        "saw_free",
        "saw_unknown_price",
    )

    def __init__(self) -> None:
        self.llm_calls = 0
        self.duration_ms = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.events_with_tokens = 0
        self.events_without_tokens = 0
        self.cost_micros_known = 0
        self.saw_priced = False
        self.saw_free = False
        self.saw_unknown_price = False

    def add(self, event: dict[str, Any], pricing: PricingRegistry) -> None:
        if event.get("success"):
            self.llm_calls += 1
        latency = event.get("latency_ms")
        if isinstance(latency, (int, float)):
            self.duration_ms += int(latency)

        prompt = event.get("prompt_tokens")
        completion = event.get("completion_tokens")
        has_tokens = isinstance(prompt, int) or isinstance(completion, int)
        if has_tokens:
            self.events_with_tokens += 1
            self.input_tokens += prompt if isinstance(prompt, int) else 0
            self.output_tokens += completion if isinstance(completion, int) else 0
        else:
            self.events_without_tokens += 1

        quote = pricing.resolve(
            event.get("provider_id"),
            event.get("model"),
            event.get("base_url_sanitized"),
        )
        if quote.status == "free":
            self.saw_free = True
        elif quote.status == "priced":
            self.saw_priced = True
            if has_tokens:
                cost = quote.cost_micros(self.input_tokens_delta(prompt), self.output_tokens_delta(completion))
                if cost is not None:
                    self.cost_micros_known += cost
        else:
            self.saw_unknown_price = True

    @staticmethod
    def input_tokens_delta(prompt: Any) -> int:
        return prompt if isinstance(prompt, int) else 0

    @staticmethod
    def output_tokens_delta(completion: Any) -> int:
        return completion if isinstance(completion, int) else 0

    def to_metrics(self) -> UsageMetrics:
        # --- tokens_status -----------------------------------------------------
        # "measured" nur, wenn mindestens ein Event Tokens geliefert hat UND
        # kein Event ohne Tokens daneben liegt. "partial" = gemischte Daten,
        # "unknown" = gar keine Token-Daten.
        tokens_status = "unknown"
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None
        total_tokens: Optional[int] = None
        if self.events_with_tokens > 0:
            input_tokens = self.input_tokens
            output_tokens = self.output_tokens
            total_tokens = self.input_tokens + self.output_tokens
            tokens_status = "measured" if self.events_without_tokens == 0 else "partial"

        tokens_complete = tokens_status == "measured"

        # --- cost_status -------------------------------------------------------
        # Ehrliche Aggregationsregeln (Issue #764):
        #   * "measured"  → alle relevanten Events haben bekannte Preise UND
        #                   vollständige Token-Usage. cost_micros ist die
        #                   belastbare Gesamtsumme.
        #   * "free"      → alle Events sind kostenfrei UND Token-Usage
        #                   vollständig (sonst wäre die Aussage irreführend).
        #   * "estimated" → bekannte Teilsumme aus bepreisten Events, aber
        #                   entweder Tokenwerte teilweise fehlend oder ein
        #                   Anteil hat unbekannten Preis.
        #   * "unknown"   → keine sinnvolle Kostenaussage möglich. cost_micros
        #                   bleibt None — wir geben nie eine erfundene 0 aus.
        cost_status = "unknown"
        cost_micros: Optional[int] = None
        if not (self.saw_priced or self.saw_free):
            # Kein Event hat einen bekannten Preis → keine Aussage möglich.
            cost_status = "unknown"
            cost_micros = None
        elif self.saw_unknown_price:
            # Mindestens ein Event ohne bekannten Preis: nur die bepreisten/
            # kostenlosen Anteile können wir ehrlich ausweisen, der Rest ist
            # eine Annahme → "estimated".
            cost_status = "estimated"
            cost_micros = self.cost_micros_known
        elif tokens_complete:
            # Alle Events bepreist/free, vollständige Token-Usage — belastbare
            # Gesamtsumme (free-Events tragen 0 Micros bei).
            cost_status = "measured" if self.saw_priced else "free"
            cost_micros = self.cost_micros_known
        else:
            # Alle Preise bekannt, aber Token-Daten teilweise unvollständig —
            # wir wissen nicht, was die fehlenden Tokens gekostet hätten. Die
            # bekannte Teilsumme ehrlich als "estimated" ausweisen.
            cost_status = "estimated"
            cost_micros = self.cost_micros_known

        return UsageMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            llm_calls=self.llm_calls,
            cost_micros=cost_micros,
            cost_status=cost_status,  # type: ignore[arg-type]
            tokens_status=tokens_status,  # type: ignore[arg-type]
            duration_ms=self.duration_ms,
        )


def aggregate_usage(
    run_id: str,
    events: Optional[Iterable[dict[str, Any]]] = None,
    pricing: Optional[PricingRegistry] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> RunUsage:
    """Events eines Runs zu RunUsage aggregieren (totals + Breakdowns)."""
    pricing = pricing or get_pricing_registry()
    event_list = list(events) if events is not None else load_call_events(run_id)

    totals = _Bucket()
    by_stage: dict[str, _Bucket] = {}
    by_provider: dict[str, _Bucket] = {}
    by_model: dict[str, _Bucket] = {}

    for event in event_list:
        totals.add(event, pricing)
        for index, key in (
            (by_stage, str(event.get("stage") or "unknown")),
            (by_provider, str(event.get("provider_id") or "unknown")),
            (by_model, str(event.get("model") or "unknown")),
        ):
            bucket = index.get(key)
            if bucket is None:
                bucket = _Bucket()
                index[key] = bucket
            bucket.add(event, pricing)

    if not event_list:
        measurement_status = "unknown"
    elif totals.events_without_tokens > 0:
        measurement_status = "partial"
    else:
        measurement_status = "complete"

    return RunUsage(
        totals=totals.to_metrics(),
        by_stage={key: bucket.to_metrics() for key, bucket in sorted(by_stage.items())},
        by_provider={key: bucket.to_metrics() for key, bucket in sorted(by_provider.items())},
        by_model={key: bucket.to_metrics() for key, bucket in sorted(by_model.items())},
        started_at=started_at,
        ended_at=ended_at,
        measurement_status=measurement_status,  # type: ignore[arg-type]
        pricing_version=pricing.pricing_version,
        pricing_source=pricing.pricing_source,
    )


def usage_summary_path(run_id: str) -> str:
    return os.path.join(ArtifactLocator.run_dir(run_id), USAGE_SUMMARY_FILENAME)


def persist_usage_summary(
    run_id: str,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> RunUsage:
    """Abschluss-Snapshot des Verbrauchs als usage_summary.json persistieren.

    Wird am Run-Ende aufgerufen; der Snapshot dient späteren Preflight-
    Schätzungen als historische Datenbasis.
    """
    usage = aggregate_usage(run_id, started_at=started_at, ended_at=ended_at)
    path = usage_summary_path(run_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(usage.model_dump_json(indent=2))
        handle.write("\n")
    os.replace(tmp_path, path)
    return usage


def load_usage_summary(run_id: str) -> Optional[RunUsage]:
    """Persistierten Abschluss-Snapshot lesen (None wenn nicht vorhanden)."""
    path = usage_summary_path(run_id)
    try:
        with open(path, encoding="utf-8") as handle:
            return RunUsage.model_validate(json.load(handle))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


# --- Mtime-basierter Read-Cache (Budget-Checks laufen pro LLM-Call) ---------

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def load_call_events_cached(run_id: str) -> list[dict[str, Any]]:
    """Wie load_call_events, aber mit mtime-Cache pro run_id."""
    path = _events_path(run_id)
    try:
        mtime = os.path.getmtime(path)
    except FileNotFoundError:
        return []
    with _cache_lock:
        cached = _cache.get(run_id)
        if cached and cached[0] == mtime:
            return cached[1]
    events = load_call_events(run_id)
    with _cache_lock:
        _cache[run_id] = (mtime, events)
    return events


def reset_usage_cache() -> None:
    """Test-Hook: Cache leeren."""
    with _cache_lock:
        _cache.clear()
