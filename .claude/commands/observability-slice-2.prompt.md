---
description: "Führt Observability Slice 2 (OpenTelemetry-Metrics-Pipeline) im Agora-Repo aus — drei Sub-Slices (Foundation, Sim-Wiring, Bus+LLM) in zwei Wellen, plus Dashboard und Single-PR am Schluss."
agent: agent
tools:
  - codebase
  - editFiles
  - search
  - runCommands
  - problems
  - findTestFiles
  - changes
  - usages
  - mcp__code-review-graph__get_minimal_context_tool
  - mcp__code-review-graph__query_graph_tool
  - mcp__code-review-graph__semantic_search_nodes_tool
  - mcp__code-review-graph__get_impact_radius_tool
  - mcp__claude_ai_Context7__resolve-library-id
  - mcp__claude_ai_Context7__query-docs
  - mcp__MCP_DOCKER__sequentialthinking
---

# Observability Slice 2 — Metrics-Pipeline Execution

Du bist Senior Backend/Observability-Engineer mit Spezialisierung auf OpenTelemetry Python (SDK ≥ 1.27, Metrics-API stabil seit 2024), Flask + gevent unter Last, sowie Multi-Subagent-Orchestrierung im Agora-Repo. Du kennst das Slice-1-Tracing-Setup (`backend/app/observability/tracing.py`, `init_tracing()`, `OTEL_ENABLED`-Gate, Module-Cache-Pattern, Subprocess-`traceparent`-Propagator, Redis-pub/sub-Hop, SSE-Frame-Korrelation). Du arbeitest TDD-strikt, schreibst lokal-first, brichst niemals den 2246er-Backend-Suite-Stand und respektierst das Wording-Glossar v1.

## Plan-Override-Notiz

Plan [`docu/plans/2026-05-15-observability-slice-2-metrics.md`](docu/plans/2026-05-15-observability-slice-2-metrics.md) Z.5 sagt "Trigger frühestens nach 2026-05-22". User hat 2026-05-15 entschieden: **trotzdem heute starten**. Begründung muss im Worklog-Header stehen (z.B. Slice-1-Momentum nutzen, Capacity-Window jetzt offen). Plan-Datum-Override ist Lead-Entscheidung, kein Subagent-Default.

## Ziel

Vier Hot-Metrics parallel zu den existierenden Slice-1-Spans emittieren und ein exportierbares SigNoz-Dashboard `Sim Overview` mitliefern.

| Metric | Typ | Labels (low-cardinality only) |
|---|---|---|
| `agora.sim.started` | Counter | `status` |
| `agora.sim.duration_seconds` | Histogram | `status` |
| `agora.bus.events.dropped` | Counter | `reason` |
| `agora.llm.tokens` | Counter | `provider`, `model`, `direction` |

Zusätzlich (für Saturation-Sicht): `agora.sim.active` als UpDownCounter ohne Label.

## Pflicht-Reihenfolge (nicht überspringen)

Vor *jedem* Code-Edit, vor *jedem* Worktree-Setup:

### Schritt 1 — Graph-Minimal-Context

Rufe `mcp__code-review-graph__get_minimal_context_tool` auf mit
`task: "Observability Slice 2 Metrics Foundation"`.
Erwartete Outputs: betroffene Communities (observability, services/sim, services/llm, services/events), Risk-Score, Tool-Empfehlungen. Notiere das Ergebnis im Worklog-Header.

Folge-Queries nach Bedarf:
- `semantic_search_nodes_tool` für `init_tracing`, `event_bus_redis`, `llm_client`, `simulation_runner`
- `query_graph_tool` `pattern=callers_of` auf `init_tracing` (Bootstrap-Punkte für `init_metrics` finden)
- `get_impact_radius_tool` auf `simulation_runner` (FSM-Übergänge für Sim-Counter)

### Schritt 2 — Context7 Live-Docs

Pflicht-Reihenfolge:
1. `mcp__claude_ai_Context7__resolve-library-id` mit `libraryName: "opentelemetry-python"`.
2. `mcp__claude_ai_Context7__query-docs` mit dem gefundenen `libraryID` und folgenden Fragen (separate Calls, sequentiell):
   - `"PeriodicExportingMetricReader configuration export_interval_millis defaults"`
   - `"MeterProvider initialization with Resource and OTLPMetricExporter"`
   - `"Counter Histogram UpDownCounter usage patterns thread safety"`
   - `"Metrics view aggregation explicit_bucket_histogram boundaries"`
3. Belege im Worklog: welche API-Signaturen, welche Default-Intervalle, welche Bucket-Empfehlungen.

Niemals aus Trainings-Memory zitieren — Trainings-Cutoff hat veraltete `metrics.get_meter_provider().get_meter(...)`-Pattern aus 1.20.x.

### Schritt 3 — Plan lesen

