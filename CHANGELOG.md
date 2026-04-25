# Changelog

Alle nennenswerten Änderungen an Agora werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

### Behoben

- **`HistoryDatabase.vue::loadRuns()` schluckte Backend-Fehler ohne Catch.** Wenn `listRuns()` einen Reject lieferte (Run-Registry-API down, Auth-Token falsch, Timeout), bubbelte der Promise-Reject als unhandled Rejection durch — UI zeigte stumm eine leere Liste, Browser-Konsole spammte „Axios response error". Neuer `.catch`-Branch setzt `loadError`, rendert eine sichtbare Fehlerzeile mit „Erneut versuchen"-Button und behält die leere Liste konsistent.
- **LLM-Resilienz gegen transiente Upstream-5xx.** `LLMClient.chat()` und `LLMClient.describe_image()` rufen den OpenAI-kompatiblen Endpoint jetzt über `llm_call_with_retry()` (`backend/app/utils/retry.py`) auf — Exponential-Backoff mit Jitter analog zu `neo4j_call_with_retry`. Retry auf `APIConnectionError`, `APITimeoutError`, `RateLimitError` und `APIStatusError` mit Status 5xx / 408 / 429; 4xx-Client-Fehler fallen sofort durch. Ollama-Cloud-Hickser killen damit nicht mehr die Pipeline-Init (Symptom: `POST /api/graph/ontology/generate` → `Error code: 500 - {'error': 'Internal Server Error (ref: ...)'}`). Konfigurierbar per `LLM_MAX_RETRIES` (Default 3), `LLM_RETRY_INITIAL_DELAY` (1.0 s), `LLM_RETRY_MAX_DELAY` (30 s). Tests: `test_retry.py` (+4 → 13).

## [0.5.0] — 2026-04-24

Ship der kompletten Priorisierungs-Kette #13 → #14 → #9 → #10 → #12 → #11 plus Release-Polish.

### Hinzugefügt

- **Issue #9 Phase A–C — Event Bus + SSE Bridge.**
  - `SimulationEventBus`-Port (`backend/app/services/event_bus.py`) mit `InMemoryEventBus`, `FilePollingEventBus` (offline-first, wrappt `SimulationArtifactStore`) und `RedisEventBus` (`backend/app/services/event_bus_redis.py`).
  - Redis-Service (`redis:7-alpine` mit Healthcheck + Volume) in `docker-compose.yml`; `Config.REDIS_URL` + `Config.EVENT_BUS_BACKEND` (`auto`/`redis`/`file`) wählen den Transport im `AgoraContainer`.
  - `SimulationRunner._save_run_state` spiegelt Snapshots auf `CHANNEL_STATE`.
  - SSE-Endpoint `GET /api/simulation/<id>/stream` (`backend/app/api/simulation_stream.py`) bridged `state`/`control` an `EventSource`-Clients. Heartbeat alle 15 s.
  - Frontend: `useEventStream.js` + `api/stream.js`; `Step3Simulation.vue` ersetzt 2,5-s-Status-Polling durch den Stream.
  - Tests: `test_event_bus.py` (13), `test_event_bus_redis.py` (6, skip ohne Redis), `test_simulation_stream.py` (2).
- **Issue #10 — Temporal Graph Evolution.**
  - RELATION-Kanten: `valid_from_round`, `valid_to_round`, `reinforced_count` (neu in `Neo4jStorage.add_text` + `_edge_to_dict`).
  - `Neo4jStorage.get_edges_at_round` (coalesce-Legacy-Semantik), `reinforce_relation`, `tombstone_relation`, idempotenter `backfill_temporal_defaults`. `GraphStorage`-Protocol bekommt Default-Stubs für Non-Neo4j-Adapter.
  - `TemporalGraphService` (`backend/app/services/temporal_graph.py`) mit `get_snapshot` + `compute_diff` (added / removed / reinforced); lazy Per-Graph-Backfill.
  - API: `GET /api/graph/snapshot/<gid>/<round>` und `GET /api/graph/diff/<gid>?start_round=..&end_round=..`.
  - Ingest: `GraphBuilderService` stamped `round_num=0`, `GraphMemoryUpdater` nutzt max(round_num) des Batches.
  - Tests: `test_temporal_graph.py` (7).
- **Issue #12 — Polarization-Metriken.**
  - `NetworkAnalyticsService` (`backend/app/services/network_analytics.py`) — `networkx`-Interaktionsgraph, Louvain-Communities, Echo-Chamber-Index, Betweenness-Bridge-Agents.
  - `networkx>=3.2` als Runtime-Dep.
  - API: `GET /api/simulation/<id>/metrics` mit `window_size_rounds` + `platform` Query-Params.
  - Dokumentation `docu/analytics.md` erklärt Filter (nur gerichtete Aktionen), Graph-Projektion, Heuristiken, API-Schema, Follow-ups.
  - Tests: `test_network_analytics.py` (7).
