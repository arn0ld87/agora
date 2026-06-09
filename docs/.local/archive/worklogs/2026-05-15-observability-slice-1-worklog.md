# Worklog — Observability Slice 1 (2026-05-15)

## Scope

End-to-End-Tracing der Sim-Pipeline mit SigNoz Community Edition + OpenTelemetry.
Plan: [`docu/plans/2026-05-15-observability-slice-1.md`](plans/2026-05-15-observability-slice-1.md).
Branch: `feat/observability-slice-1`.
Treiber: Lerneffekt + System-Integration-Story (Q3 2026) + lokal-first Observability für
den AI-Stack. Kein Performance- oder Wartbarkeitsschmerz — Sichtbarkeit über vier seltene
Hops (gevent ↔ OTel, `subprocess.Popen`, Redis-pub/sub, SSE-Frame ↔ Browser).

## Ergebnis (alle 6 Sub-Slices durch)

- **1a — Compose-Stack.** SigNoz CE + OTel-Collector als Compose-Profile `observability`
  in `docker-compose.observability.yml` plus `deploy/observability/`. Default ungestartet,
  kein Overhead solange das Profile nicht hochgefahren wird. Commit `09e818b`.
- **1b — Flask + gevent.** Auto-Instrumentation in `backend/app/observability/__init__.py`
  und `backend/app/observability/tracing.py`. Root-Span `agora.simulation.create` im
  `simulation_lifecycle.py` an der Sim-Erzeugung verankert. Idempotenz über Module-Cache,
  NoOp-Pfad bei `OTEL_ENABLED=false`. Commit `3380b6c`.
- **1c — subprocess.Popen.** `TRACEPARENT`-ENV-Inject in `process_manager.py`, Extract
  via `TraceContextTextMapPropagator().extract()` in `backend/scripts/_sim_common.py`
  über die neue Helper-Funktion `init_runner_tracing()`. Drei Runner-Scripts angebunden.
  Commit `172769a`.
- **1d — Redis-pub/sub.** Custom Propagator: `_otel_traceparent`-Feld im publizierten
  Event-Dict. Publisher in `subprocess_redis_bridge.py`, Consumer-Span
  `agora.bus.event.consume` in `event_bus_redis.py::_subscribe_live`. Generator-Grenze
  bewusst sauber behandelt: Span endet vor `yield`, nicht über die gesamte SSE-Lifetime.
  Commit `d82e51c`.
- **1e — SSE + Frontend-Web-Tracer.** `trace_id` im SSE-Frame
  (`simulation_stream.py::_event_to_sse`), `frontend/src/observability/tracing.ts` mit
  WebTracerProvider und ZoneContextManager, `lastTraceId`-Ref in `useEventStream.ts`,
  SigNoz-Deep-Link im SimDetail-Panel (`Step3Simulation.vue`). Bundle-Delta +34 kB.
  Commits `212505e` (Foundation) und `425d098` (final).
- **1f — Worklog + Blog-Draft + STATUS-Update.** Dieses Worklog, der Blog-Draft
  [`docu/2026-05-15-observability-slice-1-blog-draft.md`](2026-05-15-observability-slice-1-blog-draft.md)
  und der STATUS-Anhang. Kein Code-Touch.

## Gemessen

- Backend `pytest -x -q`: **2232 passed, 9 skipped**. Kein bestehender Test gebrochen.
- Backend `ruff check . && mypy app`: clean.
- Frontend `npm run typecheck && npm run lint && npm run build`: clean.
- Vitest-Smoke neue Suite für `observability/tracing.ts` und `useEventStream`-Deep-Link
  (4 Cases): PASS.
- Frontend-Bundle: **728 kB → 763 kB (+34 kB)** durch OTel Web-SDK +
  `@opentelemetry/context-zone` + `@opentelemetry/exporter-trace-otlp-http`.
- Slice-Aufwand: ~6 atomic Sub-Slices über mehrere parallele Subagent-Wellen
  (Backend-Worker / Frontend-Worker / Test-Worker).
- Commit-Anzahl auf Branch: 6 (1a–1e); 1f folgt mit dieser Doku.

## Offen / Folge-Slices