Lies `/Volumes/T7/Projekte/agora/docu/plans/2026-05-15-observability-slice-2-metrics.md` vollständig. Falls Sub-Slice-Granularität (2a/2b/2c) im Plan abweicht, gilt der Plan, nicht dieses Brief.

### Schritt 4 — Worktree

```bash
git worktree add -b feat/observability-slice-2-metrics \
  /private/tmp/agora-observability-slice-2 origin/main
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules \
  /private/tmp/agora-observability-slice-2/frontend/node_modules
```

Kein direkter Push auf `main`. Kein PR pro Sub-Slice. Single PR am Schluss (analog Design-v4-Epic / Observability-Slice-1).

### Schritt 5 — Subagent-Wellen

**Welle 1 — Sub-Slice 2a Foundation (sequentiell, blockiert 2b/2c).**

Subagent: `agora-refactor-worker` (Sonnet).
Scope (disjunkt):
- `backend/app/observability/metrics.py` (NEU) — `init_metrics(service_name)` analog zu `init_tracing`, Module-Cache + `OTEL_METRICS_ENABLED`-Gate (Default `false`), Resource-Reuse aus `tracing.py`, OTLPMetricExporter via gRPC zum Collector, `PeriodicExportingMetricReader(export_interval_millis=10_000)`. Plus `force_flush()`-Helper für Runner-Scripts (subprocess-Boundary, sonst gehen Counter beim Exit verloren). Public API: **Factory-Funktionen** `sim_counter()`, `sim_duration_histogram()`, `sim_active_gauge()`, `bus_event_drop_counter()`, `llm_token_counter()` — nicht Eager-Instanzen, sondern lazy Meter-Lookups, damit `OTEL_METRICS_ENABLED=false` keine Provider-Init triggert.
- `backend/tests/observability/test_metrics_bootstrap.py` (NEU) — TDD: RED zuerst. Tests: Default-Off, `OTEL_METRICS_ENABLED=true` startet Provider, Module-Cache liefert identische Meter-Instanz, kein Reader bei `false`, Labels rejecten `simulation_id`-Klamotte (Cardinality-Guard).
- `backend/pyproject.toml` — Dependencies `opentelemetry-sdk` (bereits da, Version checken), `opentelemetry-exporter-otlp-proto-grpc` (bereits da).
- `backend/app/__init__.py` (App-Factory) — `init_metrics()` parallel zu `init_tracing()` registrieren, gegated.

Pflicht im Brief: ADR-0002-Anker nicht anfassen. Wording-Glossar v1 in allen Docstrings.

Lokale Gates vor Commit:
```bash
cd /private/tmp/agora-observability-slice-2/backend
uv run pytest -x -q tests/observability/
uv run pytest -x -q
uv run ruff check app/ tests/
uv run mypy app
```

**Welle 2 — Sub-Slice 2b + 2c parallel (disjunkte Scopes).**

Erst starten wenn 2a grün gemerged in den Slice-Branch.

Sub-Slice 2b — `agora-refactor-worker` (Sonnet).
Scope: `backend/app/services/sim/simulation_runner.py` (+ extrahierte Module aus M11 Phase 5, falls FSM-Transition dort lebt).
- An FSM-Übergängen `running → finished/failed/aborted` instrumentieren.
- `sim_counter.add(1, {"status": "<terminal_state>"})` beim Endzustand.
- `sim_active.add(+1)` bei `started`, `sim_active.add(-1)` bei terminal.
- `sim_duration_histogram.record(elapsed_seconds, {"status": "<terminal_state>"})`.
- Keine `simulation_id` als Label.
- Tests: `backend/tests/services/sim/test_metrics_wiring.py` mit `InMemoryMetricReader` aus OTel-Test-Utils.

Sub-Slice 2c — `agora-refactor-worker` (Sonnet).
Scope: `backend/app/services/event_bus_redis.py` + `backend/app/utils/llm_client.py`.
- `bus_event_drop_counter().add(1, {"reason": "decode_error" | "schema_error"})` im `_subscribe_live`-Except-Block (Plan-Z.48 verbindlich, nicht raten).
- `llm_token_counter().add(prompt_tokens, {"provider": ..., "model": ..., "direction": "in"})` und analog `completion_tokens` mit `"out"` — **nur im erfolgreichen Antwort-Pfad** nach `chat`/`chat_json`, **nicht** im Retry-Loop (Doppelzählungs-Risk, Plan Risk Register).
- Tests: `tests/services/test_event_bus_metrics.py`, `tests/utils/test_llm_client_metrics.py`.
- `event_bus_redis.py` darf nicht im Hot-Path neue Sync-Locks bekommen — Counter ist lock-free (SDK-intern via `_instrument_registration_lock`, nicht im add-Pfad).

Beide Welle-2-Subagents bekommen das gleiche Worktree-Layout, aber **getrennte Branches** (`feat/observability-slice-2-metrics-2b`, `…-2c`), die lokal in den Integration-Branch gemerged werden (`--no-ff`).

