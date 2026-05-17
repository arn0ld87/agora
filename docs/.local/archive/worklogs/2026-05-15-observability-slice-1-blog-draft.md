# End-to-End-Tracing für einen lokalen Multi-Agent-Simulator: vier seltene Hops

*Draft für alexle135.de · Stand 2026-05-15 · Slice 1 von Agora-Observability*

## Warum überhaupt Tracing für einen lokalen Stack?

Agora ist ein lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.
Backend ist Flask mit `gevent`-Workern, die Agenten laufen über OASIS in einem
eigenen `subprocess`, Live-Events fließen über Redis-pub/sub, der Browser liest
Server-Sent-Events. Bis Mai 2026 hatte ich für diesen Stack keinerlei verteiltes
Tracing. Logs, ja. Print-Statements im Runner-Subprozess, ja. Aber keine Linie,
die einen einzelnen Sim-Lauf vom Klick im Browser bis zur letzten Agent-Antwort
zusammenhält.

Die ehrliche Motivation: kein akuter Performance-Schmerz. Die Sim-Pipeline
arbeitet stabil, Antwortzeiten liegen im Bereich, in dem ein User noch nicht
ungeduldig wird. Treiber waren stattdessen drei andere Punkte. Erstens ein
Lerneffekt — `OpenTelemetry` über `subprocess`-Grenzen und einen Redis-Bus zu
ziehen ist nicht trivial, und das ist genau die Sorte Aufgabe, die ich für
meine Q3-2026-Story über System-Integration brauche. Zweitens lokal-first
Observability für AI-Workloads, ohne SaaS-Lock-in. Drittens die einfache
Tatsache, dass ich nach einem fehlgeschlagenen Sim-Lauf bisher mehrere
Log-Files parallel auf Korrelation prüfen musste. Eine `trace_id` macht das in
einer Zeile sichtbar.

## Architektur in einem Absatz

Der Stack besteht aus drei Service-Namen: `agora-frontend`, `agora-backend`
und `agora-oasis-runner`. Trace-Daten gehen per W3C-`traceparent` durch die
Pipeline und werden von einem OpenTelemetry-Collector eingesammelt. Backend
ist SigNoz Community Edition, self-hosted, Apache-2.0-lizensiert, mit
ClickHouse als Speicher. Alles läuft als Docker-Compose-Profile
`observability`. Solange ich das Profile nicht hochfahre, ist der Overhead
gleich null. Die Backend-Instrumentation ist außerdem default-off über das
Flag `OTEL_ENABLED=false` — Agora startet ohne SigNoz und ohne OTel-Collector
exakt wie vorher.

## Hop 1 — gevent + Flask

Der erste seltene Hop ist die Kombination aus `gevent.monkey.patch_all()` und
OTel. Das Pattern, das funktioniert: `init_tracing()` läuft in der App-Factory
**nach** dem Monkey-Patch, aber **vor** dem ersten Blueprint-Register. OTel
nutzt `ContextVar` für Span-Propagation, und das Verhalten unter gepatchten
Greenlets ist seit ~2023 stabil — der Span-Context bleibt am richtigen
Greenlet.

```python
# backend/app/observability/tracing.py
def init_tracing(service_name: str = "agora-backend") -> None:
    if not os.getenv("OTEL_ENABLED", "false").lower() == "true":
        return  # NoOp-Pfad
    if _is_initialized():
        return  # idempotent
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FlaskInstrumentor().instrument()
    RedisInstrumentor().instrument()
```

Idempotenz ist Pflicht, weil Flask in Tests die App-Factory mehrfach aufruft
und sonst doppelte Provider-Registrierungen einen Test-Cross-Effect erzeugen.

## Hop 2 — `subprocess.Popen` zum OASIS-Runner

Sobald Agora einen Sim startet, forkt das Backend einen Runner-Subprozess
über `subprocess.Popen`. OTels Auto-Instrumentation propagiert keinen
Trace-Context über Prozessgrenzen — das ist Aufgabe des Anwendungs-Codes.
Mein Pattern: der `TRACEPARENT`-Header wandert als Environment-Variable in
den Child, der Child injiziert ihn beim Start in seinen eigenen Tracer-
Context.

```python
# backend/scripts/_sim_common.py
def init_runner_tracing(service_name: str = "agora-oasis-runner") -> Context | None:
    if os.getenv("OTEL_ENABLED", "false").lower() != "true":
        return None
    init_tracing(service_name=service_name)
    traceparent = os.getenv("TRACEPARENT")
    if not traceparent:
        return None
    carrier = {"traceparent": traceparent}
    return TraceContextTextMapPropagator().extract(carrier)
```

Im Parent (in `process_manager.py`) baue ich vor `subprocess.Popen` einen
Carrier aus dem aktuellen Span-Context, kopiere den `traceparent` ins
ENV-Dict und übergebe es per `env=`. Wichtig: kein impliziter `os.environ`-
Merge, sondern ein explizit aufgebautes Environment, sonst sind
sicherheitsrelevante Variablen mit unklarem Scope an Bord.

