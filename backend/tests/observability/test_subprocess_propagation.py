"""Slice 1c: TRACEPARENT-Roundtrip durch subprocess.Popen-Boundary.

Verifikation: Ein Parent-Span im Test-Process setzt TRACEPARENT als ENV-Var.
Ein Child-Prozess extrahiert den Trace-Context und gibt die Trace-ID aus.
Die Trace-ID muss identisch sein — d.h. der Subprocess-Hop erhält den Context.

Isolation: Der Test nutzt einen lokalen TracerProvider ohne
``trace.set_tracer_provider()`` zu rufen, um den globalen OTel-Zustand
nicht zu mutieren. Das Subprocess-Child parst TRACEPARENT direkt
(string-split), ohne OTel-SDK-Imports zu benötigen.
"""
import subprocess
import sys

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def test_traceparent_propagates_via_env(tmp_path):
    # Lokaler Provider — kein set_tracer_provider(), globaler Zustand bleibt unberührt.
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("parent") as parent:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        traceparent = carrier["traceparent"]
        parent_trace_id = format(parent.get_span_context().trace_id, "032x")

    # Child-Prozess extrahiert die Trace-ID direkt aus dem traceparent-String:
    # Format: 00-<trace-id>-<span-id>-<flags>
    script = tmp_path / "child.py"
    script.write_text(
        "import os\n"
        "tp = os.environ['TRACEPARENT']\n"
        "parts = tp.split('-')\n"
        "print(parts[1])\n"
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        env={"TRACEPARENT": traceparent, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == parent_trace_id