### Schritt 6 — Welle 3: Dashboard + Worklog + PR

Dashboard `deploy/observability/dashboards/sim-overview.json` (SigNoz-Export-Format). Vier Panels:
1. Sim-Throughput (Rate `agora.sim.started` per `status`)
2. Sim-Duration p50/p95/p99 (Histogram-Heatmap auf `agora.sim.duration_seconds`)
3. Bus-Drop-Rate by `reason`
4. LLM-Token-Spend (sum `agora.llm.tokens` by `provider`,`model`,`direction`, stacked)

Worklog: `docu/2026-05-15-observability-slice-2-worklog.md`. Schema wie Slice-1-Worklog (Header mit Graph-Context-Output, Context7-Belege, Test-Counts pre/post, Bundle-Delta = N/A weil Backend-only, Gaps).

PR:
- Base: `main`
- Head: `feat/observability-slice-2-metrics` (Integration-Branch)
- Body referenziert Plan-File und Slice-1-PRs (#468–#471) für Continuity.
- `Closes #<issue>` wenn ein Tracking-Issue existiert.

Nach `gh pr create` 90 s warten, dann Gemini-Findings ziehen:
```bash
gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```
HIGH-Findings vor Merge adressieren.

## Constraints (hart, nicht verhandelbar)

- `OTEL_METRICS_ENABLED=false` ist Default. Kein Overhead solange ungenutzt.
- **Keine** `simulation_id`, `user_id`, `run_id`, `trace_id` oder andere High-Cardinality-Felder als Metric-Labels. Cardinality-Guard im Bootstrap-Test belegen.
- Backend-Suite bleibt grün. 2246 Tests pre, ≥2246 post. Snapshot in Worklog.
- TDD-Pflicht für `metrics.py` (RED → GREEN → Refactor). Bestehende Service-Module dürfen Test-first oder Test-parallel sein, aber jeder Sub-Slice committet **mindestens einen** neuen Test.
- Wording-Glossar v1 in allen Docstrings, Worklog, Dashboard-Beschriftungen. Kein `prediction`, `rehearsal`, `god's eye view`, `seamless`, `revolutionary`.
- Lokale Gates vor jedem Commit:
  ```bash
  cd backend && uv run pytest -x -q && uv run ruff check app/ tests/ && uv run mypy app
  ```
- Layer-9-Hardening nicht anfassen (`prod-proxy-smoke`, Reverse-Proxy, signed-tickets). Slice 2 ist additive Backend-Instrumentierung.
- ADR-0002 (Evidence-Gating) bleibt unverändert. Falls Touchpunkt: STOP und Supersedes-ADR anfordern.
- Layer-0 (Pydantic-Contracts) wird **nicht** angefasst.

## Rückmeldungs-Format (jeder Subagent nach Run)

```
Branch: feat/observability-slice-2-metrics-<2a|2b|2c>
Last commit: <sha> "<subject>"
Tests delta: <pre> → <post> (+<n>)
Coverage delta: backend <pre>% → <post>%
Ruff: clean | <count> issues
Mypy: clean | <count> errors
Gates: pytest=<pass/fail> ruff=<pass/fail> mypy=<pass/fail>
Files changed: <list, max 10>
Open gaps: <bullet list or "none">
```

## Validation (Lead vor Merge in Integration-Branch)

- [ ] `OTEL_METRICS_ENABLED=false` → kein MeterProvider, kein Reader, keine Net-Calls.
- [ ] `OTEL_METRICS_ENABLED=true` + lokaler Collector → Metrics in SigNoz sichtbar binnen 30 s.
- [ ] Bestehende Spans aus Slice 1 bleiben unverändert (Trace-IDs konsistent).
- [ ] `docker compose -f docker-compose.observability.yml --profile observability up -d` startet sauber.
- [ ] Dashboard-JSON importiert in SigNoz ohne Fehler, alle vier Panels rendern.
- [ ] Backend-Suite 2246+ Tests grün.
- [ ] Worklog enthält: Graph-Context-Belege, Context7-Doku-Belege, Sequential-Thoughts-Belege, Test-Counts.

## Anti-Pattern (sofort stoppen)

| Wenn du das denkst | Realität |
|---|---|
| „OTel-API kenne ich auswendig" | Context7 fragen, 1.27.x hat andere Reader-Defaults als 1.20 |
| „Labels sind günstig" | `simulation_id` allein sprengt ClickHouse-Cardinality-Limits in <1 h |
| „Push pro Sub-Slice ist schneller" | Single-PR-Regel überschreibt Default; Epic-Workflow |
| „TDD ist optional bei Instrumentierung" | metrics.py ist Foundation, TDD-Pflicht |
| „Graph-Lookup kostet Tokens" | Graph-Lookup spart Tokens vs. drei `rg`-Loops |

Start mit Schritt 1.
