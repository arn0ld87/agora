# AGENTS.md

This file provides guidance to Codex and other agent runtimes working in this repository.

> **Hinweis:** `CLAUDE.md` ist die Schwesterdatei für Claude Code und soll fachlich mit diesem Dokument synchron bleiben.

## Projekt

Agora (**v0.5.0 alpha**) ist ein lokal-first-Fork von MiroFish: Dokument hochladen → Wissensgraph extrahieren → personalisierte Agenten spawnen → Social-Media-Reaktionen simulieren → Report erzeugen. Der Fork ersetzt Zep Cloud durch Neo4j und DashScope/OpenAI durch Ollama (oder einen beliebigen OpenAI-kompatiblen Endpoint).

Stack: Flask (Python 3.11) + Vue 3 + Vite + Neo4j 5.18 CE + OASIS (`camel-oasis`) + Ollama. Package-Manager: `uv` fürs Backend, `npm` fürs Frontend. Aktuell produktiv gefahren mit LLM `qwen3-coder-next:cloud` und Embedding `qwen3-embedding:4b` (2560 dim, siehe Gotchas).

## Dokumentationsquellen

- **`docu/`** ist die verbindliche Ablage für laufende Projekt-Doku: Audit, Zielarchitektur, Refactoring-Backlog, P0-Protokolle, Verlauf.
- **`docs/README.md`** ist nur noch ein Redirect-Hinweis auf `docu/`.
- **`CHANGELOG.md`** am Repo-Root führt die Release-Notes.

Wichtige Einstiegsdateien:
- `docu/README.md`
- `docu/target-architecture.md`
- `docu/refactoring-backlog-priorisiert.md`
- `docu/p0-arbeitsprotokoll.md`
- `CHANGELOG.md`

## Erwartete Tool-Nutzung (proaktiv — nicht erst auf Anfrage)

- **context7** — bei jeder Task, die Bibliotheken, Frameworks, SDKs, CLIs oder Cloud-Services berührt (Flask, Vue 3, Vite, Neo4j-Driver, OASIS/CAMEL, Ollama, OpenAI-kompatible Chat-/Tool-Call-APIs, pytest, uv, …) aktuelle Docs prüfen, bevor du Code schreibst oder änderst.
- **GitHub-Suche** — bei Debugging von Third-Party-Verhalten (OASIS-Eigenheiten, Neo4j-Vector-Search-Kanten, Ollama-Tool-Call-Payloads, Qwen/GPT-OSS-Reasoning-Blöcke) zuerst Upstream-Issues/PRs prüfen.
- **sequential-thinking** — automatisch für Multi-File-Refactors, pipelinespannende Änderungen (graph → env → simulation → report), Debugging über die Flask↔OASIS-Subprozess-Grenze oder Tasks mit unklarem Lösungspfad.

Defaults, keine Eskalation. Wenn du eins davon überspringst, notiere kurz warum.

## Commands

Alle Commands laufen vom Repo-Root.

```bash
# First-time install (root npm + frontend npm + backend uv sync)
npm run setup:all

# Dev — backend (uv run python run.py) und frontend (vite) parallel
npm run dev

# Einzelprozesse
npm run backend        # Flask auf :5001
npm run frontend       # Vite auf :5173 (proxy /api → :5001)
npm run build          # Production-Frontend-Bundle

# Quality-Gate
npm run check

# Einzel-Linter / Tests
npm run lint:backend   # ruff, gescopter Rollout
npm run lint:frontend
npm run test:backend   # = cd backend && uv run pytest
cd backend && uv run pytest path/to/test_file.py::test_name
cd backend && uv run python -m compileall app scripts
```

`npm run lint:backend` ist weiterhin ein **gescopter Rollout** auf refaktorierte/stabilisierte Dateien. Strategischer Zielzustand bleibt „default strict + zentrale Excludes“, aber Stand v0.5.0 ist noch nicht Full-Repo-Ruff-clean.

Docker (Full Stack inkl. Neo4j):

