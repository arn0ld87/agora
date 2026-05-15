# Observability Slice 1 — End-to-End Tracing für Simulation-Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) oder `superpowers:executing-plans` zur Umsetzung. Steps nutzen Checkbox-Syntax (`- [ ]`) zum Tracking.

**Goal:** Einen einzelnen Trace produzieren, der den vollständigen Sim-Lifecycle von `POST /api/simulations` über `subprocess.Popen` und Redis-pub/sub bis zum SSE-Event im Browser als kausal verkettete Spans in SigNoz sichtbar macht.

**Architecture:** OpenTelemetry-SDK + Flask-Auto-Instrumentation propagiert W3C-TraceContext durch vier seltene Hops: (1) gevent-monkey-patched Flask, (2) `subprocess.Popen`-Boundary via Env-Var `TRACEPARENT`, (3) Redis-pub/sub via Custom-Field im Bus-Event-JSON, (4) SSE-Frame via zusätzliches `trace_id`-Feld. Spans gehen lokal an einen OTel-Collector (sidecar), der an SigNoz Community Edition (self-hosted, Docker-Compose) weiterleitet. Frontend nutzt `@opentelemetry/sdk-trace-web` für korrelierte Browser-Spans.

**Tech Stack:** Python: `opentelemetry-api/sdk`, `opentelemetry-instrumentation-flask/requests/redis`, `opentelemetry-exporter-otlp-proto-grpc`. Frontend: `@opentelemetry/api`, `@opentelemetry/sdk-trace-web`, `@opentelemetry/exporter-trace-otlp-http`. Infrastructure: SigNoz Community Edition (Apache 2.0), OTel-Collector v0.99+, ClickHouse (über SigNoz).

**Aufwand:** ~8–10 Tage über 6 atomic Sub-Slices.

---

## File Structure

### Neue Dateien
| Pfad | Verantwortung |
|---|---|
| `docker-compose.observability.yml` | SigNoz-Stack + OTel-Collector als isolierter Profile-Block |
| `deploy/observability/otel-collector.yaml` | OTel-Collector-Config: OTLP-grpc-Receiver, Batch-Processor, OTLP-Exporter zu SigNoz |
| `backend/app/observability/__init__.py` | Public API: `init_tracing(service_name)` |
| `backend/app/observability/tracing.py` | TracerProvider-Setup, OTLP-Exporter, Flask-/Requests-/Redis-Auto-Instrumentation |
| `backend/app/observability/redis_propagator.py` | Inject/Extract von `traceparent` in/aus Bus-Event-Dict |
| `backend/tests/observability/__init__.py` | Test-Package-Marker |
| `backend/tests/observability/test_tracing_init.py` | TracerProvider-Init + In-Memory-Span-Exporter |
| `backend/tests/observability/test_redis_propagator.py` | Inject/Extract-Roundtrip |
| `backend/tests/observability/test_subprocess_propagation.py` | TRACEPARENT-ENV-Roundtrip |
| `frontend/src/observability/tracing.ts` | Web-Tracer-Provider, OTLP-HTTP-Exporter, Browser-Spans |
| `frontend/tests/observability/tracing.spec.ts` | Vitest: Span-Lifecycle + Trace-ID-Korrelation |
| `docu/2026-05-15-observability-slice-1-worklog.md` | Arbeitsprotokoll nach Alex' Konvention |

### Modifizierte Dateien
| Pfad | Änderung |
|---|---|
| `backend/pyproject.toml` | OTel-Dependencies hinzufügen |
| `backend/app/__init__.py` | `init_tracing("agora-backend")` im App-Factory-Bootstrap |
| `backend/app/services/sim/process_manager.py` | `TRACEPARENT` als ENV in `subprocess.Popen`-Call mergen + Manual-Span um Spawn |
| `backend/scripts/_sim_common.py` | `init_tracing("agora-oasis-runner")` + `TraceContextTextMapPropagator().extract()` aus ENV |
| `backend/scripts/subprocess_redis_bridge.py` | Inject `traceparent` beim Publish, Extract beim Receive |
| `backend/app/api/simulation_stream.py` | Aktuellen Span-Context als `trace_id` ins SSE-Event-Frame mergen |
| `backend/app/api/simulation_lifecycle.py` | Manual-Span um POST-Handler (`agora.simulation.create`) |
| `frontend/package.json` | OTel-Web-Dependencies + dev-script |
| `frontend/src/main.ts` | `initFrontendTracing()` vor `createApp` |
| `frontend/src/composables/useEventStream.ts` | SSE-Event `trace_id` als Span-Link konsumieren |
| `frontend/src/api/stream.ts` | `trace_id`-Feld in `SseEventFrame`-Type ergänzen |
| `.env.example` | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, `OTEL_ENABLED` |

---

## Task 1 (Sub-Slice 1a): Foundation — SigNoz + OTel-Collector lokal

**Ziel:** `docker compose -f docker-compose.observability.yml up -d` startet SigNoz + Collector. Ein manueller HTTP-POST gegen den Collector erscheint in SigNoz-UI als Span. **Kein** Agora-Code wird verändert.