- **Slice 2 — Metrics-Pipeline.** OTel-Metrics für HTTP-Latency, Sim-Counter, LLM-Calls.
- **Slice 3 — Logs-Korrelation.** Strukturierte Log-Lines mit `trace_id`-Feld,
  Cross-Linking SigNoz-Logs ↔ Traces.
- **Slice 4 — SLOs + Burn-Rate-Alerts.** Erst sinnvoll mit Slice 2.
- **Production-Härtung.** OTel im `prod`-Image (Multi-Stage), Layer-9-Gates erneut
  durchlaufen, `read_only: true` mit OTel-Pufferpfaden verträglich machen.
- **PR-Workflow.** Nach `gh pr create` (durch User) 90 s warten, Gemini-Findings sichten,
  HIGH/MEDIUM adressieren, dann FF-Merge auf `main`.

## Risiken / Beobachtungen

- **gevent + OTel Span-Context.** Im monkey-patched Eventloop liefert OTel die Context-
  Propagation per `ContextVar`. End-to-End-Verifikation gegen einen Live-SigNoz-Stack
  steht aus (kein Live-Stack in CI). Slice-1f-Smoke ist manuell vom User auszuführen.
- **Auto-Instrumentation-Redis im Runner-Subprozess.** Kann theoretisch doppelte Spans
  erzeugen, wenn der Runner `redis.Redis()` direkt nutzt und die Auto-Instrumentation
  zusätzlich beim Boot greift. Mitigation: bei Beobachtung gezielt
  `RedisInstrumentor().uninstrument()` nach `init_runner_tracing` aufrufen — nicht
  präventiv deaktiviert, um die Beobachtung im echten Stack erst zu machen.
- **Generator-Span in `_subscribe_live`.** Bewusst auf die Decode- und Yield-Vorbereitung
  begrenzt. Wenn der Span über `yield` ginge, würde seine Lifetime an die SSE-Verbindung
  gekoppelt — das ist kein einzelner Bus-Event mehr, sondern ein Stream. Aktuell:
  ein Span pro Event, sauber begrenzt.
- **OTel-Flask DeprecationWarning.** `__version__` ist in Flask 3.2 deprecated; das
  warnt aus dem `opentelemetry-instrumentation-flask`-Code, nicht aus Agora.
  Upstream-Problem, kein eigener Code.
- **Test-Side-Effect.** Slice-1d-Test setzt `trace.set_tracer_provider()` global. Isoliert
  via Fixture im selben File, damit Slice-1b-Tests nicht in denselben Provider greifen.
  Cross-Test-Side-Effect ist damit gelöst.

## Folgeaktionen für den User

1. **Live-Smoke.**

   ```bash
   cd /Volumes/T7/Projekte/agora
   docker compose -f docker-compose.observability.yml --profile observability up -d
   OTEL_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
       docker compose up -d agora
   # Sim starten via UI, dann SigNoz auf http://localhost:3301
   ```

   Erwartet: End-to-End-Trace mit ≥5 Service-Hops (`agora-frontend` →
   `agora-backend` → Redis → `agora-oasis-runner` → Redis → `agora-backend` →
   SSE-Frame mit `trace_id`).

2. **PR-Workflow.**

   ```bash
   gh pr create --title "feat(observability): End-to-End-Tracing Slice 1" \
                --body  "..."
   sleep 90
   gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
   gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
   ```

   HIGH-Findings im Branch nachpatchen, MEDIUM nach Scope, LOW dokumentieren.

3. **Knowledge-Graph-Refresh.** Nach Merge `code-review-graph update` ausführen, damit
   die neuen `app/observability/`-Knoten und der Propagator in `event_bus_redis.py`
   indiziert sind.

## Referenzen

- Plan: [`docu/plans/2026-05-15-observability-slice-1.md`](plans/2026-05-15-observability-slice-1.md)
- Blog-Draft: [`docu/2026-05-15-observability-slice-1-blog-draft.md`](2026-05-15-observability-slice-1-blog-draft.md)
- Status-Anhang: [`docu/STATUS.md § Observability Slice 1`](STATUS.md#observability-slice-1-2026-05-15)