- **Issue #11 Phase 1 — Dynamic Ontology Mutation.**
  - `OntologyManager` (`backend/app/services/ontology_mutation.py`) mit per-graph `threading.Lock` für thread-safe `update()`.
  - `OntologyMutationService` mit Modi `disabled`/`review_only`/`auto`, pluggable `ConceptScorer` (Default-Heuristik: rejectet generische Platzhalter, belohnt PascalCase + context match), bounded In-Memory-Audit-Log + optional `audit_sink`.
  - Config: `ONTOLOGY_MUTATION_MODE` (default `disabled`), `ONTOLOGY_MUTATION_MIN_CONFIDENCE` (default 0.6).
  - `AgoraContainer.ontology_manager` + `ontology_mutation_service()`.
  - Tests: `test_ontology_mutation.py` (14) — Sanitization, Scorer, Manager-Idempotenz, Thread-Safety (20 concurrent writers), Modes, Audit-Log.
- **Issue #14 — `AgoraContainer` (DI).** Hand-rolled Container ersetzt `app.extensions[...]`-Service-Locator; Singletons (`neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`) + Factories (`graph_builder()`, `temporal_graph()`, `network_analytics()`, `ontology_mutation_service()`). `app.extensions['*']` bleiben als Backward-Compat-Aliase. Tests ohne Flask-App-Context (`test_container.py`).
- **Issue #13 — `SimulationArtifactStore`-Port.** Hexagonal-Port (`backend/app/services/artifact_store.py`) mit `LocalFilesystemArtifactStore` (Produktion, atomare Writes) und `InMemoryArtifactStore` (Tests). Alle Simulation-JSON-I/Os laufen über den Store. Constraint-Guard `tests/test_no_json_io_leakage.py` hält die SoC-Regel aufrecht.
- **fix(startup)** — Neo4j-Startup-Exception wird in `app.extensions['neo4j_storage_error']` persistiert und über `/api/status` + `/api/simulation/available-models` ausgeliefert. UI (`Home.vue`) zeigt den echten Fehler statt eines Platzhalters.
- **Dependency-Additionen:** `redis>=5.0.0`, `networkx>=3.2`.
- **Contract- und Smoke-Tests:** `test_artifact_store.py` (30), `test_no_json_io_leakage.py` (3).

### Geändert

- `Neo4jStorage.add_text` und `add_text_batch` akzeptieren jetzt einen optionalen `round_num`-Parameter.
- `SimulationIPCClient/Server` publishen/subscriben jetzt über den `SimulationEventBus` statt direkt den Store. Public-API unverändert.
- `docker-compose.yml`: Agora-Container hängt an `redis: service_healthy`, `REDIS_URL=redis://redis:6379/0` in Service-Env fest verdrahtet.

### Notiz — offen / Follow-up

- **Issue #17** (neu): RPC/Interview-IPC komplett von File-Polling auf Redis Pub/Sub migrieren. Der `RedisEventBus` delegiert `CHANNEL_RPC_COMMAND` + `rpc.response.*` derzeit bewusst an den `FilePollingEventBus`, weil der OASIS-Subprozess (`run_reddit_simulation.py` / `run_twitter_simulation.py`) seinen eigenen File-IPC-Handler hat. Dessen Umbau ist eigenständig getrackt.
- **Issue #11 Phase 2**: NER→Mutation-Wiring. Der `OntologyMutationService` ist aufrufbar, aber noch nicht vom Ingest-Pfad getriggert.
- **Issue #10 Optional**: Frontend-Round-Slider in `GraphPanel`; und echter MERGE-basierter Reinforce-Pfad in `add_text` (heute nur `reinforce_relation` als separater Helper).
- `services/run_registry.py` bleibt bewusst beim direkten `json_io`-Zugriff — eigener Store-Adapter folgt in separater PR.

## [0.4.1] — 2026-04-23

### Hinzugefügt
- fail-fast Validierung für `EMBEDDING_MODEL` / `VECTOR_DIM` inklusive echter Embedding-Probe beim Backend-Start
- `frontend/src/composables/usePolling.js` als gemeinsamer Polling-Baustein für Langläufer
- `backend/app/utils/json_io.py` für atomische JSON-Schreibvorgänge und defensive Reads
- `docu/README.md` sowie `docs/README.md` als klarerer Einstieg in die neue Dokumentationsstruktur
- `GraphStorage.get_filtered_entities_with_edges` — Cypher-Pushdown für gefilterte Entitäten inkl. Adjazenz (ersetzt In-Memory-Filterung im `EntityReader`)
- Bounded Queue + Backpressure im `GraphMemoryUpdater` (`GRAPH_MEMORY_QUEUE_MAX`, `GRAPH_MEMORY_PUT_TIMEOUT`) — OOM-Schutz bei langsamer Neo4j-Ingestion