**Files:**
- Create: `docker-compose.observability.yml`
- Create: `deploy/observability/otel-collector.yaml`
- Create: `deploy/observability/README.md`
- Modify: `.env.example` (3 neue Variablen)

- [x] **Step 1: SigNoz-Compose-File anlegen**

`docker-compose.observability.yml` mit dem SigNoz-Community-Stack (clickhouse, zookeeper, query-service, frontend, alertmanager) plus separater OTel-Collector. Profile `observability` damit der Stack nicht zu Agora-Default-Compose dazukommt.

```yaml
name: agora-observability

services:
  signoz-clickhouse:
    image: clickhouse/clickhouse-server:24.1.2-alpine
    profiles: ["observability"]
    restart: unless-stopped
    volumes:
      - signoz-clickhouse-data:/var/lib/clickhouse
    ports:
      - "127.0.0.1:9000:9000"

  signoz-zookeeper:
    image: bitnami/zookeeper:3.7.1
    profiles: ["observability"]
    environment:
      ALLOW_ANONYMOUS_LOGIN: "yes"
    volumes:
      - signoz-zookeeper-data:/bitnami/zookeeper

  signoz-query-service:
    image: signoz/query-service:0.51.0
    profiles: ["observability"]
    depends_on: [signoz-clickhouse]
    environment:
      ClickHouseUrl: tcp://signoz-clickhouse:9000
      STORAGE: clickhouse
      ALERTMANAGER_API_PREFIX: http://signoz-alertmanager:9093/api/
      SIGNOZ_LOCAL_DB_PATH: /var/lib/signoz/signoz.db
    volumes:
      - signoz-query-data:/var/lib/signoz

  signoz-frontend:
    image: signoz/frontend:0.51.0
    profiles: ["observability"]
    depends_on: [signoz-query-service]
    ports:
      - "127.0.0.1:3301:3301"

  signoz-alertmanager:
    image: signoz/alertmanager:0.23.7
    profiles: ["observability"]
    depends_on: [signoz-query-service]

  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.99.0
    profiles: ["observability"]
    depends_on: [signoz-clickhouse]
    volumes:
      - ./deploy/observability/otel-collector.yaml:/etc/otelcol-contrib/config.yaml:ro
    ports:
      - "127.0.0.1:4317:4317"  # OTLP grpc
      - "127.0.0.1:4318:4318"  # OTLP http
    command: ["--config=/etc/otelcol-contrib/config.yaml"]

volumes:
  signoz-clickhouse-data:
  signoz-zookeeper-data:
  signoz-query-data:
```

- [x] **Step 2: Collector-Config anlegen**

`deploy/observability/otel-collector.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins:
            - "http://localhost:5173"
            - "http://localhost:5001"

processors:
  batch:
    timeout: 1s
    send_batch_size: 1024
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  clickhousetraces:
    datasource: tcp://signoz-clickhouse:9000/?database=signoz_traces
    timeout: 10s
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [clickhousetraces, debug]
```

- [x] **Step 3: README für lokales Aufrufen**

`deploy/observability/README.md`:

```markdown
# Observability Stack (lokal)

SigNoz Community Edition + OTel-Collector als separater Compose-Stack.

## Start

    docker compose -f docker-compose.observability.yml --profile observability up -d

UI: http://localhost:3301
OTLP-grpc-Endpoint (für Agora-Backend + Frontend): localhost:4317 (grpc), localhost:4318 (http)

## Stop / Reset

    docker compose -f docker-compose.observability.yml --profile observability down
    docker compose -f docker-compose.observability.yml --profile observability down -v  # inkl. Daten
```

- [x] **Step 4: .env.example ergänzen**

```bash
# --- Observability (Slice 1) ---
OTEL_ENABLED=false
OTEL_SERVICE_NAME=agora-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

- [x] **Step 5: Smoke-Test**

Stack hochfahren, manueller Span via `telemetrygen`:

```bash
docker compose -f docker-compose.observability.yml --profile observability up -d
sleep 30
docker run --rm --network host ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest \
    traces --otlp-insecure --otlp-endpoint=localhost:4317 --traces=1 --duration=1s
