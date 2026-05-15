# Observability Slice 2 — Metrics-Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` oder `superpowers:executing-plans`.

**Status:** Plan, Implementation offen. Baut auf Slice 1 (Tracing) auf. Trigger frühestens nach 2026-05-22.

**Goal:** Sim-Lifecycle und kritische Backend-Pfade emittieren OpenTelemetry-Metrics (Counter, Histogram, UpDownCounter) parallel zu den existierenden Spans. SigNoz zeigt Sim-Latenz-Histogramm, Error-Rate, Active-Sim-Gauge und LLM-Token-Verbrauch in einem Dashboard.

**Architecture:** OTLP-Metrics-Exporter über den existierenden Collector (Slice 1a). ClickHouse-Backend von SigNoz unterstützt Metrics nativ. Frontend bekommt einen einfachen Counter für Stream-Reconnects.

**Tech Stack:** `opentelemetry-sdk` (Metrics-Provider), `opentelemetry-exporter-otlp-proto-grpc` (bereits aus Slice 1b), neues Modul `backend/app/observability/metrics.py`. Default-Off via `OTEL_METRICS_ENABLED=false`.

**Aufwand:** ~3–4 Tage in 3 Sub-Slices.

---

## File Structure

### Neu
- `backend/app/observability/metrics.py` — `init_metrics(service_name)` + Helper für die 4 Hot-Counter.
- `backend/tests/observability/test_metrics.py` — InMemoryMetricReader-Smoke + Counter-Increment-Roundtrip.
- `deploy/observability/signoz-dashboard-sim-overview.json` — exportierbares Dashboard-JSON.

### Modify
- `backend/pyproject.toml` — Dep `opentelemetry-sdk` (Metrics ist im selben Paket, kein Extra).
- `backend/app/observability/__init__.py` — Re-Export `init_metrics`.
- `backend/app/__init__.py` — `init_metrics()` neben `init_tracing()`.
- `backend/app/services/simulation_runner.py` — `sim_started` (Counter), `sim_duration_seconds` (Histogram), `sim_active` (UpDownCounter).
- `backend/app/services/event_bus_redis.py` — `bus_events_dropped_total` (Counter mit `reason`-Label) für KeyError/JSONDecodeError-Pfad.
- `backend/app/utils/llm_client.py` — `llm_tokens_total` (Counter mit `provider`, `model`, `direction`-Labels).
- `.env.example` — `OTEL_METRICS_ENABLED`.

---

## Task 1 — Foundation `metrics.py`

- [ ] **TDD:** `test_metrics.py` mit `InMemoryMetricReader`. Zwei Cases: (a) Counter-Increment landet in Reader, (b) NoOp wenn `OTEL_METRICS_ENABLED=false`.
- [ ] metrics.py::init_metrics(service_name) analog zu init_tracing. Module-Cache, OTLP-gRPC-Exporter, PeriodicExportingMetricReader(export_interval_millis=10_000). Hinweis: force_flush() für Runner-Scripts einplanen.
- [ ] Helper-Factories: `sim_counter()`, `sim_duration_histogram()`, `sim_active_gauge()`, `bus_event_drop_counter()`, `llm_token_counter()`.
- [ ] Test grün, Commit.

## Task 2 — Verdrahtung in Sim-Lifecycle

- [ ] In `simulation_runner.py` an den FSM-Übergängen `PENDING → RUNNING` und `RUNNING → DONE|FAILED`:
  - `sim_counter().add(1, {"status": "started"|"done"|"failed"})`
  - `sim_active_gauge().add(+1 | -1)`
  - `sim_duration_histogram().record(elapsed_seconds, {"status": ...})`
- [ ] In `event_bus_redis.py::_subscribe_live`-Except-Block: `bus_event_drop_counter().add(1, {"reason": "decode_error" | "schema_error"})`.
- [ ] In `llm_client.py`: nach jeder erfolgreichen `chat()`-/`chat_json()`-Antwort `llm_token_counter().add(prompt_tokens, {"direction": "in"})` und analog für `completion_tokens`.

## Task 3 — Dashboard + Worklog

- [ ] SigNoz-Dashboard `Sim Overview` (Panels: Active-Sim-Gauge, p50/p95/p99-Duration, Started/Done/Failed-Rate, Drop-Counter-Sparkline, Token-Verbrauch nach Provider).
- [ ] Export als `signoz-dashboard-sim-overview.json`, in `deploy/observability/` versionieren.
- [ ] Worklog `docu/2026-05-XX-observability-slice-2-worklog.md`.
- [ ] STATUS.md ergänzen, `scripts/sync-status.sh` ausführen.
- [ ] **Ein PR**, analog Slice 1.

---

## Akzeptanzkriterien

1. `OTEL_METRICS_ENABLED=false`: keine Metric-Emission, Sim-Performance unverändert.
2. `OTEL_METRICS_ENABLED=true`: SigNoz-UI zeigt nach einer Sim mindestens diese vier Series: `agora.sim.started`, `agora.sim.duration_seconds`, `agora.bus.events.dropped`, `agora.llm.tokens`.
3. Backend pytest grün, kein Bestehender Test gebrochen.
4. Dashboard-JSON in Repo versioniert, lokaler Import in SigNoz testbar.

---

## Risk Register

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| PeriodicExportingMetricReader Memory unter gevent | Niedrig | Export-Interval = 10s konservativ; Daten gehen über lokalen Collector, kein Backpressure |
| LLM-Token-Counter doppelt gezählt bei Retry | Mittel | Nur in erfolgreichem Antwort-Pfad incrementieren, nicht im Retry-Loop |
| Cardinality-Explosion bei Labels | Niedrig | Keine `simulation_id` als Label, nur Status/Provider/Model |
