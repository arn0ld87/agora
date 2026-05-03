# Agora Roadmap

> Stand: 2026-05-03. Verbindliche Test-Counts und Layer-Status: [`docu/STATUS.md`](STATUS.md). Layer-Detailtabelle: [`CLAUDE.md`](../CLAUDE.md#architektur-layer-status). Operative Tasks: [`PLAN.md`](../PLAN.md). Versions-Historie und Detail-Backlog: `docu/refactoring-backlog-priorisiert.md`, `docu/p0-arbeitsprotokoll.md`, `CHANGELOG.md`.

## Current State (v0.9.0+ post-tag, Layer 0–6 grün)

Fully local fork on Neo4j CE + Ollama, no Zep Cloud dependency. Core pipeline works end-to-end: upload → graph build → persona generation → multi-agent OASIS simulation → report.

Reader-Honesty-Refactor (Sub-Slices 02–17, Layer 0–5) und Frontend-TypeScript-Migration (Sub-Slices 26–28, Layer 6) sind durch. Die 0.5/0.6-Linien-Historie steht weiter unten unter [§ Historie](#historie-050--06).

---

## Now / Next / Later

### Now — Milestone M9 (Prod-Hardening, Mai 2026, Slices F1–F5)

Übergang von v0.9.0-Release + Reader-Honesty-Refactor zu stabiler Production-Ready-Vorbereitung (Layer 9 Deployment, SSE-Auth, Reverse-Proxy). Detail: [`PLAN.md` § Milestone M9](../PLAN.md).

- **F5 Doku-Sync** (Sub-Slice 44, **diese Woche**): Status.md als Single Source of Truth, ROADMAP v0.9.0+ / 2026-05-03, CONTRIBUTING.md Repo-Root, Inline-Zahlen aus README/CLAUDE.md entfernt.
- **F1 Reverse-Proxy** (Sub-Slice 45): Saubere Verdrahtung eines Reverse-Proxy (nginx / HAProxy) vor dem Prod-Container; Auth-Token-Termination auf Proxy-Ebene, X-Forwarded-{For,Host,Proto}-Handling, Zero-Downtime-Reload.
- **F2 Auth-Hardening** (Sub-Slices 46–47): Signed-Ticket-API (`POST /api/auth/ticket`) statt URL-Token-Fallback (#106 Refs); Frontend-Migration auf Ticket-Header; Redis-Session-Store für SSE.
- **F3 Gunicorn-Gevent** (Sub-Slice 48): Worker-Modell von sync+`--timeout 600` auf `-k gevent` umstellen; OASIS-Subprozess-Entkopplung verifizieren, Fork-Safety-Tests für Neo4j/Redis-Pools.

### Next — Milestone M10 (Test-Schärfe + CVE-Watch, Juni 2026)

Erhöhen der Coverage und automatisierte Security-Überwachung.

- **F6 Coverage** (Sub-Slices 49–50): Backend- und Frontend-Coverage auf >85 % heben; untestete Pfade identifizieren und mit gezielten Tests schliessen.
- **F12 Lint-Tiefe** (Sub-Slice 51): zusätzliche ruff-Rules (Bandit-Integration für Security-Checks), mypy-Strict-Modus für neue Module.
- **F4 CVE-Monitor** (Sub-Slice 52): Automated pip-audit + npm-audit in CI; CVE-Tracking-Arbeitsprotokoll; Upstream-Pin-Strategie dokumentieren.

### Later — Milestones M11–M13 (Code-Hotspots, Feature-Welle, v1.0-Vorbereitung)

- **M11 (Code-Hotspots, Juli 2026)**: Refactor kritischer Module (evidence_binder, confidence_calculator, report_agent Pro-Reorg); Multi-Model-Router; Custom-NER-Plugins.
- **M12 (Feature-Welle, August 2026)**: Graph-Versioning (Snapshots), Branch-Compare-UI, Persona-Review-UX-Polish, Export-Templates (custom Markdown/PDF).
- **M13 (v1.0-Vorbereitung, September 2026)**: Helm-Chart, E2E-Test-Suite (Playwright), Performance-Benchmarks, Federation-Groundwork.

## Historie (0.5 / 0.6)

Die 0.5 line shipped six prioritized issues (#13 → #14 → #9 → #10 → #12 → #11 Phase 1). The 0.6 line added LLM retry resilience, frontend defensive error handling, default-strict ruff scope, NER → ontology-mutation wiring (#11 Phase 2), RPC/Interview-IPC over Redis Pub/Sub (#17), and the 0.6.x dependency/docs hygiene wave (Stand vor 2026-05-03).

### Implemented (v0.5.0 + unreleased)

- **Quality gates** — `npm run check` runs default-strict ruff on `app/ tests/`, pytest (207 passed, 2 Redis integration skips without `TEST_REDIS_URL`), frontend lint, frontend build.
- **DI container (#14)** — `AgoraContainer` with singletons (`neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`, `ontology_mutation_service`) and request-scoped factories (`graph_builder`, `temporal_graph`, `network_analytics`).
- **Event bus + SSE (#9)** — `SimulationEventBus` with `InMemoryEventBus`, `FilePollingEventBus`, `RedisEventBus`. SSE endpoint `GET /api/simulation/<id>/stream` replaces 2.5s status polling.
- **Temporal graph (#10)** — relation edges carry `valid_from_round`, `valid_to_round`, `reinforced_count`. APIs `GET /api/graph/snapshot/<gid>/<round>` and `GET /api/graph/diff/<gid>?...`.
- **Polarization metrics (#12)** — `NetworkAnalyticsService` with Louvain communities, echo-chamber index, betweenness-based bridge agents. API `GET /api/simulation/<id>/metrics`.
- **Ontology mutation (#11 Phase 1+2)** — `OntologyManager` (thread-safe per-graph locks) + `OntologyMutationService` (`disabled` / `review_only` / `auto`). NER pipeline forwards novel entity types automatically; service exceptions never block ingestion.
- **LLM resilience** — `LLMClient.chat` / `describe_image` retry on transient upstream failures (`APIConnectionError`, `APITimeoutError`, `RateLimitError`, `APIStatusError` 5xx/408/429) via `llm_call_with_retry`.
- **Operability** — `/api/status`, request-IDs, atomic JSON writes (`utils/json_io.py`), Neo4j call retry, fail-fast embedding-config validation.

---

## Near Term

### v0.6.1 — RPC migration + frontend hygiene

Schließt die letzten Loose Ends der 0.5-Saga und macht das Frontend Production-tauglich.

- [x] **Issue #17 — RPC/Interview-IPC auf Redis Pub/Sub** (abgeschlossen). Backend `RedisEventBus` und alle drei OASIS-Subprocess-Scripts laufen jetzt hybrid (Redis Pub/Sub + File-Fallback); `RedisIPCBridge` im OASIS-Eventloop, Backend-side `_await_response` race't beide Quellen.
- [x] **Frontend Round-Slider** für Temporal-Graph-Snapshots (#10 optional, abgeschlossen). `GraphRoundSlider.vue` lebt im `GraphPanel`, blendet sich automatisch ein sobald der Graph mindestens eine Simulationsrunde gesehen hat. Filter läuft client-seitig (`filterEdgesAtRound`); `getGraphSnapshot`/`getGraphDiff` für späteren server-side Bedarf bereitgestellt.
- [x] **Workspace-Layout-Shell** (EPIC-03 ST-01). `WorkspaceLayout`/`WorkspaceHeader`/`WorkspaceSplit`/`WorkspaceBrandLink`/`WorkspaceModeSwitch`/`WorkspaceStepStatus` (`frontend/src/layouts/`) sind die gemeinsame Shell für `MainView`/`SimulationView`/`SimulationRunView`/`ReportView`/`InteractionView`.
- [x] **Workspace-State-Composables** (EPIC-03 ST-02 + ST-03). `useWorkspaceMode` (viewMode + Panel-Styles + toggleMaximize + workspaceModes) und `useWorkspaceStatus` (currentStatus + konfigurierbares Status-Mapping zu kind/text) liegen unter `frontend/src/composables/`. Alle 5 Pipeline-Views konsumieren `useWorkspaceMode`; SimulationView/ReportView/InteractionView zusätzlich `useWorkspaceStatus`. SimulationRunView behält paused-Overlay-Logik bewusst eigenständig, MainView phasen-basierte Status-Logik ebenfalls.
- [x] **Frontend-Warnungen abbauen** — Vue/Vite-Build und ESLint laufen aktuell warning-frei (`npm run check` exit=0). Falls neue Warnings auftauchen, im Folgeticket erfassen.
- [x] **Hybrid-Search-Weights konfigurierbar** — `Config.HYBRID_SEARCH_VECTOR_WEIGHT` / `Config.HYBRID_SEARCH_KEYWORD_WEIGHT` (Defaults 0.7 / 0.3 wie bisher), `SearchService` nimmt sie per Constructor-Argument, `Neo4jStorage` reicht sie aus der Config durch. Pro Graph noch nicht (das wäre ein größerer Schnitt — Folgeticket).
- [x] **Dependency-/Doku-Hygiene** — Frontend-Advisories für `axios` / `follow-redirects` / `postcss` per kompatiblem `npm audit fix` bereinigt, `/api/status` nutzt die zentrale App-Version, README/Roadmap-Testzahlen aktualisiert.

### v0.7.0 — Multi-model + persona governance

- [ ] **Model router** — assign different Ollama models to different tasks (fast model for NER, large model for reports).
- [ ] **Persona Review Flow** (Backlog EPIC-13) — gate before simulation start: review, edit, approve, regenerate single personas.
- [ ] Quantization-aware config: auto-select context window based on available VRAM.
- [ ] Multi-language simulation support (agents interacting in different languages on the same graph).

### v0.8.0 — API contracts + observability

- [ ] **Standardized API error/response envelopes** (Backlog EPIC-09). Currently `success`/`data`/`error` lives in spirit but not enforced.
- [ ] **Run dashboard** (Backlog EPIC-11) — operative transparency over the run registry: queue depth, per-stage success rate, latency histograms.
- [ ] **TypeScript for API models** (Backlog EPIC-14) — typed response shapes generated from backend, replacing untyped JS in `frontend/src/api/`.
- [ ] **Contract tests** Backend ↔ Frontend.
- [ ] Export simulation transcripts as structured JSON for external analysis.

---

## v1.0.0 — Production Ready

Targets the cutoff for "I'd let a colleague run this on their machine without hand-holding."

- [ ] **AuthN/AuthZ** — beyond the current optional `AGORA_AUTH_TOKEN` opaque-token guard: real users, scoped permissions, session model.
- [ ] **Graph versioning** — snapshot and restore full graph states (deep-copy of nodes/edges/ontology, not just temporal-edge slicing).
- [ ] **Branch Compare** (Backlog EPIC-12) — first-class diff UI between two simulation branches: deltas in personas, action distributions, polarization metrics.
- [ ] **Plugin system** for custom NER extractors, search strategies, report templates.
- [ ] **E2E test suite** — Playwright or similar against a docker-compose stack.
- [ ] **Performance benchmarks** — document throughput (texts/min) and latency budgets per hardware tier.
- [ ] **Helm chart** for Kubernetes deployment.
- [ ] **Replay / Reproduce Run** — deterministic re-execution of a finished simulation given the same artifacts.
- [ ] CI auf `npm run check` plus Container-Build, Branch-Schutz, Coverage-Threshold.

### Beyond v1.0

- [ ] Federation: connect multiple Agora instances to share entity knowledge.
- [ ] Fine-tuned local models specifically trained for NER/RE on social simulation data.
- [ ] Evidence-/Confidence-Scoring layer (Backlog EPIC-15) for graph claims.
- [ ] Voice-driven interaction with running simulations.

---

## Hardware Tiers

| Tier | RAM | GPU VRAM | Recommended Model | Expected Performance |
|------|-----|----------|-------------------|---------------------|
| Minimal | 8 GB | — (CPU only) | qwen2.5:3b | Slow, basic NER quality |
| Light | 16 GB | 6-8 GB | qwen2.5:7b | Usable for small graphs |
| Standard | 32 GB | 12-16 GB | qwen2.5:14b | Good for most use cases |
| Power | 64 GB | 24+ GB | qwen3-coder-next:cloud (Ollama Cloud) or qwen2.5:32b local | Full quality, fast |

---

## Contributing

AGPL-3.0. Contributions welcome — especially around:

- Python 3.12+ compatibility for CAMEL-AI / OASIS
- Additional embedding model support
- E2E test coverage
- TypeScript migration of the frontend API layer

See [GitHub Issues](https://github.com/arn0ld87/agora/issues) for active work.