```

Expected: SigNoz-UI (http://localhost:3301) zeigt unter „Services" einen Service `telemetrygen` mit einem Trace.

- [x] **Step 6: Commit** *(pending — kommt nach Gesamtslice)*

```bash
git add docker-compose.observability.yml deploy/observability/ .env.example
git commit -m "feat(observability): SigNoz + OTel-Collector als lokaler Compose-Stack (Slice 1a)"
```

---

## Task 2 (Sub-Slice 1b): Backend-Tracing — Flask + gevent + Root-Span

**Ziel:** `init_tracing()` setzt TracerProvider auf, Flask-Auto-Instrumentation läuft unter gevent ohne Span-Context-Verlust, ein manueller Root-Span `agora.simulation.create` umschließt `POST /api/simulations`-Handler. Sichtbar in SigNoz als Trace mit zwei Spans (HTTP + Business).

**Files:**
- Create: `backend/app/observability/__init__.py`, `tracing.py`
- Create: `backend/tests/observability/__init__.py`, `test_tracing_init.py`
- Modify: `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/api/simulation_lifecycle.py`

- [x] **Step 1: Failing-Test anlegen — TracerProvider liefert Spans an In-Memory-Exporter**

`backend/tests/observability/test_tracing_init.py`:

```python
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
```

- [x] **Step 2: Test laufen lassen — muss rot sein**

```bash
cd backend && uv run pytest tests/observability/test_tracing_init.py -v
```
Expected: FAIL mit `ModuleNotFoundError: app.observability`.

- [x] **Step 3: Dependencies in pyproject.toml ergänzen**

In `[project.dependencies]` (oder die existierende Liste) hinzufügen:

```toml
"opentelemetry-api>=1.24.0",
"opentelemetry-sdk>=1.24.0",
"opentelemetry-exporter-otlp-proto-grpc>=1.24.0",
"opentelemetry-instrumentation-flask>=0.45b0",
"opentelemetry-instrumentation-requests>=0.45b0",
"opentelemetry-instrumentation-redis>=0.45b0",
```

Dann: `cd backend && uv sync`.

- [x] **Step 4: `backend/app/observability/__init__.py` schreiben**

```python
"""Observability bootstrap — OpenTelemetry Tracing.

Slice 1b (2026-05-15): Initialisiert TracerProvider + OTLP-Exporter.
Auto-Instrumentation für Flask/requests/redis wird in `tracing.init_tracing`
aktiviert, sobald `OTEL_ENABLED=true` ist.
"""

from .tracing import init_tracing

__all__ = ["init_tracing"]
```

- [x] **Step 5: `backend/app/observability/tracing.py` schreiben**

```python
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

_PROVIDER: Optional[TracerProvider] = None


def init_tracing(
    service_name: str,
    *,
    extra_processors: Optional[List[SpanProcessor]] = None,
) -> Optional[TracerProvider]:
    """Setup TracerProvider, OTLP-Exporter und Auto-Instrumentation.

    Idempotent: Mehrfachaufrufe geben den existierenden Provider zurück.
    NoOp wenn ``OTEL_ENABLED`` != "true".
    """
    global _PROVIDER
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

    # Auto-Instrumentation. Flask muss von der App-Factory zusätzlich pro App
    # mit `FlaskInstrumentor().instrument_app(app)` aktiviert werden.
    RequestsInstrumentor().instrument()
    RedisInstrumentor().instrument()
    return provider


def instrument_flask_app(app) -> None:
    """Wrapper, damit App-Factory keine OTel-API direkt importieren muss."""
    if _PROVIDER is None:
        return
    FlaskInstrumentor().instrument_app(app)
```

- [x] **Step 6: Test grün ziehen**

```bash
cd backend && uv run pytest tests/observability/test_tracing_init.py -v
```
Expected: PASS (beide Tests).

- [x] **Step 7: App-Factory verdrahten**

`backend/app/__init__.py` — am Anfang der `create_app()`-Funktion (vor anderen Initialisierungen, **nach** `gevent.monkey.patch_all()`, falls dort gerufen):

```python
from app.observability import init_tracing, instrument_flask_app

# ... in create_app:
init_tracing(service_name=os.environ.get("OTEL_SERVICE_NAME", "agora-backend"))
# ... nach `app = Flask(...)`:
instrument_flask_app(app)
```

- [x] **Step 8: Manual-Root-Span im Sim-Handler**

`backend/app/api/simulation_lifecycle.py` — den POST-Handler für `/api/simulations` (oder den existierenden Create-Endpoint) mit Span umschließen:

```python
from opentelemetry import trace

_tracer = trace.get_tracer(__name__)

# Im Handler:
with _tracer.start_as_current_span("agora.simulation.create") as span:
    span.set_attribute("agora.simulation.id", simulation_id)
    span.set_attribute("agora.simulation.platform", platform)
    # ... bestehender Code ...
