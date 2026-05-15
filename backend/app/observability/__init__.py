"""Observability bootstrap — OpenTelemetry Tracing + Metrics + Logs.

Slice 1b (2026-05-15): TracerProvider + OTLP-Span-Exporter.
Slice 2a (2026-05-15): MeterProvider + OTLP-Metric-Exporter, fünf Instrument-Factories.
Slice 3a (2026-05-15): LoggerProvider + LoggingInstrumentor + JsonTraceFormatter.

Tracing:  ``OTEL_ENABLED=true`` aktiviert Spans.
Metrics:  ``OTEL_METRICS_ENABLED=true`` aktiviert Metrics.
Logs:     ``OTEL_LOGS_ENABLED=true`` aktiviert Log-Korrelation.
Alle Default-Off — kein Overhead solange die Env-Vars fehlen oder ``false`` sind.
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
from .logging_bridge import init_logging, force_flush_logs, JsonTraceFormatter

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
    # Logs
    "init_logging",
    "force_flush_logs",
    "JsonTraceFormatter",
]
