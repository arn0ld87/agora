"""Observability bootstrap — OpenTelemetry Tracing + Metrics.

Slice 1b (2026-05-15): TracerProvider + OTLP-Span-Exporter.
Slice 2a (2026-05-15): MeterProvider + OTLP-Metric-Exporter, fünf Instrument-Factories.

Tracing:  ``OTEL_ENABLED=true`` aktiviert Spans.
Metrics:  ``OTEL_METRICS_ENABLED=true`` aktiviert Metrics.
Beide Default-Off — kein Overhead solange die Env-Vars fehlen oder ``false`` sind.
"""

from .tracing import init_tracing, instrument_flask_app
from .metrics import (
    init_metrics,
    force_flush,
    sim_counter,
    sim_duration_histogram,
    sim_active_gauge,
    bus_event_drop_counter,
    llm_token_counter,
)

__all__ = [
    # Tracing
    "init_tracing",
    "instrument_flask_app",
    # Metrics
    "init_metrics",
    "force_flush",
    "sim_counter",
    "sim_duration_histogram",
    "sim_active_gauge",
    "bus_event_drop_counter",
    "llm_token_counter",
]