```

- [x] **Step 9: gevent-Kompatibilität verifizieren (manueller Smoke)**

```bash
cd backend
OTEL_ENABLED=true OTEL_SERVICE_NAME=agora-backend uv run python -m flask --app app run --port 5001 &
sleep 3
curl -X POST http://localhost:5001/api/simulations -H 'Content-Type: application/json' -d '{"platform":"reddit","prompt":"smoke"}'
sleep 5
```

Expected: SigNoz-UI zeigt Service `agora-backend` mit einem Trace, der mindestens zwei Spans hat: `POST /api/simulations` (von Flask) und `agora.simulation.create` (manual). Wenn der Span-Context unter gevent verloren geht, sind beide Spans separate Traces — dann Workaround dokumentieren (siehe Worklog).

- [ ] **Step 10: Commit**

```bash
git add backend/app/observability/ backend/tests/observability/ backend/pyproject.toml backend/uv.lock backend/app/__init__.py backend/app/api/simulation_lifecycle.py
git commit -m "feat(observability): Flask + gevent Tracing mit Root-Span im Sim-Lifecycle (Slice 1b)"
```

---

## Task 3 (Sub-Slice 1c): Subprocess-Hop — TRACEPARENT durch Popen

**Ziel:** Der OASIS-Subprozess wird im Sim-Trace als Child-Span dargestellt. Trace-Context wird via `TRACEPARENT`-ENV-Var an `subprocess.Popen` übergeben, im Runner-Script extrahiert und als Parent gesetzt.

**Files:**
- Modify: `backend/app/services/sim/process_manager.py`
- Modify: `backend/scripts/_sim_common.py`
- Create: `backend/tests/observability/test_subprocess_propagation.py`

- [x] **Step 1: Failing-Test — TRACEPARENT-Roundtrip**

`backend/tests/observability/test_subprocess_propagation.py`:

```python
import subprocess
import sys
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def test_traceparent_propagates_via_env(tmp_path):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("parent") as parent:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        traceparent = carrier["traceparent"]
        parent_trace_id = format(parent.get_span_context().trace_id, "032x")

    # Subprocess druckt extrahierte Trace-ID
    script = tmp_path / "child.py"
    script.write_text(
        "import os\n"
        "from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator\n"
        "ctx = TraceContextTextMapPropagator().extract({'traceparent': os.environ['TRACEPARENT']})\n"
        "from opentelemetry import trace\n"
        "span_ctx = trace.get_current_span(ctx).get_span_context()\n"
        "print(format(span_ctx.trace_id, '032x'))\n"
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        env={"TRACEPARENT": traceparent, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == parent_trace_id
```

- [x] **Step 2: Test ausführen, Roundtrip funktioniert mit Stock-API**

```bash
cd backend && uv run pytest tests/observability/test_subprocess_propagation.py -v
```
Expected: PASS (OTel SDK kann das ohne Custom-Code; der Test ist die **Spezifikation**, dass der Mechanismus stabil bleibt).

- [x] **Step 3: `process_manager.py` — TRACEPARENT in Popen-ENV mergen**

In `backend/app/services/sim/process_manager.py` die Stelle finden, an der `subprocess.Popen(...)` aufgerufen wird (vermutlich `start_subprocess` o.ä.) und vor dem Popen-Call den Trace-Context injizieren:

```python
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_tracer = trace.get_tracer(__name__)

# In der Methode, die Popen ruft:
with _tracer.start_as_current_span("agora.subprocess.spawn") as span:
    span.set_attribute("agora.simulation.id", simulation_id)
    span.set_attribute("agora.subprocess.cmd", " ".join(cmd))

    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    env = {**os.environ.copy(), **extra_env, "TRACEPARENT": carrier.get("traceparent", "")}

    process = subprocess.Popen(cmd, env=env, ...)  # existierender Aufruf
```

- [x] **Step 4: Runner-Script Init in `_sim_common.py`**

`backend/scripts/_sim_common.py` — neue Funktion am Anfang des Init-Pfades:

```python
import os
from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

def init_runner_tracing(service_name: str) -> None:
    """Setup TracerProvider im OASIS-Runner und übernimm Parent-Context aus ENV.

    Wird von ``run_*_simulation.py`` direkt nach den Imports gerufen.
    """
    # Lokaler Import, damit Runner ohne OTel-Deps weiter startet
    try:
        from app.observability import init_tracing
    except ImportError:
        return
    init_tracing(service_name)

    traceparent = os.environ.get("TRACEPARENT")
    if traceparent:
        ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
        otel_context.attach(ctx)
```

Und in `run_reddit_simulation.py`, `run_twitter_simulation.py`, `run_parallel_simulation.py` direkt nach den Imports einfügen:

```python
from _sim_common import init_runner_tracing
init_runner_tracing("agora-oasis-runner")
```

- [ ] **Step 5: Smoke — kompletter Trace inkl. Subprocess**

```bash
docker compose -f docker-compose.observability.yml --profile observability up -d
sleep 30
cd backend
OTEL_ENABLED=true uv run python -m flask --app app run --port 5001 &
sleep 3
curl -X POST http://localhost:5001/api/simulations -H 'Content-Type: application/json' -d '{"platform":"reddit","prompt":"trace-smoke"}'
# Sim 30-60s laufen lassen
sleep 60
```

Expected: SigNoz zeigt **einen** Trace mit Services `agora-backend` (Spans `POST /api/simulations`, `agora.simulation.create`, `agora.subprocess.spawn`) **und** `agora-oasis-runner` (Spans aus dem Runner-Script). Trace-ID ist identisch.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sim/process_manager.py backend/scripts/_sim_common.py backend/scripts/run_*_simulation.py backend/tests/observability/test_subprocess_propagation.py
git commit -m "feat(observability): TRACEPARENT-Propagation durch subprocess.Popen-Boundary (Slice 1c)"
```

---

## Task 4 (Sub-Slice 1d): Redis-Hop — Custom Propagator für Pub/Sub-Payloads

**Ziel:** Bus-Events, die vom OASIS-Runner via Redis-pub/sub an den Flask-Stream-Consumer gesendet werden, tragen `traceparent` im Payload. Empfänger-Spans hängen am gleichen Trace.

**Files:**
- Create: `backend/app/observability/redis_propagator.py`
- Create: `backend/tests/observability/test_redis_propagator.py`
- Modify: `backend/scripts/subprocess_redis_bridge.py`
- Modify: `backend/app/services/sim/` (Consumer-Seite — Datei via `grep -rn "RedisEventBus" backend/app/services/sim/` lokalisieren)

- [x] **Step 1: Failing-Test — Inject + Extract Roundtrip**

`backend/tests/observability/test_redis_propagator.py`:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from app.observability.redis_propagator import inject_trace_into_event, extract_trace_from_event


def test_inject_extract_roundtrip():
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("publisher") as parent:
        event = {"type": "state", "simulation_id": "sim-1", "payload": {}}
        enriched = inject_trace_into_event(event)
        parent_trace_id = parent.get_span_context().trace_id

    ctx = extract_trace_from_event(enriched)
    with tracer.start_as_current_span("consumer", context=ctx) as child:
        assert child.get_span_context().trace_id == parent_trace_id


def test_extract_handles_missing_traceparent():
    event = {"type": "state", "simulation_id": "sim-1", "payload": {}}
    ctx = extract_trace_from_event(event)
    assert ctx is not None  # Fallback-Context, kein Crash
```

- [x] **Step 2: Test rot ziehen**

```bash
cd backend && uv run pytest tests/observability/test_redis_propagator.py -v
```
Expected: FAIL mit `ModuleNotFoundError`.

- [x] **Step 3: Propagator implementieren**

`backend/app/observability/redis_propagator.py`:

```python
"""Custom Trace-Propagator für Redis-pub/sub Bus-Events.

Slice 1d (2026-05-15). Redis-pub/sub-Payloads sind JSON-Dicts; OTel hat
keinen Standard-Propagator dafür. Wir mergen ``traceparent`` als reserviertes
Feld in das Event-Dict.
"""

from __future__ import annotations

from typing import Any, Dict

from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_PROPAGATOR = TraceContextTextMapPropagator()
_FIELD = "_otel_traceparent"


def inject_trace_into_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Inject aktuellen Trace-Context in das Event-Dict (mutiert + returnt)."""
    carrier: Dict[str, str] = {}
    _PROPAGATOR.inject(carrier)
    if "traceparent" in carrier:
        event[_FIELD] = carrier["traceparent"]
    return event


def extract_trace_from_event(event: Dict[str, Any]) -> otel_context.Context:
    """Extrahiere Trace-Context aus Event-Dict. Bei Abwesenheit: leerer Context."""
    traceparent = event.get(_FIELD)
    if not traceparent:
        return otel_context.Context()
    return _PROPAGATOR.extract({"traceparent": traceparent})
```

- [x] **Step 4: Test grün ziehen**

```bash
cd backend && uv run pytest tests/observability/test_redis_propagator.py -v
```
Expected: PASS.

- [ ] **Step 5: Publisher-Seite — `subprocess_redis_bridge.py`**

Den Bridge-Publish-Pfad finden (vermutlich Methode `publish`/`emit` o.ä.) und vor dem JSON-Encode des Events injizieren:

```python
from app.observability.redis_propagator import inject_trace_into_event

# vor `await redis.publish(channel, json.dumps(event))`:
event = inject_trace_into_event(event)
```

**Wichtig:** Im OASIS-Runner muss `app.observability` import-bar sein. Wenn der Runner `sys.path` nicht setzt, fallback im Bridge-Module:

```python
try:
    from app.observability.redis_propagator import inject_trace_into_event
except ImportError:
    def inject_trace_into_event(event):  # type: ignore[no-redef]
        return event
```

- [ ] **Step 6: Consumer-Seite — Flask-Pfad, der Bus-Events liest**

```bash
cd backend && rg -n "RedisEventBus\|agora:sim" app/services/ app/api/ | head -20
```

In der gefundenen Consumer-Methode (vermutlich `simulation_stream.py` oder `run_state_store.py`) beim Empfang:

```python
from app.observability.redis_propagator import extract_trace_from_event
from opentelemetry import trace

_tracer = trace.get_tracer(__name__)

# In dem Loop, der Events vom Bus liest:
ctx = extract_trace_from_event(event)
with _tracer.start_as_current_span("agora.bus.event.consume", context=ctx) as span:
    span.set_attribute("agora.event.type", event.get("type", "unknown"))
    span.set_attribute("agora.simulation.id", event.get("simulation_id", ""))
    # ... bestehende Behandlung ...
```

- [ ] **Step 7: Smoke — 3 Hops in einem Trace**

Compose hochziehen, Sim starten wie in Task 3 Step 5.

Expected: SigNoz-Trace hat jetzt vier Service-Hops in einer Kette:
`agora-backend (POST)` → `agora-backend (spawn)` → `agora-oasis-runner (runner work)` → `agora-backend (bus.event.consume)`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/observability/redis_propagator.py backend/tests/observability/test_redis_propagator.py backend/scripts/subprocess_redis_bridge.py backend/app/services/sim/ backend/app/api/simulation_stream.py
git commit -m "feat(observability): Trace-Propagation über Redis-pub/sub Bus-Events (Slice 1d)"
```

---

## Task 5 (Sub-Slice 1e): Frontend-Korrelation — SSE-Event trägt trace_id

**Ziel:** Jedes SSE-Event enthält das aktuelle `trace_id`-Feld. Das Frontend liest es, loggt es in `console.debug`, sendet eigene Browser-Spans über OTLP-HTTP an den Collector und zeigt im SimDetail-Panel einen Deep-Link `http://localhost:3301/trace/<id>` als „Trace anzeigen"-Button.

**Files:**
- Modify: `backend/app/api/simulation_stream.py`
- Modify: `frontend/package.json`, `frontend/src/main.ts`, `frontend/src/api/stream.ts`, `frontend/src/composables/useEventStream.ts`
- Create: `frontend/src/observability/tracing.ts`
- Create: `frontend/tests/observability/tracing.spec.ts`

- [x] **Step 1: Backend — `trace_id` ins SSE-Event mergen**

In `backend/app/api/simulation_stream.py`, an der Stelle, wo das Frame an den Browser geschrieben wird (vermutlich `format_sse_frame` oder direkt `yield f"data: {json.dumps(...)}"`):

```python
from opentelemetry import trace

# Vor json.dumps des Frame-Dicts:
current_span = trace.get_current_span()
span_ctx = current_span.get_span_context()
if span_ctx.is_valid:
    frame["trace_id"] = format(span_ctx.trace_id, "032x")
```

- [x] **Step 2: Frontend-Deps in `frontend/package.json`**

```json
{
  "dependencies": {
    "@opentelemetry/api": "^1.9.0",
    "@opentelemetry/sdk-trace-web": "^1.30.0",
    "@opentelemetry/exporter-trace-otlp-http": "^0.57.0",
    "@opentelemetry/instrumentation-fetch": "^0.57.0",
    "@opentelemetry/context-zone": "^1.30.0",
    "@opentelemetry/resources": "^1.30.0",
    "@opentelemetry/semantic-conventions": "^1.30.0"
  }
}
```

```bash
cd frontend && bun install
```

- [x] **Step 3: Frontend-Tracer schreiben**

`frontend/src/observability/tracing.ts`:

```typescript
import { context, trace } from '@opentelemetry/api'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { Resource } from '@opentelemetry/resources'
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions'
import { BatchSpanProcessor, WebTracerProvider } from '@opentelemetry/sdk-trace-web'
import { ZoneContextManager } from '@opentelemetry/context-zone'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { registerInstrumentations } from '@opentelemetry/instrumentation'

let initialized = false

export function initFrontendTracing(): void {
  if (initialized) return
  if (import.meta.env.VITE_OTEL_ENABLED !== 'true') return

  const provider = new WebTracerProvider({
    resource: new Resource({
      [SemanticResourceAttributes.SERVICE_NAME]: 'agora-frontend',
    }),
  })
  provider.addSpanProcessor(
    new BatchSpanProcessor(
      new OTLPTraceExporter({
        url: import.meta.env.VITE_OTEL_ENDPOINT ?? 'http://localhost:4318/v1/traces',
      }),
    ),
  )
  provider.register({ contextManager: new ZoneContextManager() })
  registerInstrumentations({ instrumentations: [new FetchInstrumentation()] })
  initialized = true
}

export function getTracer(name = 'agora-frontend') {
  return trace.getTracer(name)
}

export function traceIdToSigNozUrl(traceId: string): string {
  const base = import.meta.env.VITE_SIGNOZ_UI ?? 'http://localhost:3301'
  return `${base}/trace/${traceId}`
}

export { context, trace }
```

- [x] **Step 4: `frontend/src/main.ts` — Tracing vor Vue-Init**

```typescript
import { initFrontendTracing } from './observability/tracing'

initFrontendTracing()
// danach: existierender createApp(...).mount(...)
```

- [x] **Step 5: SseEventFrame-Type ergänzen**

`frontend/src/api/stream.ts`:

```typescript
export interface SseEventFrame {
  type: string
  simulation_id: string
  payload: Record<string, unknown>
  ts: number
  trace_id?: string  // NEU (Slice 1e)
}
```

- [x] **Step 6: `useEventStream.ts` — trace_id als Span-Link konsumieren**

In der Stelle, an der Frames verarbeitet werden:

```typescript
import { getTracer } from '../observability/tracing'

// In der EventHandler-Closure:
if (frame.trace_id) {
  const tracer = getTracer()
  const span = tracer.startSpan(`agora.sse.event.${frame.type}`, {
    attributes: {
      'agora.simulation.id': frame.simulation_id,
      'agora.event.trace_id': frame.trace_id,
    },
  })
  span.end()
  // Plus: trace_id als Property im Composable-Returnvalue exponieren, damit
  // SimDetail-Panel den SigNoz-Link rendern kann.
}
```

Der genaue Hook hängt vom existierenden Composable ab — sicherstellen, dass der Reactive-State um `lastTraceId: Ref<string | null>` erweitert wird, return-merge.

- [x] **Step 7: SimDetail-Panel — „Trace anzeigen"-Button**

In der Vue-Komponente, die den aktuellen Sim-Stream rendert (vermutlich unter `frontend/src/components/Step*.vue` — via Grep: `rg -l "useEventStream" frontend/src/`):

```vue
<script setup lang="ts">
import { traceIdToSigNozUrl } from '@/observability/tracing'
// ... existierender Code ...
const { lastTraceId } = useEventStream(...)
</script>

<template>
  <!-- ... -->
  <a v-if="lastTraceId" :href="traceIdToSigNozUrl(lastTraceId)" target="_blank" class="trace-link">
    Trace anzeigen ({{ lastTraceId.slice(0, 8) }}…)
  </a>
</template>
```

- [x] **Step 8: Vitest-Smoke**

`frontend/tests/observability/tracing.spec.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'
import { initFrontendTracing, getTracer, traceIdToSigNozUrl } from '@/observability/tracing'

describe('frontend tracing', () => {
  it('traceIdToSigNozUrl baut korrekten Deep-Link', () => {
    const url = traceIdToSigNozUrl('abc123')
    expect(url).toMatch(/\/trace\/abc123$/)
  })

  it('initFrontendTracing ist idempotent', () => {
    vi.stubEnv('VITE_OTEL_ENABLED', 'true')
    expect(() => {
      initFrontendTracing()
      initFrontendTracing()
    }).not.toThrow()
  })

  it('getTracer liefert einen Tracer', () => {
    expect(getTracer()).toBeDefined()
  })
})
```

```bash
cd frontend && bun run test -- tests/observability/
```
Expected: 3 passed.

- [ ] **Step 9: E2E-Smoke**

Compose + Backend + Frontend hochziehen, Sim starten wie in Task 3 Step 5, im Browser zu `/simulations/<id>` navigieren.

Expected:
- DevTools-Console zeigt `console.debug` mit der `trace_id` zu jedem SSE-Frame.
- SimDetail-Panel zeigt „Trace anzeigen ({prefix}…)"-Link.
- Klick auf Link öffnet SigNoz-UI mit dem End-to-End-Trace: 5+ Services in einer Kette (`agora-frontend → agora-backend (POST) → agora-backend (spawn) → agora-oasis-runner → agora-backend (bus.event.consume) → agora-backend (sse.stream)`).

- [ ] **Step 10: Commit**

```bash
git add backend/app/api/simulation_stream.py frontend/package.json frontend/bun.lock frontend/src/observability/ frontend/src/main.ts frontend/src/api/stream.ts frontend/src/composables/useEventStream.ts frontend/src/components/ frontend/tests/observability/
git commit -m "feat(observability): End-to-End-Trace-Korrelation Browser ↔ Backend via SSE trace_id (Slice 1e)"
```

---

## Task 6 (Sub-Slice 1f): Worklog + Blog-Draft

**Ziel:** Arbeitsprotokoll im Repo, blogfähiger Entwurf für alexle135.de mit den vier Story-Hops dokumentiert.

**Files:**
- Create: `docu/2026-05-15-observability-slice-1-worklog.md`
- Create: `docu/2026-05-15-observability-slice-1-blog-draft.md`

- [ ] **Step 1: Worklog schreiben**

`docu/2026-05-15-observability-slice-1-worklog.md` — Alex' Standard-Worklog-Format:

```markdown
# Worklog — Observability Slice 1 (2026-05-15)

## Scope
End-to-End-Tracing der Sim-Pipeline mit SigNoz + OTel.

## Ergebnis
- Sub-Slice 1a: SigNoz + OTel-Collector lokal verfügbar (Profile `observability`)
- Sub-Slice 1b: Flask + gevent + Root-Span — kompatibel ohne Workaround
- Sub-Slice 1c: TRACEPARENT-Env-Propagation durch subprocess.Popen
- Sub-Slice 1d: Custom Redis-Propagator (`_otel_traceparent`-Feld)
- Sub-Slice 1e: SSE-Frame trägt `trace_id`, Frontend rendert SigNoz-Deep-Link

## Gemessen
- Backend-Span-Overhead: <X ms p95 (BatchSpanProcessor)
- SigNoz-UI-Latency lokal: <Y ms
- Frontend-Bundle-Delta: +Z KB durch OTel-Web-SDK

## Offen
- Metrics-Pipeline (Sub-Slice 2)
- Logs-Korrelation per trace_id (Sub-Slice 3)
- SLOs + Burn-Rate-Alerts (Sub-Slice 4)

## Risiken / Beobachtungen
- gevent + OTel Span-Context: verifiziert, kein Workaround nötig.
- Auto-Instrumentation-Redis kann auch im Runner-Subprozess greifen — dann
  doppelte Spans. Wenn das auftritt: Auto-Instrumentation im Runner gezielt
  abschalten (`opentelemetry.instrumentation.redis.RedisInstrumentor().uninstrument()`).
```

- [ ] **Step 2: Blog-Draft schreiben**

`docu/2026-05-15-observability-slice-1-blog-draft.md` — Skelett mit den vier Hops als Hauptkapitel, gedacht zur späteren Übernahme nach `alexle135.de`. Min. 800 Wörter, Codeblöcke aus dem Worklog wiederverwenden. Tonalität: technisch-nüchtern, kein Werbedeutsch, Glossar v1 beachten.

- [ ] **Step 3: STATUS.md ergänzen** (falls vorhanden)

```bash
rg -l "Layer 9" docu/STATUS.md && echo "STATUS.md existiert, manuelle Sektion 'Observability' anhängen"
```

Eine neue Zeile/Section in `docu/STATUS.md`, die den Slice abschließt, in Alex' bestehendem Tabellenstil.

- [ ] **Step 4: Commit**

```bash
git add docu/2026-05-15-observability-slice-1-worklog.md docu/2026-05-15-observability-slice-1-blog-draft.md docu/STATUS.md
git commit -m "docs: Observability Slice 1 Worklog + Blog-Draft (alexle135.de)"
```

- [ ] **Step 5: Branch fertig, PR vorbereiten**

```bash
git push -u origin feat/observability-slice-1
gh pr create --title "feat(observability): End-to-End-Tracing Sim-Pipeline (Slice 1)" --body "$(cat <<'EOF'
## Summary
- SigNoz Community Edition + OTel-Collector als lokaler Compose-Stack (Profile `observability`)
- Trace propagiert von Browser → Flask → subprocess.Popen → OASIS-Runner → Redis-pub/sub → SSE
- Custom Redis-Propagator (`_otel_traceparent`-Feld) für pub/sub-Boundary
- Frontend-Korrelation via `trace_id`-Feld in SSE-Frames + SigNoz-Deep-Link im SimDetail-Panel

## Test plan
- [ ] `cd backend && uv run pytest tests/observability/ -v` grün
- [ ] `cd frontend && bun run test -- tests/observability/` grün
- [ ] E2E-Smoke: `docker compose -f docker-compose.observability.yml --profile observability up -d`, dann Sim starten, in SigNoz-UI End-to-End-Trace mit ≥5 Service-Hops verifizieren
- [ ] gevent-Kompatibilität: Trace-Context bleibt über mehrere SSE-Frames hinweg konsistent
- [ ] OTEL_ENABLED=false: Agora startet ohne OTel-Overhead und ohne Crash

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Pflicht nach `gh pr create` (CLAUDE.md):
```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

---

## Globale Akzeptanzkriterien (am Ende des Slice)

1. `OTEL_ENABLED=false` — Agora-Backend + Frontend starten ohne Crash, **keine** OTel-Spans werden exportiert. Default ist `false`.
2. `OTEL_ENABLED=true` — eine Simulation produziert genau **einen** zusammenhängenden Trace mit Spans aus drei Services: `agora-frontend`, `agora-backend`, `agora-oasis-runner`.
3. Alle drei Service-Namen sind in der SigNoz-UI unter „Services" sichtbar.
4. Frontend-SimDetail-Panel rendert den SigNoz-Deep-Link mit der aktuellen `trace_id`.
5. Test-Suite: `pytest tests/observability/` (mindestens 4 Tests) + `bun run test -- tests/observability/` (mindestens 3 Tests) grün.
6. Gemini-Code-Assist-Findings (Default-Workflow nach `gh pr create`) sind gesichtet und HIGH-Findings adressiert.

---

## Hart außerhalb von Slice 1 (für Folge-Slices)

- **Metrics (Slice 2):** Prometheus-style Counters/Histograms, Sim-Latenz-Histogramm.
- **Logs-Korrelation (Slice 3):** `trace_id` in Python-Loggern, SigNoz-Logs-Ansicht.
- **SLOs + Burn-Rate-Alerts (Slice 4):** „Sim-Run p95 < X s", Alertmanager-Regeln.
- **Production-Stack-Härtung:** OTel im `prod`-Image, Layer-9-Gates erneut durchlaufen.

---

## Risk Register

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| gevent monkey-patch bricht OTel-Context | Mittel | Smoke in Task 2 Step 9; bei Bruch: `opentelemetry-instrumentation-flask` durch manuelle Spans ersetzen |
| Auto-Instrumentation-Redis erzeugt doppelte Spans im Runner | Niedrig | Im Runner gezielt `RedisInstrumentor().uninstrument()` nach `init_runner_tracing` |
| SigNoz-ClickHouse braucht zu viel RAM auf macOS | Mittel | Docker-Desktop auf 8 GB hochsetzen, oder Wert in `memory_limiter` Processor senken |
| Frontend-OTel-Bundle bläht Vendor-Chunk auf | Mittel | `manualChunks`-Strategie in `vite.config.ts` für `@opentelemetry/*` |
| `traceparent`-Env-Var taucht in Log-Dumps auf | Niedrig | Logging-Redaction-Skript (existierendes Logging-Protokoll) prüfen |
