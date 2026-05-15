"""Custom Trace-Propagator für Redis-pub/sub Bus-Events.

Slice 1d (2026-05-15). Redis-pub/sub-Payloads sind JSON-Dicts; OTel hat
keinen Standard-Propagator dafür. Wir mergen ``traceparent`` als reserviertes
Feld ``_otel_traceparent`` in das Event-Dict.

Typischer Einsatz
-----------------
Publisher (Subprocess-Seite, ``subprocess_redis_bridge.py``)::

    event_dict = inject_trace_into_event(event_dict)
    await redis.publish(channel, json.dumps(event_dict))

Consumer (Flask-Seite, ``event_bus_redis.py``)::

    data = json.loads(msg["data"])
    ctx = extract_trace_from_event(data)
    with tracer.start_as_current_span("agora.bus.event.consume", context=ctx):
        ...
"""

from __future__ import annotations

from typing import Any, Dict

from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_PROPAGATOR = TraceContextTextMapPropagator()
_FIELD = "_otel_traceparent"


def inject_trace_into_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Injiziert den aktuellen Trace-Context als ``_otel_traceparent``-Feld.

    Mutiert das übergebene Dict und gibt es zurück. Wenn kein aktiver Span
    vorliegt (NoOpTracer), wird das Dict unverändert zurückgegeben.
    """
    carrier: Dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    if "traceparent" in carrier:
        event[_FIELD] = carrier["traceparent"]
    return event


def extract_trace_from_event(event: Dict[str, Any]) -> otel_context.Context:
    """Extrahiert den Trace-Context aus einem Event-Dict.

    Gibt bei fehlendem oder ungültigem ``_otel_traceparent`` einen leeren
    Context zurück — kein Crash, kein Fallback auf einen falschen Trace.
    """
    traceparent = event.get(_FIELD)
    if not traceparent:
        return otel_context.Context()
    return _PROPAGATOR.extract({"traceparent": traceparent})


__all__ = ["inject_trace_into_event", "extract_trace_from_event"]
