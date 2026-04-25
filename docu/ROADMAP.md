# Agora Roadmap

> Stand: 2026-04-25. Versions-Historie und Detail-Backlog: `docu/refactoring-backlog-priorisiert.md`, `docu/p0-arbeitsprotokoll.md`, `CHANGELOG.md`.

## Current State (v0.5.0 + Unreleased)

Fully local fork on Neo4j CE + Ollama, no Zep Cloud dependency. Core pipeline works end-to-end: upload → graph build → persona generation → multi-agent OASIS simulation → report.

The 0.5 line shipped six prioritized issues (#13 → #14 → #9 → #10 → #12 → #11 Phase 1) and the post-0.5 unreleased branch added LLM retry resilience, frontend defensive error handling, default-strict ruff scope, and the NER → ontology-mutation wiring (#11 Phase 2).

### Implemented (v0.5.0 + unreleased)

- **Quality gates** — `npm run check` runs default-strict ruff on `app/ tests/`, pytest (202 passed, 1 skip), frontend lint, frontend build.
- **DI container (#14)** — `AgoraContainer` with singletons (`neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`, `ontology_mutation_service`) and request-scoped factories (`graph_builder`, `temporal_graph`, `network_analytics`).
- **Event bus + SSE (#9)** — `SimulationEventBus` with `InMemoryEventBus`, `FilePollingEventBus`, `RedisEventBus`. SSE endpoint `GET /api/simulation/<id>/stream` replaces 2.5s status polling.
- **Temporal graph (#10)** — relation edges carry `valid_from_round`, `valid_to_round`, `reinforced_count`. APIs `GET /api/graph/snapshot/<gid>/<round>` and `GET /api/graph/diff/<gid>?...`.
- **Polarization metrics (#12)** — `NetworkAnalyticsService` with Louvain communities, echo-chamber index, betweenness-based bridge agents. API `GET /api/simulation/<id>/metrics`.
- **Ontology mutation (#11 Phase 1+2)** — `OntologyManager` (thread-safe per-graph locks) + `OntologyMutationService` (`disabled` / `review_only` / `auto`). NER pipeline forwards novel entity types automatically; service exceptions never block ingestion.
- **LLM resilience** — `LLMClient.chat` / `describe_image` retry on transient upstream failures (`APIConnectionError`, `APITimeoutError`, `RateLimitError`, `APIStatusError` 5xx/408/429) via `llm_call_with_retry`.
- **Operability** — `/api/status`, request-IDs, atomic JSON writes (`utils/json_io.py`), Neo4j call retry, fail-fast embedding-config validation.

---

## Near Term

### v0.6.0 — RPC migration + frontend hygiene

Schließt die letzten Loose Ends der 0.5-Saga und macht das Frontend Production-tauglich.

- [ ] **Issue #17 — RPC/Interview-IPC auf Redis Pub/Sub**. Aktuell laufen `state` und `control` über Redis, RPC und Interview-Streams hängen noch am `FilePollingEventBus`. Migration entkoppelt Backend und Subprozess sauber.
- [ ] **Frontend Round-Slider** für Temporal-Graph-Snapshots (#10 optional). UI-Bedienelement für `GET /api/graph/snapshot/<gid>/<round>`.
- [ ] **Gemeinsames Workspace-Layout** (Backlog EPIC-03). Aktuell duplizierte Layout-Logik in `MainView`/`ReportView`/`InteractionView`/`SimulationRunView`.
- [ ] **Frontend-Warnungen abbauen** — Vue/Vite-Build noch mit Warnings, schrittweise erschlagen.
- [ ] Tune hybrid search weights (currently `0.7 vector / 0.3 BM25`) — make configurable per graph.

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
