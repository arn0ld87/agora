"""Tests für app.observability.logging_bridge (Slice 3a Foundation).

TDD-Spec: LoggerProvider initialisiert gegated über OTEL_LOGS_ENABLED;
JsonTraceFormatter erzeugt JSON-Zeilen mit Trace-Korrelation;
force_flush_logs NoOp ohne Provider.

Fixture-Strategie (analog Slice 2a):
  Modul-Level-Cache (_provider / _lock) wird via Monkeypatch zurückgesetzt.
  Teardown ruft provider.shutdown() auf, sobald ein echter LoggerProvider
  im Cache liegt — verhindert Background-Thread-Leak (Audit-Finding Slice 2a).
"""

from __future__ import annotations

import json
import logging
import threading

import pytest
from opentelemetry.sdk._logs import LoggerProvider

import app.observability.logging_bridge as bridge_module
from app.observability import init_logging, force_flush_logs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_bridge_module_cache(monkeypatch):
    """Setzt den Modul-Cache vor jedem Test zurück.

    Teardown ruft provider.shutdown() auf, sobald ein echter LoggerProvider
    im Cache liegt, um Background-Thread-Leak zu verhindern.
    """
    monkeypatch.setattr(bridge_module, "_provider", None)
    monkeypatch.setattr(bridge_module, "_lock", threading.Lock())
    yield
    provider = bridge_module._provider
    if isinstance(provider, LoggerProvider):
        provider.shutdown()
    bridge_module._provider = None


# ---------------------------------------------------------------------------
# Case 1: Default-Off ohne Env-Var
# ---------------------------------------------------------------------------


def test_default_off_no_provider(monkeypatch):
    """OTEL_LOGS_ENABLED unset → init_logging triggert LoggerProvider nicht.

    Der Modul-Cache bleibt None; kein StreamHandler am Root-Logger.
    """
    monkeypatch.delenv("OTEL_LOGS_ENABLED", raising=False)
    root_before = len(logging.getLogger().handlers)

    init_logging("agora-test")

    assert bridge_module._provider is None
    # Kein zusätzlicher StreamHandler durch init_logging
    assert len(logging.getLogger().handlers) == root_before


# ---------------------------------------------------------------------------
# Case 2: Default-Off mit explizitem false
# ---------------------------------------------------------------------------


def test_default_false_no_provider(monkeypatch):
    """OTEL_LOGS_ENABLED=false → identisches Verhalten wie unset."""
    monkeypatch.setenv("OTEL_LOGS_ENABLED", "false")

    init_logging("agora-test")

    assert bridge_module._provider is None


# ---------------------------------------------------------------------------
# Case 3: Enabled — Provider wird initialisiert
# ---------------------------------------------------------------------------


def test_enabled_initializes_provider(monkeypatch):
    """OTEL_LOGS_ENABLED=true → init_logging registriert LoggerProvider."""
    monkeypatch.setenv("OTEL_LOGS_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

    init_logging("agora-test")

    assert bridge_module._provider is not None
    assert isinstance(bridge_module._provider, LoggerProvider)


# ---------------------------------------------------------------------------
# Case 4: Idempotenz — zweiter Aufruf liefert denselben Provider
# ---------------------------------------------------------------------------


def test_module_cache_idempotent(monkeypatch):
    """Zweimaliger Aufruf von init_logging → identische Provider-Instanz."""
    monkeypatch.setenv("OTEL_LOGS_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

    init_logging("agora-test")
    p1 = bridge_module._provider

    init_logging("agora-test")
    p2 = bridge_module._provider

    assert p1 is p2


# ---------------------------------------------------------------------------
# Case 5: JsonTraceFormatter — Trace-ID im aktiven Span
# ---------------------------------------------------------------------------


def test_json_formatter_outputs_trace_id_in_span_context():
    """JsonTraceFormatter liest otelTraceID/otelSpanID aus LogRecord-Attributen.

    Innerhalb eines aktiven Spans werden trace_id und span_id als nicht-leere
    Strings in das JSON-Payload eingebettet.
    """
    from opentelemetry.sdk.trace import TracerProvider

    tracer_provider = TracerProvider()
    tracer = tracer_provider.get_tracer("test")

    formatter = bridge_module.JsonTraceFormatter(service_name="agora-test")

    captured: list[logging.LogRecord] = []

    class CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    logger = logging.getLogger("test_span_context")
    handler = CapturingHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        with tracer.start_as_current_span("test-span"):
            # LoggingInstrumentor patcht root-Logger; hier simulieren wir
            # das Attribut-Injection manuell, um keine echte Instrumentation
            # im Isolations-Test zu brauchen.
            logger.info("hello from span")

        assert len(captured) == 1
        record = captured[0]

        # Hole aktiven Span-Context zum Zeitpunkt des Loggings aus dem with-Block
        # → nutze TracerProvider, um trace_id/span_id direkt einzufügen
        with tracer.start_as_current_span("test-span-2") as active_span:
            active_ctx = active_span.get_span_context()
            record.otelTraceID = format(active_ctx.trace_id, "032x")  # type: ignore[attr-defined]
            record.otelSpanID = format(active_ctx.span_id, "016x")  # type: ignore[attr-defined]

        formatted = formatter.format(record)
        payload = json.loads(formatted)

        assert payload["trace_id"] != ""
        assert payload["span_id"] != ""
        assert payload["service.name"] == "agora-test"
        assert payload["message"] == "hello from span"
        assert "timestamp" in payload
        assert "level" in payload
    finally:
        logger.removeHandler(handler)
        tracer_provider.shutdown()


# ---------------------------------------------------------------------------
# Case 6: JsonTraceFormatter — leere Trace-IDs ohne Span
# ---------------------------------------------------------------------------


def test_json_formatter_no_span_empty_trace_id():
    """JsonTraceFormatter ohne aktiven Span: trace_id und span_id sind leere Strings."""
    formatter = bridge_module.JsonTraceFormatter(service_name="agora-test")

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="no span here",
        args=(),
        exc_info=None,
    )
    # Keine otelTraceID / otelSpanID Attribute gesetzt

    formatted = formatter.format(record)
    payload = json.loads(formatted)

    assert payload["trace_id"] == ""
    assert payload["span_id"] == ""
    assert payload["message"] == "no span here"
    assert payload["service.name"] == "agora-test"


# ---------------------------------------------------------------------------
# Case 7: force_flush_logs NoOp ohne init
# ---------------------------------------------------------------------------


def test_force_flush_logs_noop_when_disabled():
    """force_flush_logs() ohne vorheriges init_logging() wirft nicht."""
    # _reset_bridge_module_cache sorgt dafür dass _provider=None
    result = force_flush_logs()
    assert result is None
