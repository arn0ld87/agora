"""Observability bootstrap — OpenTelemetry Tracing.

Slice 1b (2026-05-15): Initialisiert TracerProvider + OTLP-Exporter.
Auto-Instrumentation für Flask/requests/redis wird in `tracing.init_tracing`
aktiviert, sobald `OTEL_ENABLED=true` ist.
"""

from .tracing import init_tracing, instrument_flask_app

__all__ = ["init_tracing", "instrument_flask_app"]
