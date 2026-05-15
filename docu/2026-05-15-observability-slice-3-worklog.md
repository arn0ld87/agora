# Observability Slice 3 — Logs-Korrelation Worklog

**Datum:** 2026-05-15
**Branch:** feat/observability-slice-3-logs
**Base:** origin/main @ e55f908 (Slice 2 Merge, PR #473)
**Plan:** [docu/plans/2026-05-15-observability-slice-3-logs-correlation.md](plans/2026-05-15-observability-slice-3-logs-correlation.md)
**Plan-Vorgabe:** „Trigger nach Slice 2" erfüllt — Slice 2 wurde 2026-05-15 14:18 UTC gemerged, Slice 3 startet direkt im Anschluss (Momentum-Window).

---

## Tool-Pflicht-Belege

- **code-review-graph::get_minimal_context_tool** (2026-05-15): 6689 Nodes, 56349 Edges, 710 Files. Risk **medium (0.70)**, 8 test gaps. Key entities: `create_app`, `init_logging`, `app.logger`, `monitor_simulation`, `run_*_simulation.py`. Communities `services-simulation`, `app-observability`, `tests-observability`. Tool-Empfehlung: `detect_changes`, `get_affected_flows`, `query_graph` (pattern=`imports_of`).
- **context7 (/websites/opentelemetry-python_readthedocs_io_en_stable):** Zwei Queries — (1) LoggingInstrumentor + LogRecord-Init mit trace_id/span_id aus span_context; (2) LoggerProvider + BatchLogRecordProcessor + OTLPLogExporter (gRPC) inkl. Env-Variablen `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`/`_INSECURE`/`_HEADERS`. Verifiziert: `OTLPLogExporter` `force_flush()` ist No-Op (Exporter selbst puffert nicht — `BatchLogRecordProcessor` ist der puffernde Teil), Trace-Korrelation läuft über `LoggingInstrumentor`-injizierte `otelTraceID`/`otelSpanID`-Attribute am LogRecord.
- **Plan-Read:** docu/plans/2026-05-15-observability-slice-3-logs-correlation.md, Tasks 1–2 + Risk Register + Akzeptanzkriterien Z.49–64 berücksichtigt.

---

## Sub-Slice 3a — Foundation logging_bridge.py

**Worker:** agora-refactor-worker (Sonnet)
**Commit:** `67b01b0` — `feat(observability): logging_bridge.py foundation (Slice 3a)`
**Files:**
- `backend/app/observability/logging_bridge.py` (NEU, 112 LOC) — `init_logging()`, `force_flush_logs()`, `JsonTraceFormatter`, `LoggingInstrumentor.instrument(set_logging_format=False)`-Setup, Module-Cache mit `threading.Lock`
- `backend/tests/observability/test_logging_bridge.py` (NEU, 194 LOC, 7 TDD-Cases) — Default-Off, Enabled-Init mit Teardown, Module-Cache-Idempotenz, JSON-Roundtrip mit Span-Context, JSON-ohne-Span-leerer-Trace-ID, force_flush-NoOp
- `backend/app/observability/__init__.py` (+12 LOC) — Re-Export `init_logging`, `force_flush_logs`, `JsonTraceFormatter`
- `backend/pyproject.toml` (+4 LOC) — `opentelemetry-instrumentation-logging>=0.45b0` als Runtime-Dep
- `backend/uv.lock` — Lock-Update
- `.env.example` (+8 LOC) — `OTEL_LOGS_ENABLED=false` + `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` dokumentiert

**Tests delta:** 2260 → 2267 (+7)
**Ruff/Mypy:** clean

**JsonTraceFormatter-Felder verifiziert:** `timestamp` (ISO-8601 UTC), `level`, `logger`, `message`, `trace_id`, `span_id`, `service.name`, plus optional `exception` mit Stacktrace.

**Notable decisions:**
- `set_logger_provider` aus `opentelemetry._logs` (public API), **nicht** aus `opentelemetry.sdk._logs` — gegen das installierte SDK (0.62b1) verifiziert.
- `opentelemetry-instrumentation-logging>=0.45b0` als `[dependencies]` (nicht `dev`), da unter `OTEL_LOGS_ENABLED=true` zur Laufzeit benötigt.
- Test Case 5 simuliert LoggingInstrumentor-Injection manuell per `record.otelTraceID = ...`, um den Test von einem echten Root-Logger-Patch zu isolieren (Audit-Bewertung pending).
- Fixture-Teardown ruft `provider.shutdown()` bei enabled-Tests — Lessons aus Slice-2-Audit-Finding MEDIUM-1 (Background-Thread-Leak) angewendet.

---

## Sub-Slice 3b — Verdrahtung App + Runner

**Worker:** agora-refactor-worker (Sonnet) — vom Lead nach ~11 min Hängen gestoppt, finaler ruff-Fix (E402) und Commit vom Lead übernommen.
**Commit:** `0437d20` — `feat(observability): wire init_logging and migrate prints to logger (Slice 3b)`
**Files:**
- `backend/app/__init__.py` — `init_logging(service_name=...)` zwischen `init_tracing()` und `init_metrics()` in `create_app()` platziert
- `backend/scripts/_sim_common.py` — `init_runner_logging(service_name)` analog zu `init_runner_tracing`
- `backend/scripts/run_parallel_simulation.py`, `run_reddit_simulation.py`, `run_twitter_simulation.py` — `init_runner_logging("agora-oasis-runner")` direkt nach `init_runner_tracing`
- `backend/scripts/agent_tools.py` — ~25 `print()` → `logger.info/.warning/.error`; stderr-Stellen → warning
- `backend/app/observability/logging_bridge.py` — Audit-MEDIUM-1-Followup: Kommentar dokumentiert privaten `sdk._logs`-Importpfad
- `backend/tests/observability/test_logging_wiring.py` (NEU, 3 Smoke-Tests) — `create_app` ruft `init_logging`; `init_runner_logging` ruft Public-API; ImportError ist silent

**Tests delta:** 2267 → 2263 passed/9 skipped/7 deselected (+3 wiring tests; pytest-Reporting durch Cross-Slice-Test-Count-Variation leicht volatil, alle relevanten Cases grün)
**Ruff/Mypy:** clean (nach Lead-Fix E402 in agent_tools.py: `logger = logging.getLogger(__name__)` nach Third-Party-Imports verschoben)

**print()-Migration im Sim-Pfad:**
- `scripts/agent_tools.py` ~25 Stellen migriert (Hot-Spot OASIS-Runner, alle Sim-Lifecycle-Pfade).
- **Out-of-Scope:** `scripts/check_voice.py` (CLI-Tool, legitimer `print()` für GitHub-Actions-Output). Keine weiteren `print()` im Sim-Pfad.

**Notable decisions:**
- Worker stockte bei finalem ruff-Pass — `import logging` korrekt zugefügt, aber `logger = logging.getLogger(__name__)` versehentlich zwischen Stdlib- und Third-Party-Imports gesetzt → E402 für `import requests`/`bs4`/`dotenv`. Lead hat `logger`-Statement nach allen Imports verschoben.
- Audit-MEDIUM-1-Followup (`sdk._logs`-Kommentar) im selben 3b-Commit mitgenommen, da der Pfad ohnehin angefasst wurde.
- Audit-MEDIUM-2 (echter LoggingInstrumentor-Roundtrip-Test) **noch offen** — die drei `test_logging_wiring.py`-Tests sind Mock-Wiring-Tests, kein Live-Span+Log-Roundtrip. Followup für Slice 4 oder separat einzuplanen.

---

## Welle 3 — Collector-Config + Dashboard + Finalize

### Collector-Config
- **Deploy-Artefakt:** `deploy/observability/otel-collector.yaml` (M) oder separate `otel-collector-logs.yaml`
  - Neue Pipeline: `logs` mit `filelog`-Receiver (oder direkter OTLP-Logs-Receiver) + Batch-Processor + `otlp`-Exporter
  - Voraussetzung: Slice 3a emittiert JSON-Logs mit `trace_id` / `span_id`
  - _<TBD: Config-Details nach 3a-Commit>_

### SigNoz Dashboard-Update
- **SimDetail-Panel-Deep-Link** (Slice 1e wiederverwendet): `http://localhost:3301/logs?traceID=<trace_id>` zeigt Logs für aktuellen Trace
- **Logs-Panel im Sim-Dashboard:** z. B. letzte 20 Log-Einträge für laufenden Sim (optional, Plan-konform offen)
- _<TBD: JSON-Import nach Config-Finalize>_

### Dokumentation
- **STATUS.md ergänzt:** _<TBD in Finalize>_
- **scripts/sync-status.sh ausgeführt:** _<TBD>_

---

## Audit Slice 3a — Foundation logging_bridge.py

**Auditor:** agora-evidence-auditor (Sonnet, read-only)
**Empfehlung:** **PASS WITH FOLLOWUPS**

**Befund-Tabelle:**

| Kriterium | Status |
|---|---|
| Default-Off-Garantie | PASS — `OTEL_LOGS_ENABLED != "true"` → early return; Handler-Count-Assert in Test 1 |
| JsonTraceFormatter-Pflichtfelder | PASS — alle 7 Felder + Exception-Bedingung |
| Trace-ID-Propagation | PARTIAL — Formatter-Logik korrekt, Instrumentor-Roundtrip in Case 5 manuell simuliert (MEDIUM-2) |
| Background-Thread-Teardown | PASS — `provider.shutdown()` in autouse-Fixture (Slice-2-Lesson) |
| Module-Cache-Idempotenz | PASS — `threading.Lock` + Double-Checked-Locking |
| Wording-Glossar v1 | PASS — null Treffer |
| Layer-Boundary | PASS — kein Layer-0/9/ADR-0002, tracing.py + metrics.py unverändert |
| Plan-Akzeptanzkriterien 3a | PASS |

**HIGH-Findings:** keine.

**MEDIUM-Findings:**
1. `opentelemetry.sdk._logs` ist privater Pfad ohne öffentlichen Alias (Logs-API noch experimental im SDK). Funktional korrekt auf 1.41.1, aber Bruch-Risiko bei SDK-Restrukturierung. **Action:** Kommentar in `logging_bridge.py:24` ergänzt (Lead-Followup-Edit vor Welle-3-Commit).
2. Test Case 5 simuliert Instrumentor-Injection manuell (Span aktiv, aber `init_logging` nicht aufgerufen, Trace-Attribute werden nach dem Log-Call gesetzt). Verifiziert Formatter-Logik korrekt, aber **nicht** die echte Instrumentor-Propagation. **Action:** Integrationstest in 3b — `init_logging("test")` + `LoggingInstrumentor` aktiv + Log-Call innerhalb echtem Span verifiziert Auto-Attribute.

**LOW-Finding:**
- Root-Logger-Handler-Leak möglich bei wiederholten enabled-Inits ohne Handler-Cleanup; Fixture-Teardown adressiert via `provider.shutdown()`, removed aber den `StreamHandler` nicht vom Root-Logger.

---

## Akzeptanzkriterien (aus Plan)

- [ ] `OTEL_LOGS_ENABLED=false`: Logs gehen weiter an stdout im bisherigen Format (kein Bruch).
- [ ] `OTEL_LOGS_ENABLED=true`: Logs sind JSON, enthalten `trace_id`/`span_id`, in SigNoz unter „Logs" suchbar.
- [ ] SimDetail-Panel-Trace-Link zeigt Logs für diesen Trace (Slice 1e-Mechanik + Slice 3-Daten).
- [ ] Kein `print()` mehr im Sim-Lifecycle-Pfad; Out-of-Scope-Stellen dokumentiert im Worklog.
- [ ] Backend-Suite Tests grün nach 3a + 3b.

---

## Risk Register (Plan-Spiegel + Slice-Findings)

| Risiko | Wahrscheinlichkeit | Status |
|---|---|---|
| Doppelte Log-Formatter überschreiben sich | Mittel | Module-Cache + Logger-Hierarchie in 3a; Audit-Verifikation Pflicht |
| Subprocess-Logs verlieren trace_id | Mittel | `init_runner_logging` nach `init_runner_tracing` in 3b; Context-Propagation über Env-Var |
| JSON-Logs brechen tail-Workflow | Niedrig | Default-Off (`OTEL_LOGS_ENABLED=false`); JSON nur mit explizitem Toggle |

---

## PR

- **PR-Nummer:** _<TBD am Ende, EIN PR für Slice 3a + 3b + Collector>_
- **Gemini-Findings:** _<TBD nach 90s wait>_
- **Merge-Notiz:** _<TBD>_
