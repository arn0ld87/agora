"""OpenTelemetry Metrics-Bootstrap für Agora.

Slice 2a (2026-05-15): Initialisiert MeterProvider + OTLP-Exporter.
Fünf Factory-Funktionen liefern Instruments (Counter, Histogram,
UpDownCounter) für die zentralen Lauf-/Bus-/LLM-Messpunkte.

Default-Off — ohne ``OTEL_METRICS_ENABLED=true`` werden keinerlei
Provider registriert und keine Netzwerk-Verbindungen aufgebaut. Alle
Factory-Funktionen bleiben aufrufbar und liefern NoOp-Instruments.

Cardinality-Guard: Fünf OTel-Views erzwingen eine Attribut-Whitelist
pro Instrument. Hochkardinalitäre Labels (``simulation_id``, ``user_id``,
``run_id``) werden niemals an den Exporter weitergeleitet.

gevent-Kompatibilität: identische Anforderung wie in ``tracing.py`` —
``gevent.monkey.patch_all()`` muss VOR dem ersten Import dieses Moduls
gelaufen sein.
"""

from __future__ import annotations

import os
import threading
from typing import List, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource

# Modul-Level-Cache — Idempotenz bei mehrfachen create_app()-Aufrufen (z. B. Tests).
_provider: Optional[MeterProvider] = None
_meter: Optional[metrics.Meter] = None
_lock: threading.Lock = threading.Lock()

# Name des globalen Meters (zur internen Instrument-Erstellung).
_METER_NAME = "agora"

# Sim-Laufzeiten reichen von wenigen Sekunden (Smoke) bis ~30 Minuten (Voll-Sim).
# Feinere Standard-Buckets wären nutzlos — explizite Grenzen in Sekunden.
_SIM_DURATION_BOUNDARIES = [1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800]


def _build_views() -> List[View]:
    """Erstellt die View-Whitelist für alle fünf Agora-Instruments.

    Hochkardinalitäre Attribute (simulation_id, user_id, run_id) werden
    durch ``attribute_keys``-Restriktion nicht weitergeleitet. Die Views
    werden beim MeterProvider-Init registriert.

    Returns:
        Liste der View-Objekte (verbindlich für init_metrics + Testfixture).
    """
    return [
        View(
            instrument_name="agora.sim.started",
            attribute_keys={"status"},
        ),
        View(
            instrument_name="agora.sim.duration_seconds",
            attribute_keys={"status"},
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=_SIM_DURATION_BOUNDARIES,
            ),
        ),
        View(
            instrument_name="agora.sim.active",
            attribute_keys=set(),
        ),
        View(
            instrument_name="agora.bus.events.dropped",
            attribute_keys={"reason"},
        ),
        View(
            instrument_name="agora.llm.tokens",
            attribute_keys={"provider", "model", "direction"},
        ),
    ]


def init_metrics(service_name: str) -> None:
    """Initialisiert MeterProvider gegated über OTEL_METRICS_ENABLED.

    Bei Default (env unset oder 'false'): NoOp, kein Provider, keine
    Netzwerk-Aufrufe. Bei 'true': MeterProvider mit
    PeriodicExportingMetricReader + OTLPMetricExporter (gRPC).

    Idempotent: zweiter Aufruf mit beliebigem service_name ist ein NoOp,
    der bestehende Provider aus dem Modul-Cache bleibt aktiv.

    Args:
        service_name: OTel ``service.name``-Resource-Attribut.
    """
    global _provider, _meter  # noqa: PLW0603

    if os.environ.get("OTEL_METRICS_ENABLED", "false").lower() != "true":
        return

    with _lock:
        if _provider is not None:
            return

        # Spät-Import um Startup-Overhead bei Default-Off zu vermeiden.
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
        interval_ms = int(
            os.environ.get("OTEL_METRIC_EXPORT_INTERVAL", "10000")
        )

        exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=interval_ms,
        )
        resource = Resource.create({"service.name": service_name})
        provider = MeterProvider(
            metric_readers=[reader],
            resource=resource,
            views=_build_views(),
            shutdown_on_exit=True,
        )
        metrics.set_meter_provider(provider)
        _provider = provider
        _meter = provider.get_meter(_METER_NAME)


def force_flush(timeout_millis: int = 5000) -> None:
    """Erzwingt Export gepufferter Metrics. Pflicht in Runner-Subprozessen vor Exit.

    NoOp wenn init_metrics() noch nicht aufgerufen wurde oder
    OTEL_METRICS_ENABLED != "true" war.

    Args:
        timeout_millis: Maximale Wartezeit für den Export in Millisekunden.
    """
    if _provider is None:
        return
    _provider.force_flush(timeout_millis=timeout_millis)


def _get_meter() -> metrics.Meter:
    """Gibt den Modul-Meter zurück. Lazy: holt bei fehlendem Cache-Meter
    den globalen OTel-Meter (NoOp wenn kein Provider registriert)."""
    if _meter is not None:
        return _meter
    return metrics.get_meter(_METER_NAME)


# ---------------------------------------------------------------------------
# Factory-Funktionen (lazy — kein Instrument-Lookup beim Modul-Import)
# ---------------------------------------------------------------------------


def sim_counter() -> metrics.Counter:
    """Counter für gestartete Sim-Läufe.

    Instrument: ``agora.sim.started`` (unit="1").
    Erlaubte Attribute: ``status``.
    """
    return _get_meter().create_counter(
        name="agora.sim.started",
        unit="1",
        description="Anzahl gestarteter Sim-Läufe.",
    )


def sim_duration_histogram() -> metrics.Histogram:
    """Histogram für Laufzeiten abgeschlossener Sim-Läufe.

    Instrument: ``agora.sim.duration_seconds`` (unit="s").
    Erlaubte Attribute: ``status``.
    Buckets: 1 s – 1800 s (Realbereich Agora-Läufe).
    """
    return _get_meter().create_histogram(
        name="agora.sim.duration_seconds",
        unit="s",
        description="Laufzeit abgeschlossener Sim-Läufe in Sekunden.",
    )


def sim_active_gauge() -> metrics.UpDownCounter:
    """UpDownCounter für aktive (laufende) Sim-Läufe.

    Instrument: ``agora.sim.active`` (unit="1").
    Keine Attribute (leere Whitelist — Cardinality-Guard).
    """
    return _get_meter().create_up_down_counter(
        name="agora.sim.active",
        unit="1",
        description="Anzahl aktuell laufender Sim-Läufe.",
    )


def bus_event_drop_counter() -> metrics.Counter:
    """Counter für verworfene Event-Bus-Ereignisse.

    Instrument: ``agora.bus.events.dropped`` (unit="1").
    Erlaubte Attribute: ``reason``.
    """
    return _get_meter().create_counter(
        name="agora.bus.events.dropped",
        unit="1",
        description="Anzahl verworfener Event-Bus-Ereignisse.",
    )


def llm_token_counter() -> metrics.Counter:
    """Counter für verarbeitete LLM-Tokens.

    Instrument: ``agora.llm.tokens`` (unit="1").
    Erlaubte Attribute: ``provider``, ``model``, ``direction``.
    """
    return _get_meter().create_counter(
        name="agora.llm.tokens",
        unit="1",
        description="Anzahl verarbeiteter LLM-Tokens.",
    )
