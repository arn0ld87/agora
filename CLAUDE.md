# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

> **Hinweis:** `AGENTS.md` ist die Schwesterdatei für Codex/andere Agents und soll fachlich mit diesem Dokument synchron bleiben.

## Projekt

Agora (**v0.6.0 alpha**) ist ein lokal-first-Fork von MiroFish: Dokument hochladen → Wissensgraph extrahieren → personalisierte Agenten spawnen → Social-Media-Reaktionen simulieren → Report erzeugen. Der Fork ersetzt Zep Cloud durch Neo4j und DashScope/OpenAI durch Ollama (oder einen beliebigen OpenAI-kompatiblen Endpoint).

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

**Dev-Override aktiv:** `docker-compose.override.yml` bind-mountet den Repo-Root nach `/app` und hält `/app/node_modules`, `/app/frontend/node_modules` und `/app/backend/.venv` auf named volumes. Damit sind Source-Änderungen im Container sofort sichtbar; ein Rebuild ist nur bei Dockerfile- oder Dependency-Änderungen nötig.

Nützliche Dev-Kommandos:

```bash
# Dev-Container mit aktuellem Source-Code neu erstellen

docker compose up -d --force-recreate agora

# Nach Dockerfile-/Dependency-Änderungen sauber rebuilden

docker compose build agora && docker compose up -d --force-recreate --no-deps agora

# Dependency-Volumes bei Bedarf hart zurücksetzen

docker compose down -v && docker compose up -d
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
- `HYBRID_SEARCH_VECTOR_WEIGHT=0.7`, `HYBRID_SEARCH_KEYWORD_WEIGHT=0.3` — Mischung im `SearchService`. Müssen sich nicht zu 1.0 summieren (jede Seite wird vorher normalisiert).
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
3. **Simulation** — OASIS läuft als separater Subprozess; Flask↔Subprozess-IPC über den `SimulationEventBus` (`FilePollingEventBus` offline-first, `RedisEventBus` hybrid Pub/Sub + File im Compose-Default seit Issue #17); `run_state.json` ist Post-Mortem-Persistenz. `SimulationRunner.register_cleanup()` killt Orphans beim Shutdown.
4. **Report** — `ReportAgent` nutzt `GraphToolsService` und optional `WebTools`; Loop-Limits via `REPORT_AGENT_MAX_TOOL_CALLS` und `REPORT_AGENT_MAX_REFLECTION_ROUNDS`.

### Event-Bus & SSE (Issues #9 + #17)

- `backend/app/services/event_bus.py` definiert `SimulationEventBus` (publish / subscribe / request_response) mit Channel-Konstanten `control`, `state`, `rpc.command`, `rpc.response.<id>`, `action`.
- Drei Adapter: `InMemoryEventBus` (Tests), `FilePollingEventBus` (offline-first, wrappt `SimulationArtifactStore`), `RedisEventBus` (compose-Default via `redis:7-alpine`). Backend-Auswahl via `Config.EVENT_BUS_BACKEND` (`auto` | `redis` | `file`).
- **Live-Kanäle** `control`/`state` gehen über Redis Pub/Sub mit retained Snapshot im Artifact-Store für späte Subscriber.
- **RPC-Kanäle** (`rpc.command`, `rpc.response.*`) seit Issue #17 hybrid: Backend published parallel auf Redis + File, `_await_response` race't beide Quellen, first-come-wins, der Verlierer wird via `_cleanup_rpc_artifacts` aufgeräumt. Subprocess-Listener `RedisIPCBridge` (`backend/scripts/subprocess_redis_bridge.py`) läuft im OASIS-Eventloop neben dem File-Polling; `seen_command_ids` im IPCHandler dedupliziert Doppel-Dispatch. Ohne `REDIS_URL` bleibt die Bridge inaktiv und alles läuft wie im File-only-Modus.
- SSE-Bridge: `GET /api/simulation/<id>/stream` mit 15-s-Heartbeat. Frontend nutzt `frontend/src/composables/useEventStream.js`.

### Graph-Analytik (Issues #10 + #12)

- **Temporal Graph (#10):** RELATION-Kanten tragen `valid_from_round`, `valid_to_round`, `reinforced_count`. `TemporalGraphService` (`backend/app/services/temporal_graph.py`) liefert `get_snapshot` und `compute_diff`; API unter `GET /api/graph/snapshot/<gid>/<round>` und `GET /api/graph/diff/<gid>?start_round=..&end_round=..`. Lazy Backfill stampft Pre-#10-Kanten auf `valid_from_round=0`.
- **Polarisation (#12):** `NetworkAnalyticsService` (`backend/app/services/network_analytics.py`) bildet OASIS-Aktionen auf einen `networkx`-Interaktionsgraph ab, liefert Louvain-Communities, Echo-Chamber-Index und Betweenness-basierte Bridge-Agents. API: `GET /api/simulation/<id>/metrics` (`window_size_rounds`, `platform` optional). Dokumentation in `docu/analytics.md`.
- **Ontology-Mutation (#11):** `OntologyManager` + `OntologyMutationService` (`backend/app/services/ontology_mutation.py`) mit Modi `disabled`/`review_only`/`auto`, thread-safe per-graph-Locks, Audit-Log und pluggable `ConceptScorer`. Config via `ONTOLOGY_MUTATION_MODE` und `ONTOLOGY_MUTATION_MIN_CONFIDENCE`. **Phase 2 ist live**: `Neo4jStorage.add_text` ruft `_evaluate_ontology_mutations()` direkt nach NER, filtert NER-Output gegen die aktuelle Ontologie und reicht alles Unbekannte an `service.evaluate_batch()` durch. Service ist im Container Singleton, wird via `Neo4jStorage.set_ontology_mutation_service()` late-bound (vermeidet zirkuläre `OntologyManager↔Storage`-Dependency). Service-Exceptions werden geloggt aber geschluckt — Ingestion bleibt robust.

### Operability (v0.5.0)

- `GET /api/status` liefert `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp`.
- `Neo4jStorage` nutzt `neo4j_call_with_retry` (Exponential Backoff + Jitter, max 3 Retries bei `ServiceUnavailable`/`SessionExpired`/`TransientError`).
- `LLMClient.chat` / `describe_image` nutzen `llm_call_with_retry` (gleiche Backoff-Mechanik) gegen transiente Upstream-Fehler: `APIConnectionError`, `APITimeoutError`, `RateLimitError`, `APIStatusError` mit 5xx/408/429. 4xx-Client-Fehler werden sofort durchgereicht. Knöpfe: `LLM_MAX_RETRIES` (3), `LLM_RETRY_INITIAL_DELAY` (1.0), `LLM_RETRY_MAX_DELAY` (30.0). Schützt v. a. die Ontology-Generierung gegen Ollama-Cloud-5xx-Flaps.
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

Stand v0.6.0 (2026-04-26):

- Quality-Gates (`npm run check`, CI, **214 Backend-Tests grün** mit Live-Redis; Module skipt sauber ohne `TEST_REDIS_URL`). Backend-Lint ist auf `app/ tests/` umgestellt (default-strict).
- Issue-Serie #13 → #14 → #9 → #10 → #12 → #11 (Phase 1 + 2) → #17 abgeschlossen und auf `main`
- `AgoraContainer` als DI-Anker; Singletons `neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`, `ontology_mutation_service`. Factories: `graph_builder`, `temporal_graph`, `network_analytics`
- Event-Bus + SSE-Bridge (#9), Temporal Graph Snapshots (#10) inkl. Frontend-Round-Slider, Polarization-Metriken (#12), Ontology-Mutation inkl. NER-Wiring (#11), LLM-Retry gegen Cloud-5xx-Flaps, RPC/Interview-IPC hybrid Redis Pub/Sub + File (#17), Workspace-Layout-Shell + State-Composables (EPIC-03 ST-01/02/03)

Wirklich offen bleiben vor allem:

- weiterer Abbau der Frontend-Warnungen
- standardisierte API-Error/Response-Envelopes (EPIC-09)
- TypeScript-Migration der Frontend-API-Schicht (EPIC-14)
- Folgeticket: File-IPC-Pfad deprecaten sobald Telemetrie zeigt dass alle Live-Setups den Redis-Bridge-Pfad nutzen

## Referenz

- `docu/graphrag-speedup.md` — Ollama-Cloud-Tuning / Graph-Build-Speedup
- `docu/agent-tools-integration.md` — OASIS-Agenten + `GraphToolsService` / `WebTools`
- `docu/security-hardening.md` — aktuelle Security-Baseline
- `docu/target-architecture.md` — Soll-Bild nach dem Refactoring
