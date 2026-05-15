"""OpenTelemetry Logs-Bridge für Agora.

Slice 3a (2026-05-15): Initialisiert LoggerProvider + LoggingInstrumentor,
der OTel-Trace-Kontext (trace_id, span_id) in jeden Python-LogRecord injiziert.

Default-Off — ohne ``OTEL_LOGS_ENABLED=true`` werden keinerlei Provider
registriert und der bestehende ``app.logger``-Pfad bleibt unverändert.

gevent-Kompatibilität: Gleiche Anforderung wie in ``tracing.py`` und
``metrics.py`` — ``gevent.monkey.patch_all()`` muss VOR dem ersten Import
dieses Moduls gelaufen sein.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Optional

# opentelemetry.sdk.logs (ohne Underscore) existiert nicht; sdk._logs ist der
# kanonische Importpfad auf SDK 1.41.1 — kommunale Praxis bis Logs-API stabil ist.
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

# Modul-Level-Cache — Idempotenz bei mehrfachen create_app()-Aufrufen (z. B. Tests).
_provider: Optional[LoggerProvider] = None
_lock: threading.Lock = threading.Lock()


def init_logging(service_name: str) -> None:
    """Initialisiert LoggerProvider + LoggingInstrumentor gegated über OTEL_LOGS_ENABLED.

    Bei Default (env unset oder 'false'): NoOp, kein LoggerProvider. Der
    bestehende ``app.logger``-Pfad bleibt vollständig unverändert.

    Bei 'true':
      1. LoggerProvider mit BatchLogRecordProcessor + OTLPLogExporter (gRPC) registrieren.
      2. LoggingInstrumentor().instrument(set_logging_format=False) — eigener
         Formatter hat Vorrang.
      3. Root-Logger bekommt zusätzlich einen StreamHandler mit JsonTraceFormatter
         (stdout, JSON-Zeilen).
      4. Modul-Cache: idempotenter zweiter Aufruf liefert denselben Provider.

    Args:
        service_name: OTel ``service.name``-Resource-Attribut.
    """
    global _provider  # noqa: PLW0603

    if os.environ.get("OTEL_LOGS_ENABLED", "false").lower() != "true":
        return

    with _lock:
        if _provider is not None:
            return

        # Spät-Import um Startup-Overhead bei Default-Off zu vermeiden.
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
            OTLPLogExporter,
        )
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

        resource = Resource.create({"service.name": service_name})
        exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
        processor = BatchLogRecordProcessor(exporter)
        provider = LoggerProvider(resource=resource)
        provider.add_log_record_processor(processor)
        set_logger_provider(provider)
        _provider = provider

        # Patcht Root-Logger: jeder LogRecord bekommt otelTraceID, otelSpanID,
        # otelServiceName und otelTraceSampled als Attribute.
        LoggingInstrumentor().instrument(set_logging_format=False)

        # Zusätzlicher StreamHandler mit JSON-Trace-Formatter auf stdout.
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonTraceFormatter(service_name=service_name))
        # Ensure we don't add multiple JSON handlers to the root logger to avoid duplication and leaks.
        root_logger = logging.getLogger()
        if not any(isinstance(h.formatter, JsonTraceFormatter) for h in root_logger.handlers):
            root_logger.addHandler(handler)


def force_flush_logs(timeout_millis: int = 5000) -> None:
    """Erzwingt Export gepufferter Logs. Pflicht in Runner-Subprozessen vor Exit.

    NoOp wenn init_logging() noch nicht aufgerufen wurde oder
    OTEL_LOGS_ENABLED != "true" war.

    Args:
        timeout_millis: Maximale Wartezeit für den Export in Millisekunden.
    """
    if _provider is None:
        return
    _provider.force_flush(timeout_millis)


class JsonTraceFormatter(logging.Formatter):
    """JSON-Formatter mit Trace-Korrelation. Ein LogRecord pro JSON-Zeile.

    Felder: timestamp (ISO-8601), level, logger, message, trace_id, span_id,
    service.name. trace_id und span_id werden aus LogRecord-Attributen gelesen,
    die LoggingInstrumentor injiziert (otelTraceID, otelSpanID).
    Wenn kein aktiver Span: Felder sind leere Strings.

    Exception-Info wird als ``exception``-Feld im JSON-Payload kodiert,
    wenn im LogRecord vorhanden.
    """

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "otelTraceID", "") or ""
        span_id = getattr(record, "otelSpanID", "") or ""
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
            "service.name": self._service_name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
