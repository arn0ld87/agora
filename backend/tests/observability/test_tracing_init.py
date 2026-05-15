"""Tests für app.observability.init_tracing (Slice 1b).

TDD-Spec: TracerProvider liefert Spans an konfigurierten Exporter;
NoOp wenn OTEL_ENABLED != "true".
"""

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from app.observability import init_tracing


def test_init_tracing_emits_spans_to_configured_exporter(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "true")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "agora-test")
    exporter = InMemorySpanExporter()
    provider = init_tracing("agora-test", extra_processors=[SimpleSpanProcessor(exporter)])

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("unit-span"):
        pass

    provider.force_flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "unit-span"
    assert spans[0].resource.attributes["service.name"] == "agora-test"


def test_init_tracing_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_ENABLED", "false")
    provider = init_tracing("agora-test", extra_processors=[])
    assert provider is None
