# Observability Slice 2 — Metrics-Pipeline Worklog

**Datum:** 2026-05-15
**Branch:** feat/observability-slice-2-metrics
**Base:** origin/main @ c3a3e00 (Slice 1 Merge, PRs #468–#471)
**Plan:** [docu/plans/2026-05-15-observability-slice-2-metrics.md](plans/2026-05-15-observability-slice-2-metrics.md)
**Plan-Override:** Plan-Datum „Trigger frühestens 2026-05-22" am 2026-05-15 vom Lead überstimmt. Begründung: Slice-1-Momentum nutzen, Capacity-Window jetzt offen, keine Layer-9-Hardening-Re-Validation nötig.

---

## Tool-Pflicht-Belege

- **code-review-graph::get_minimal_context_tool** (2026-05-15): 6689 Nodes, 56349 Edges, 710 Files. Risk **low (0.00)**. Communities `services-simulation`, `tests-returns`, `tests-wenn`. Flows `goReport`, `initProject`, `doStart`. Tool-Empfehlung: `detect_changes`, `semantic_search_nodes`, `get_architecture_overview`.
- **context7 (/websites/opentelemetry-python_readthedocs_io_en_stable):** Drei Queries — (1) MeterProvider-Init + PeriodicExportingMetricReader + OTLPMetricExporter; (2) Counter/Histogram/UpDownCounter-Usage + Thread-Safety; (3) View + ExplicitBucketHistogramAggregation. Verifiziert: `export_interval_millis` Default 60000 (Env-Override `OTEL_METRIC_EXPORT_INTERVAL`), `OTLPMetricExporter(endpoint="localhost:4317", insecure=True, max_export_batch_size=512)`, Instrument-Registration via `_instrument_registration_lock` (thread-safe, idempotent).
- **Plan-Read:** docu/plans/2026-05-15-observability-slice-2-metrics.md, Tasks 1–3 sowie Risk Register Z.71–77 berücksichtigt.

---

## Sub-Slice 2a — Foundation

**Worker:** agora-refactor-worker (Sonnet)
**Commit:** `24fbc9f` — `feat(observability): metrics.py foundation (Slice 2a)`
**Files:**
- `backend/app/observability/metrics.py` (NEU, 182 LOC) — `init_metrics()`, `force_flush()`, `_build_views()`, fünf Factories
- `backend/tests/observability/test_metrics.py` (NEU, 231 LOC, 8 TDD-Cases)
- `backend/app/observability/__init__.py` — Re-Export aller Metrics-Symbole
- `backend/app/__init__.py` — App-Factory: `init_metrics(service_name=...)` parallel zu `init_tracing()`
- `.env.example` — `OTEL_METRICS_ENABLED=false`, `OTEL_METRIC_EXPORT_INTERVAL` dokumentiert

**Tests delta:** 2240 → 2248 (+8)
**Ruff/Mypy:** clean (171 source files via mypy)

**Notable decisions:**
- `frozenset` → `set` für View `attribute_keys`: mypy-OTel-Stubs deklarieren `set[str] | None`, nicht `AbstractSet`. Laufzeitverhalten identisch.
- Test-Fixture `metrics_provider` nutzt `monkeypatch.setattr` auf `_provider`/`_meter` statt OTel-Global-Registry-Reset — verhindert Cross-Test-Kontamination ohne `metrics.set_meter_provider()`-Reset.
- `test_enabled_initializes_provider` startet echten PeriodicExportingMetricReader-Background-Thread mit OTLP-Export-Versuch auf `localhost:4317`. Logs UNAVAILABLE, kein Test-Failure (Test prüft nur `_provider is not None`).

---

## Sub-Slice 2b — Sim-Wiring

**Worker:** agora-refactor-worker (Sonnet)
**Commit:** `d816e9f` — `feat(observability): wire sim-lifecycle metrics (Slice 2b)`
**Files:**
- `backend/app/services/sim/process_manager.py` — Import `sim_active_gauge`, `sim_counter`; PENDING→RUNNING-Transition +2 Instrument-Calls
- `backend/app/services/sim/monitor.py` — Import der drei Factories; `_compute_elapsed_seconds()`-Helper; COMPLETED/FAILED/Exception-Pfad je +3 Calls
- `backend/tests/services/sim/test_metrics_wiring.py` (NEU, 5 Tests)

**Tests delta:** 2251 → 2256 (+5)
**Ruff/Mypy:** clean

**FSM-Transitions instrumentiert:**
- `process_manager.py:311-312` — PENDING → RUNNING: `sim_active_gauge().add(1)`, `sim_counter().add(1, {"status": "started"})`
- `monitor.py:135-139` — RUNNING → COMPLETED: gauge −1, counter `done`, histogram
- `monitor.py:148-152` — RUNNING → FAILED (exit_code ≠ 0): gauge −1, counter `failed`, histogram
- `monitor.py:162-165` — RUNNING → FAILED (Exception-Pfad): identisch

**Notable decisions:**
- M11 Phase 5 hat `simulation_runner.py` aufgespalten — Worker hat das via Graph erkannt und die FSM-Transitions in den extrahierten Modulen (`process_manager.py`, `monitor.py`) instrumentiert, nicht im Orchestrator.
- `_compute_elapsed_seconds()` als Helper in `monitor.py` extrahiert (dreimalige Wiederverwendung in DONE/FAILED/Exception-Pfad).

---

## Sub-Slice 2c — Bus + LLM

**Worker:** agora-refactor-worker (Sonnet)
**Status:** _<läuft noch, Stand 2026-05-15 16:00>_
**Files (in-flight, uncommitted):**
- `backend/app/services/event_bus_redis.py` (M)
- `backend/app/utils/llm_client.py` (M)
- `backend/tests/services/test_event_bus_metrics.py` (??)
- `backend/tests/utils/test_llm_client_metrics.py` (??)

**Tests delta:** _<TBD nach Commit>_

---

## Audit Slice 2a — Foundation

**Auditor:** agora-evidence-auditor (Sonnet, read-only)
**Empfehlung:** **PASS WITH FOLLOWUPS**

**Befund-Tabelle:**

| Kriterium | Status |
|---|---|
| Cardinality-Guard via View-Whitelist | PASS mit WARN (set statt frozenset) |
| Default-Off-Garantie | PASS (`metrics.py:97` early return) |
| Force-Flush exportiert + NoOp wenn disabled | PASS (`metrics.py:131-142`) |
| Wording-Glossar v1 | PASS (null Treffer) |
| Plan-Akzeptanzkriterien | PASS mit WARN |
| Notable Decisions | WARN (Background-Thread-Teardown fehlt) |
| Layer-Boundary | PASS (kein Layer 0/9/ADR-0002-Touch) |

**HIGH-Findings:** keine.

**MEDIUM-Findings:**
1. **Background-Thread ohne Teardown** (`test_metrics.py:130-140`, `:148-159`): `test_enabled_initializes_provider` + `test_module_cache_idempotent` rufen kein `provider.shutdown()` in Fixture-Teardown. Background-Thread lebt nach Testende weiter. **Action:** Followup-Fix vor PR-Erstellung (Task #9).
2. **`set()` statt `frozenset` für leere Whitelist** (`metrics.py:69` für `agora.sim.active`): mutable, theoretisch durch Caller modifizierbar. Heute kein aktiver Bug.
3. **Keine Roundtrip-Tests für 3 von 5 Factories** (`bus_event_drop_counter`, `llm_token_counter`, `sim_active_gauge`): Plan-konform, aber Risk für Welle 2 Verdrahtung. **Mitigation:** 2b + 2c bringen jeweils eigene Roundtrip-Tests mit.

**LOW-Findings:**
- `agora.sim.active` als Bonus implementiert, nicht in Plan Z.64 gelistet.
- LOC-Inkonsistenz im Audit-Header (182 vs. 222 tatsächlich).

---

## Welle 3 — Dashboard + Worklog-Finalisierung

- **Dashboard:** `deploy/observability/dashboards/sim-overview.json` (NEU, 10979 Bytes, 5 Panels: Sim Throughput, Sim Duration p50/p95/p99, Bus Event Drops, LLM Token Spend, Active Sims). SigNoz v4 Schema. JSON-valid.
  - Open gap: `aggregateOperator`-Strings (rate, hist_quantile_*, sum_rate, latest) bei manuellem SigNoz-Import einmalig durchklicken/re-exportieren, falls SigNoz CE 0.51 abweichende Operator-Namen erwartet.
- **STATUS.md ergänzt:** _<TBD in Welle 3 Finalize>_
- **scripts/sync-status.sh ausgeführt:** _<TBD>_

---

## Akzeptanzkriterien (aus Plan)

- [x] `OTEL_METRICS_ENABLED=false`: keine Emission, Sim-Performance unverändert (Default-Off in 2a via early return belegt).
- [ ] `OTEL_METRICS_ENABLED=true`: SigNoz zeigt 4 Series (`agora.sim.started`, `agora.sim.duration_seconds`, `agora.bus.events.dropped`, `agora.llm.tokens`) — Verifikation nach 2c-Commit + manuellem Sim-Run pending.
- [x] Backend-Suite Tests grün — 2256+ nach 2b (Baseline 2240 vor 2a).
- [x] Dashboard-JSON importierbar (JSON-Syntax verifiziert, SigNoz-Roundtrip pending).

---

## Risk Register (Plan-Spiegel + Slice-Findings)

| Risiko | Wahrscheinlichkeit | Status |
|---|---|---|
| PeriodicExportingMetricReader Memory unter gevent | Niedrig | Akzeptiert; Export-Interval 10s konservativ; lokaler Collector ohne Backpressure |
| LLM-Token-Counter doppelt gezählt bei Retry | Mittel | 2c-Brief Pflicht: nur Success-Path inkrementieren; Test `test_retry_does_not_double_count` Pflicht |
| Cardinality-Explosion bei Labels | Niedrig | View-Whitelist hardcoded in `_build_views()`; Audit-bestätigt strukturell |
| Background-Thread-Leak in Foundation-Tests | Mittel | Audit-Finding M1; Followup-Fix Task #9 vor PR |

---

## PR

- **PR-Nummer:** _<TBD am Ende, EIN PR analog Slice 1>_
- **Gemini-Findings:** _<TBD nach 90s wait>_
- **Merge-Notiz:** _<TBD>_