## Hop 3 — Redis pub/sub

Der Runner publiziert seine Agent-Events über Redis-pub/sub zurück zum
Backend. Auch hier propagiert OTel von Haus aus nichts, weil pub/sub kein
Request-Response-Pattern ist. Ich habe einen Custom-Propagator gebaut:
das publizierte Event-Dict bekommt ein zusätzliches Feld
`_otel_traceparent`, das beim Consumer wieder extrahiert wird.

```python
# backend/app/services/redis_propagator.py
def inject_trace_to_event(event: dict) -> dict:
    carrier: dict[str, str] = {}
    TraceContextTextMapPropagator().inject(carrier)
    if "traceparent" in carrier:
        event["_otel_traceparent"] = carrier["traceparent"]
    return event

def extract_trace_from_event(event: dict) -> Context | None:
    traceparent = event.get("_otel_traceparent")
    if not traceparent:
        return None
    return TraceContextTextMapPropagator().extract({"traceparent": traceparent})
```

Der Consumer (`event_bus_redis.py::_subscribe_live`) öffnet pro empfangenem
Event einen Span `agora.bus.event.consume`, der **vor** dem `yield` wieder
geschlossen wird. Das ist die wichtigste Designentscheidung in diesem Hop:
ein Generator-Span, der über `yield` hinaus offen bliebe, würde seine
Lifetime an die SSE-Verbindung koppeln — der Span wäre dann kein einzelner
Bus-Event, sondern ein minutenlanger Stream. Ein Span pro Event, hart
begrenzt.

## Hop 4 — SSE-Frame und Browser-Tracer

Der vierte und letzte Hop führt vom Backend zurück in den Browser. Ich habe
das simpelste Schema gewählt, das funktioniert: jeder SSE-Frame trägt ein
`trace_id`-Feld in seinem JSON-Payload. Der Frontend-Code liest es im
`useEventStream`-Composable und legt es als `lastTraceId`-Ref ab.

```python
# backend/app/api/simulation_stream.py
def _event_to_sse(event: dict, span: Span | None = None) -> str:
    payload = dict(event)
    if span is not None and span.get_span_context().is_valid:
        payload["trace_id"] = format_trace_id(span.get_span_context().trace_id)
    return f"data: {json.dumps(payload)}\n\n"
```

Im Browser läuft ein OTel-Web-Tracer mit `ZoneContextManager`. Der Tracer
ist klein, kostet allerdings ein paar Kilobytes — das Bundle wächst um
34 kB (von 728 kB auf 763 kB). Dafür hat das SimDetail-Panel jetzt einen
Deep-Link in die SigNoz-UI, der direkt den richtigen Trace öffnet:

```ts
const signozUrl = `${signozBaseUrl}/trace/${lastTraceId.value}`
```

Damit ist die Kette zu: Klick im Frontend → Flask-Span → ENV-Var an den
Subprozess → Redis-Feld → Consumer-Span → SSE-Frame → Browser-Deep-Link.

## Was es kostet

- Frontend-Bundle: +34 kB (≈ 4.7 %). Akzeptabel, kein Code-Splitting-Bedarf.
- Backend-Overhead bei `OTEL_ENABLED=false`: null (NoOp-Pfad).
- Backend-Overhead bei `OTEL_ENABLED=true`: nicht final gemessen,
  erwartet im einstelligen Prozent-Bereich pro Request (Flask-Auto-
  Instrumentation + ein Custom-Span pro Sim-Step).
- Tests: 2232 Backend-Cases grün, vier neue Vitest-Cases im Frontend grün.

## Was offen bleibt

Slice 1 deckt **Traces**. Drei Folge-Slices stehen auf dem Plan und sind
bewusst nicht zusammen mit Slice 1 gebaut worden:

- **Metrics-Pipeline** für HTTP-Latency, Sim-Counter, LLM-Calls.
- **Logs-Korrelation** — strukturierte Log-Lines mit `trace_id`-Feld und
  Cross-Linking SigNoz-Logs ↔ Traces.
- **SLOs + Burn-Rate-Alerts** — erst sinnvoll, wenn Metrics stehen.

Außerdem fehlt die **Production-Härtung**: OTel im `prod`-Image, Layer-9-
Gates erneut durchlaufen, `read_only: true` mit den OTel-Pufferpfaden
verträglich machen. Das ist ein eigener Slice und kein Anhängsel.

## Fazit

Vier Hops, sechs atomic Sub-Slices, sechs Commits, ~1100 LOC Netto-Delta,
default-off. Der Stack zeigt jetzt das, was ich vorher aus drei parallelen
Log-Files lesen musste. Ob das den Aufwand rechtfertigt, hängt vom
nächsten Vorfall ab — der erste Sim-Lauf mit einem Hänger im
OASIS-Subprozess wird zeigen, ob die `trace_id` schneller zur Ursache
führt als `grep` über drei Files. Bis dahin ist es eine Infrastruktur-
Investition mit klarem Lerneffekt und einer Reihe sauber dokumentierter
Patterns für vier Grenzen, die OTel nicht von Haus aus überquert.