### Geändert
- Report-Status-Polling ist robuster gegen leere/trunkierte `progress.json` / `meta.json`
- Simulation-nahe JSON-Artefakte (`state.json`, `run_state.json`, `simulation_config.json`, `reddit_profiles.json`) werden defensiver gelesen und teils atomisch geschrieben
- Root von temporären Hilfsdateien entlastet; historische Notizen liegen jetzt unter `docu/history/`, Log-Helfer unter `scripts/logs/`
- Dokumentationsbestand weiter nach `docu/` konsolidiert
- `EntityReader.filter_defined_entities` lädt nicht mehr alle Nodes/Edges in den RAM, sondern delegiert Filter + Adjazenz an die Storage-Schicht
- `GraphMemoryUpdater.get_stats()` meldet zusätzlich `dropped_count` und `queue_max`

### Test-Status
- 102/102 Backend-Tests grün (+14 für Cypher-Pushdown und Bounded Queue)
- Frontend-Lint: 0 Fehler
- Frontend-Build: erfolgreich

## [0.4.0] — 2026-04-22

Scope-Fokus: **Operability, Refactoring-Basis & Resilienz**. Details siehe `docu/plan_0.4.md` sowie die P0-Protokolle unter `docu/`.

### Hinzugefügt
- `GET /api/status` — konsolidierter Ops-Endpoint mit `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp` (`backend/app/api/status.py`, 7 Tests)
- `backend/app/utils/gpu_probe.py` — `detect_gpu()` erkennt `nvidia-smi` und parst `ollama ps` (wirft nie, 8 Tests)
- `AGORA_LOG_FORMAT=text|json` Env-Toggle — Opt-in JSON-Logging via neuem `JSONFormatter` in `backend/app/utils/logger.py` (stdlib-only, 10 Tests)
- Request-ID-Middleware in `backend/app/__init__.py` (8-Zeichen-UUID, loggt bei `after_request`)
- `simulation_id`-Context in Simulation-Logs (`simulation_runner.py`, `api/simulation.py`)
- Kommentierte GPU-Reservation-Sektion in `docker-compose.yml` + README-Abschnitt „GPU/CPU Fallback"

### Geändert
- `Neo4jStorage` mit transientem Retry (`ServiceUnavailable`, `SessionExpired`, `TransientError`, exp. Backoff + Jitter, max 3 Retries) — via neuem `neo4j_call_with_retry` in `backend/app/utils/retry.py`
- Neue Read-only-Properties auf `Neo4jStorage`: `is_connected`, `last_error`, `last_success_ts` — vom `/api/status`-Endpoint konsumiert
- `get_ontology()` und `search()` durchlaufen jetzt das Retry-Wrapper
- Root-Quality-Gates vereinheitlicht (`npm run check`, Backend-Ruff scoped rollout, Frontend-ESLint, CI-Workflow)
- `backend/app/api/simulation.py` in fokussierte Module zerlegt (`simulation_lifecycle`, `simulation_prepare`, `simulation_profiles`, `simulation_run`, `simulation_interviews`, `simulation_history`)
- `frontend/src/components/GraphPanel.vue` in erste Teilmodule zerlegt (Detailpanel, Legende, Datenaufbereitung)

### Verschoben
- Python-3.12/CAMEL/OASIS-Kompatibilität → v0.4.1/v0.5 (Upstream-blockiert, Host-Python im Container irrelevant)

### Test-Status
- 63/63 Backend-Tests grün
- Frontend-Lint: 0 Fehler (verbleibende Warnungen dokumentiert und schrittweise abzubauen)
- Frontend-Build: erfolgreich

### Entwicklungs-Vorgehen
- Feature-Arbeit parallel über isolierte Git-Worktrees: Haiku 4.5 für GPU-Probe + `/api/status`, Sonnet 4.6 für Neo4j-Reconnect + JSON-Logging
- Merges als `--no-ff` in main, GPU-Detect in `/api/status` nachverdrahtet

## [0.3.1] — 2026-04-22

### Geändert
- **Logo & Favicon**: Agora-Branding auf neues Logo (`media/logo.png`, 1254×1254) umgestellt
  - `frontend/public/icon.png` (Favicon, 256×256)
  - `frontend/src/assets/logo/agora-logo.jpg` (Home-View, 1024×1024)
  - `static/image/agora-logo.jpg` + `agora-logo-source.jpg` (README/Banner-Assets)
  - Commits: `97aca71` → Rebase auf `2dd1e58`

## [0.3.0] — vorher

Siehe Git-Historie vor Einführung dieses Changelogs.
