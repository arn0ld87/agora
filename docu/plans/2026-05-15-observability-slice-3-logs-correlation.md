# Observability Slice 3 — Logs-Korrelation via trace_id

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` oder `superpowers:executing-plans`.

**Status:** Plan, Implementation offen. Baut auf Slice 1 + 2 auf. Trigger nach Slice 2.

**Goal:** Jeder Python-Log-Eintrag im Sim-Pfad trägt im JSON-Format das aktuelle `trace_id` und `span_id`. SigNoz-Logs-Ansicht zeigt für jeden Trace alle korrelierten Logs auf einen Klick. Existierender `app.logger`-Aufrufstil bleibt unverändert.

**Architecture:** `LoggingInstrumentor` aus `opentelemetry-instrumentation-logging` patcht den Root-Logger so, dass `trace_id` / `span_id` als LogRecord-Attribute landen. Custom `JSONFormatter` (oder `python-json-logger`) gibt JSON aus, das vom OTel-Collector via filelog-receiver oder direkt vom Backend via OTLP-Logs-Exporter zu SigNoz geht.

**Tech Stack:** `opentelemetry-instrumentation-logging`, `python-json-logger` (oder eigener `logging.Formatter`), `opentelemetry-sdk._logs` + `opentelemetry-exporter-otlp-proto-grpc` für OTLP-Logs.

**Aufwand:** ~3 Tage in 2 Sub-Slices.

---

## File Structure

### Neu
- `backend/app/observability/logging_bridge.py` — `init_logging(service_name)` + `JsonTraceFormatter`.
- `backend/tests/observability/test_logging_bridge.py` — Roundtrip: `app.logger.info("test")` innerhalb eines Spans erzeugt JSON-LogRecord mit korrektem `trace_id`.
- `deploy/observability/otel-collector-logs.yaml` oder Erweiterung von `otel-collector.yaml` mit filelog-Receiver.

### Modify
- `backend/pyproject.toml` — neue Deps.
- `backend/app/observability/__init__.py` — Re-Export.
- `backend/app/__init__.py` — `init_logging(service_name)` direkt nach `init_tracing`.
- `backend/scripts/_sim_common.py` — `init_runner_logging` analog zu `init_runner_tracing`.
- `.env.example` — `OTEL_LOGS_ENABLED`.

---

## Task 1 — Foundation `logging_bridge.py`

- [ ] **TDD:** Test, der innerhalb eines aktiven Spans `logger.info("hello")` ruft und prüft, dass die geparste JSON-Zeile `trace_id` + `span_id` enthält.
- [ ] `JsonTraceFormatter` mit Feldern: `timestamp`, `level`, `logger`, `message`, `trace_id`, `span_id`, `service.name`. Format ist eine JSON-Zeile pro Record.
- [ ] `LoggingInstrumentor().instrument(set_logging_format=False)` (eigener Formatter ist vorrangig).
- [ ] OTLP-Logs-Exporter über bestehenden Collector (zusätzlicher Pipeline-Block `logs` in `otel-collector.yaml`).

## Task 2 — Verdrahtung + Dashboard

- [ ] Alle bestehenden `print(...)`-Stellen in Prod-Code auf `logger.info|warning|error` umstellen (siehe CLAUDE.md-Verbot von `print`). Falls Stellen außerhalb des Sim-Pfads betroffen sind: aus dem Scope nehmen und als TODO in Worklog.
- [ ] Runner-Scripts `run_*_simulation.py` bekommen `init_runner_logging("agora-oasis-runner")` direkt nach `init_runner_tracing`.
- [ ] SigNoz-Dashboard-Panel: „Logs für aktuellen Trace" als Deep-Link aus dem SimDetail-Panel (Slice 1e) wiederverwendet (`http://localhost:3301/logs?traceID=<id>`).
- [ ] Worklog + STATUS.md + `sync-status.sh` + Single PR.

---

## Akzeptanzkriterien

1. `OTEL_LOGS_ENABLED=false`: Logs gehen weiter an stdout im bisherigen Format (kein Bruch).
2. `OTEL_LOGS_ENABLED=true`: Logs sind JSON, enthalten `trace_id`/`span_id` und sind in SigNoz unter „Logs" suchbar.
3. SimDetail-Panel-Trace-Link zeigt auf Wunsch auch die Logs für diesen Trace.
4. Kein `print()` mehr im Prod-Code-Pfad, der vom Sim-Lifecycle berührt wird.

---

## Risk Register

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| Doppelte Log-Formatter überschreiben sich | Mittel | Logger-Hierarchie + idempotenter Setup mit Module-Cache |
| Subprocess-Logs verlieren `trace_id` | Mittel | `init_runner_logging` muss nach `init_runner_tracing` laufen, da Tracer-Context-Propagation Voraussetzung ist |
| JSON-Logs brechen `tail -f`-Workflow | Niedrig | Pretty-Print-Toggle via `LOG_FORMAT=text\|json`, Default für Dev = `text` |