```bash
docker compose up -d
docker compose build agora && docker compose up -d --force-recreate --no-deps agora
docker logs -f agora
```

Neo4j Browser: http://localhost:7474  
Backend Health: http://localhost:5001/health  
Status: http://localhost:5001/api/status

## Konfiguration

Alles läuft über `.env` am Repo-Root, geladen von `backend/app/config.py`.

Pflicht: `LLM_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, `SECRET_KEY` (außer `FLASK_DEBUG=true`).

Wichtige nicht-offensichtliche Knöpfe:

- **`EMBEDDING_MODEL` ↔ `VECTOR_DIM` müssen zusammenpassen.**
  - `nomic-embed-text` → 768
  - `embeddinggemma:300m` → 768
  - `qwen3-embedding:4b` → 2560
  - `qwen3-embedding:8b` → 4096
- Das Backend validiert die Embedding-Konfiguration jetzt **fail-fast beim Startup** inkl. echter Probe gegen das Embedding-Backend.
- `LLM_MODEL_NAME` — Default `qwen2.5:32b`; für Ollama Cloud ist `qwen3-coder-next:cloud` empfohlen.
- `OLLAMA_THINKING=false` — strippt Reasoning-Blöcke bei Qwen3/GPT-OSS/DeepSeek-R1.
- `LLM_DISABLE_JSON_MODE=true` — deaktiviert `response_format=json_object`; Markdown-Fences werden in `chat_json()` gestrippt.
- `GRAPH_CHUNK_SIZE=1500`, `GRAPH_CHUNK_OVERLAP=150`, `GRAPH_PARALLEL_CHUNKS=4` — Graph-Build-Tuning.
- `REPORT_LANGUAGE=German`, `AGENT_LANGUAGE=de`, `TIME_PROFILE=dach_default` — DACH-Defaults.
- `ENABLE_AGENT_TOOLS=false` — experimentelles OASIS-Tool-Use, opt-in.
- `AGORA_AUTH_TOKEN` — optionaler API-Token-Schutz für `/api/*`.
- `AGORA_EXTRA_ORIGINS` / `AGORA_CORS_ALLOW_ALL=true` — CORS ist standardmäßig auf `localhost:5173` / `127.0.0.1:5173` gelockt.
- `AGORA_LOG_FORMAT=text|json` — opt-in JSON-Logs.
- `TAVILY_API_KEY` + `ENABLE_WEB_TOOLS=true` — optionaler Live-Web-Kontext für den ReportAgent.

## Architektur

### Backend-Schichten (DI über `app.extensions`, keine Globals)

`Flask create_app` registriert fünf Blueprints und legt die einzige `Neo4jStorage`-Instanz in `app.extensions['neo4j_storage']` ab. Ein Token-Guard (`install_blueprint_guard`) hängt sich als `before_request` in jedes Blueprint. Schlägt `Neo4jStorage()` fehl, wird `None` abgelegt und Endpunkte antworten kontrolliert.

```text
api/        thin HTTP-Layer — graph.py, report.py, runs.py, status.py
            plus Simulation-Slice:
              simulation.py (Kompatibilitätsmodul)
              simulation_common.py
              simulation_lifecycle.py
              simulation_entities.py
              simulation_prepare.py
              simulation_profiles.py
              simulation_run.py
              simulation_interviews.py
              simulation_history.py
services/   graph_builder, simulation_manager, simulation_runner,
            report_agent, graph_tools, oasis_profile_generator,
            simulation_config_generator, simulation_ipc,
            run_registry, entity_reader, web_tools, …
storage/    GraphStorage → Neo4jStorage, EmbeddingService,
            NERExtractor, SearchService, neo4j_schema
utils/      llm_client, file_parser, logger, retry, auth,
            gpu_probe, validation, artifact_locator, json_io
models/     Dataclasses (Project, Task)
```

`SearchService` verwendet hybrides Scoring `0.7 * vector + 0.3 * BM25`; die Vektor-Dimension ist `Config.VECTOR_DIM`.

### Die Vier-Stufen-Pipeline

1. **Graph Build** — Dokument chunken → parallele `storage.add_text`-Aufrufe (NER/RE → Embeddings → Neo4j).
2. **Env Setup** — Persona- und Simulation-Config generieren; Konfiguration wird in `uploads/simulations/<sim_id>/simulation_config.json` eingefroren.
3. **Simulation** — OASIS läuft als separater Subprozess; Flask↔Subprozess-IPC über den `SimulationEventBus` (`FilePollingEventBus` offline-first, `RedisEventBus` im Compose-Default); `run_state.json` ist Post-Mortem-Persistenz. `SimulationRunner.register_cleanup()` killt Orphans beim Shutdown.
4. **Report** — `ReportAgent` nutzt `GraphToolsService` und optional `WebTools`; Loop-Limits via `REPORT_AGENT_MAX_TOOL_CALLS` und `REPORT_AGENT_MAX_REFLECTION_ROUNDS`.

### Event-Bus & SSE (Issue #9)

- `backend/app/services/event_bus.py` definiert `SimulationEventBus` (publish / subscribe / request_response) mit Channel-Konstanten `control`, `state`, `rpc.command`, `rpc.response.<id>`, `action`.
- Drei Adapter: `InMemoryEventBus` (Tests), `FilePollingEventBus` (offline-first, wrappt `SimulationArtifactStore`), `RedisEventBus` (compose-Default via `redis:7-alpine`). Backend-Auswahl via `Config.EVENT_BUS_BACKEND` (`auto` | `redis` | `file`).
- Live-Kanäle `control`/`state` gehen in Phase B über Redis; RPC bleibt bis Issue #17 file-delegiert.
- SSE-Bridge: `GET /api/simulation/<id>/stream` mit 15-s-Heartbeat. Frontend nutzt `frontend/src/composables/useEventStream.js`.

### Graph-Analytik (Issues #10 + #12)

- **Temporal Graph (#10):** RELATION-Kanten tragen `valid_from_round`, `valid_to_round`, `reinforced_count`. `TemporalGraphService` (`backend/app/services/temporal_graph.py`) liefert `get_snapshot` und `compute_diff`; API unter `GET /api/graph/snapshot/<gid>/<round>` und `GET /api/graph/diff/<gid>?start_round=..&end_round=..`. Lazy Backfill stampft Pre-#10-Kanten auf `valid_from_round=0`.
- **Polarisation (#12):** `NetworkAnalyticsService` (`backend/app/services/network_analytics.py`) bildet OASIS-Aktionen auf einen `networkx`-Interaktionsgraph ab, liefert Louvain-Communities, Echo-Chamber-Index und Betweenness-basierte Bridge-Agents. API: `GET /api/simulation/<id>/metrics` (`window_size_rounds`, `platform` optional). Dokumentation in `docu/analytics.md`.
- **Ontology-Mutation (#11):** `OntologyManager` + `OntologyMutationService` (`backend/app/services/ontology_mutation.py`) mit Modi `disabled`/`review_only`/`auto`, thread-safe per-graph-Locks, Audit-Log und pluggable `ConceptScorer`. Config via `ONTOLOGY_MUTATION_MODE` und `ONTOLOGY_MUTATION_MIN_CONFIDENCE`. NER→Mutation-Wiring ist als Follow-up ausgelagert.

### Operability (v0.5.0)

- `GET /api/status` liefert `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp`.
- `Neo4jStorage` nutzt `neo4j_call_with_retry` (Exponential Backoff + Jitter, max 3 Retries bei `ServiceUnavailable`/`SessionExpired`/`TransientError`).
- Jeder Request bekommt eine 8-Zeichen-Request-ID.
- Langläufer laufen über `RunRegistry` und `SimulationRunner`.
- JSON-basierte Polling-Pfade wurden gehärtet: atomische JSON-Writes + defensive Reads (`utils/json_io.py`) für Report- und zentrale Simulation-Artefakte.
- `Neo4jStorage`-Startfehler werden in `app.extensions['neo4j_storage_error']` gespiegelt und von `/api/status` + `/api/simulation/available-models` ausgeliefert; die UI zeigt den echten Fehler.

### Frontend (Vue 3 + Vite)

- `frontend/src/views/`: `Home.vue`, `MainView.vue`, `Process.vue`, `SimulationView.vue`, `SimulationRunView.vue`, `ReportView.vue`, `InteractionView.vue`
- `frontend/src/components/`: `GraphPanel.vue`, `Step[1-5]*.vue`, `HistoryDatabase.vue`, `AppFooter.vue`
- `frontend/src/components/graph/`: `GraphDetailPanel.vue`, `GraphLegend.vue`, `graphPanelData.js`, `graphPanelUtils.js`, `graphPanelGeometry.js`
- `frontend/src/components/ui/`: `Btn`, `Card`, `Badge`, `Field`, `Hairline`, `Kicker`, `SectionHead`, `Select`
- `frontend/src/api/`: `index.js`, `graph.js`, `simulation.js`, `report.js`, `runs.js`
- `frontend/src/composables/usePolling.js` zentralisiert Polling-Grundlogik für Langläufer; `frontend/src/composables/useEventStream.js` ist das SSE-Pendant (Issue #9 Phase C).
- `frontend/src/api/stream.js` baut SSE-URLs mit Auth-Token (`?token=...`, weil EventSource keine Custom-Header setzt).
- **Pinia wird nicht verwendet.** Persistenter Zustand lebt noch in `src/store/pendingUpload.js`.

## Conventions & Gotchas

- Neo4j **muss 5.18+** sein.
- Backend-Env-Änderungen wirken erst nach **Backend-Restart**, nicht nach Flask-Reload.
- Uploads landen in `backend/uploads/`; Simulationen in `backend/uploads/simulations/<sim_id>/`.
- Erlaubte Upload-Extensions: `pdf`, `md`, `txt`, `markdown`. `MAX_CONTENT_LENGTH = 50 MB`.
- Secrets werden nicht in `simulation_config.json` oder andere persistierte Artefakte serialisiert.
- Upstream-Chinesisch in Attribution/Migrations-Inventaren kann bleiben; Runtime-Defaults gehen von DACH aus.

## Laufendes Refactoring

Das Repo steckt mitten in einem phasierten Umbau (Audit: `docu/2026-04-22-refactoring-produkt-audit.md`; Zielarchitektur: `docu/target-architecture.md`; Backlog: `docu/refactoring-backlog-priorisiert.md`).

Stand v0.5.0 (2026-04-24):
- Quality-Gates (`npm run check`, CI, **190 Backend-Tests grün** + 1 skip für Redis-Integration)
- Issue-Serie #13 → #14 → #9 → #10 → #12 → #11 abgeschlossen und auf `main`
- `AgoraContainer` als DI-Anker; Services werden als Singletons (`neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`) oder Factories (`graph_builder`, `temporal_graph`, `network_analytics`, `ontology_mutation_service`) exponiert
- Event-Bus + SSE-Bridge (#9), Temporal Graph Snapshots (#10), Polarization-Metriken (#12), Ontology-Mutation-Skeleton (#11)

Wirklich offen bleiben vor allem:
- RPC/Interview-IPC-Migration auf Redis Pub/Sub (Issue #17 — eröffnet, noch nicht umgesetzt)
- NER→Ontology-Mutation-Wiring (Issue #11 Phase 2)
- Frontend Round-Slider für Temporal-Graph-Snapshots (#10 optional)
- gemeinsames Workspace-Layout
- weiterer Abbau der Frontend-Warnungen
- schrittweise Ausweitung von Ruff Richtung Default-strict

## Referenz

- `docu/graphrag-speedup.md` — Ollama-Cloud-Tuning / Graph-Build-Speedup
- `docu/agent-tools-integration.md` — OASIS-Agenten + `GraphToolsService` / `WebTools`
- `docu/security-hardening.md` — aktuelle Security-Baseline
- `docu/target-architecture.md` — Soll-Bild nach dem Refactoring
