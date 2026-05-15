"""Tests für den Redis-pub/sub Trace-Propagator (Slice 1d)."""
from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.observability.redis_propagator import extract_trace_from_event, inject_trace_into_event


@pytest.fixture()
def isolated_tracer_provider():
    """Liefert einen isolierten TracerProvider ohne den globalen OTel-State zu mutieren."""
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Direkt den Provider nutzen, nicht trace.set_tracer_provider() aufrufen —
    # der globale Provider darf nur einmal gesetzt werden (OTel-Constraint).
    tracer = provider.get_tracer("test")
    return tracer, exporter, provider


def test_inject_extract_roundtrip(isolated_tracer_provider) -> None:
    """Trace-Context überlebt Inject → Extract Roundtrip über ein Event-Dict."""
    tracer, exporter, provider = isolated_tracer_provider

    with tracer.start_as_current_span("publisher") as parent:
        event: dict = {"type": "state", "simulation_id": "sim-1", "payload": {}}
        enriched = inject_trace_into_event(event)
        parent_trace_id = parent.get_span_context().trace_id

    ctx = extract_trace_from_event(enriched)
    with tracer.start_as_current_span("consumer", context=ctx) as child:
        assert child.get_span_context().trace_id == parent_trace_id


def test_extract_handles_missing_traceparent() -> None:
    """Kein Crash wenn das Event kein _otel_traceparent-Feld hat."""
    event: dict = {"type": "state", "simulation_id": "sim-1", "payload": {}}
    ctx = extract_trace_from_event(event)
    assert ctx is not None  # Fallback-Context, kein Crash
