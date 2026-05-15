"""OpenTelemetry Tracing Bootstrap für Agora.

Slice 1b (2026-05-15): Initialisiert TracerProvider + OTLP-Exporter.
Auto-Instrumentation für Flask/requests/redis wird aktiviert, sobald
``OTEL_ENABLED=true`` gesetzt ist. Default-Off — kein Overhead solange
die Env-Var fehlt oder ``false`` ist.

gevent-Kompatibilität: ``gevent.monkey.patch_all()`` muss VOR dem ersten
Import dieses Moduls gelaufen sein (üblicherweise in ``wsgi.py`` oder
ganz oben in der Import-Kette des Gunicorn-Workers). OTel-gRPC-Exporter
nutzt threading, das unter gevent transparent gepatchted ist.
"""

from __future__ import annotations

import os
from typing import List, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Modul-Level-Cache für Idempotenz: mehrfache create_app()-Aufrufe (z. B.
# in Tests) initialisieren den Provider nur einmal.
_PROVIDER: Optional[TracerProvider] = None


def init_tracing(
    service_name: str,
    *,
    extra_processors: Optional[List[SpanProcessor]] = None,
) -> Optional[TracerProvider]:
    """Setup TracerProvider, OTLP-Exporter und Auto-Instrumentation.

    Idempotent: Mehrfachaufrufe geben den existierenden Provider zurück.
    NoOp wenn ``OTEL_ENABLED`` != "true" — gibt ``None`` zurück.

    Args:
        service_name: OTel ``service.name``-Resource-Attribut.
        extra_processors: Zusätzliche SpanProzessoren (z. B. InMemorySpanExporter
            in Tests). Werden nach dem BatchSpanProcessor registriert.

    Returns:
        Der konfigurierte ``TracerProvider`` oder ``None`` wenn OTel deaktiviert.
    """
    global _PROVIDER  # noqa: PLW0603
    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        return None
    if _PROVIDER is not None:
        return _PROVIDER

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    for processor in extra_processors or []:
        provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)
    _PROVIDER = provider

    # Auto-Instrumentation.
    # Flask wird per App-Instanz in instrument_flask_app() aktiviert, da
    # FlaskInstrumentor.instrument_app(app) die WSGI-App braucht.
    # requests + redis können global instrumentiert werden.
    RequestsInstrumentor().instrument()
    RedisInstrumentor().instrument()

    return provider


def instrument_flask_app(app: object) -> None:
    """Aktiviert Flask-Auto-Instrumentation für eine konkrete App-Instanz.

    Wrapper, damit die App-Factory keine OTel-API direkt importieren muss.
    NoOp wenn ``init_tracing()`` noch nicht aufgerufen wurde oder deaktiviert ist.
    """
    if _PROVIDER is None:
        return
    FlaskInstrumentor().instrument_app(app)  # type: ignore[no-untyped-call]
