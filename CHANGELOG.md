# Changelog

Alle nennenswerten Änderungen an Agora werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt

- **`frontend/src/components/graph/GraphHints.vue`** — neue rein präsentationale Komponente für Building-/Simulating-Hint und Simulation-Finished-Hint. Erste Etappe von Issue #34 (EPIC-04-ST-01: GraphPanel zerlegen). Props: `currentPhase`, `isSimulating`, `showFinishedHint`. Emits: `dismiss-finished`. Styles 1:1 aus `GraphPanel.vue` übernommen, kein Visual-Diff. Sub-Slice 2.1 von 3.

### Geändert

- **`frontend/src/components/GraphPanel.vue`** schlanker (933 → 831 Zeilen): Hint-Markup und zugehörige Styles in `GraphHints.vue` ausgelagert; State `showSimulationFinishedHint`/`wasSimulating` plus der `watch` auf `props.isSimulating` bleiben hier (Lifecycle-State gehört nicht in präsentationale Komponente). `dismissFinishedHint` ist jetzt Handler für das `@dismiss-finished`-Event.
- **EPIC-02 (Backend-API-Splitting) als bereits erledigt geschlossen.** Die Inventur zum v0.8.0-Slice-Start zeigt, dass der Split aus `backend/app/api/simulation.py` in zehn fokussierte Module bereits in v0.4.0 vollständig umgesetzt wurde. `simulation.py` ist seither ein 17-zeiliger Compatibility-Shim ohne Routen. 48 Routen liegen unter `simulation_bp` thematisch verteilt (Lifecycle 4, Prepare 2, Run 12, Profiles 16, Interviews 4, History 4, Entities 3, Stream 1, Metrics 2), gemeinsame Helfer in `simulation_common.py`. Issue #29 wird retrospektiv durch `docu/2026-05-01-epic02-api-split-status.md` erfüllt; #30, #31, #32, #33 schließen mit Verweis auf v0.4.0-CHANGELOG-Eintrag und dieses Status-Dokument. Konsequenz: v0.8.0-Backlog reduziert sich von 13 auf 8 echte Issues (EPIC-04 ×3, EPIC-05 ×4, EPIC-10 ×1).

## [0.7.0] — 2026-05-01

Milestone "API Contracts & Quality Gate" abgeschlossen: einheitliche `ApiErrorCode`-Envelopes über Backend und Frontend, dokumentierte Response-Schemas mit JSON-Schema-Tests, Frontend-Mapper für code-basierte deutsche Fehler-Toasts, deklarative Simulation-State-Machine als Vorbereitung auf EPIC-06, und ein erstes Vitest-Setup im Frontend. 13/13 Issues geschlossen, **499 Tests grün** (488 Backend + 11 Frontend).

### Hinzugefügt

- **Simulation-State-Machine (deklarativ)** — neuer `backend/app/services/simulation_state_machine.py` mit `ALLOWED_TRANSITIONS`-Tabelle für alle 8 `SimulationStatus`-Werte plus `is_valid_transition`, `get_allowed_next`, `is_terminal`. Tabelle spiegelt 1:1 die 13 real beobachteten Transition-Call-Sites in Manager und API. **In v0.7.0 nur passiv** — EPIC-06-ST-02 wird die Helper aktiv in `SimulationManager` und API-Routes integrieren. Tests: `backend/tests/test_simulation_state_machine.py` (46 Tabellen-Tests) und `backend/tests/services/test_simulation_manager_transitions.py` (23 Behavior- und Compliance-Tests, pinnen Code gegen Tabelle).
- **Frontend-Vitest-Setup** — `vitest@4.1.5` als Dev-Dependency, minimaler `test`-Block in `frontend/vite.config.js` (Triple-Slash-Reference auf `vitest/config`, `environment: 'node'`). Erste 11 Smoke-Tests in `frontend/src/api/__tests__/envelope.spec.ts` decken `unwrap`, `ApiError`-Konstruktor und `isApiError`-Type-Guard ab. Root-`npm run check` hat jetzt 5 Stufen (lint:backend → test:backend → lint:frontend → test:frontend → build:frontend).
- **`docu/api-contracts.md`** — Single Source of Truth für Response-Envelopes und alle 23 `ApiErrorCode` (HTTP-Status, Backend-Default-DE, Frontend-UX-DE, Retry-Flag). Inhalte 1:1 aus `backend/app/utils/api_errors.py` und `frontend/src/api/errorMessages.ts` extrahiert. `.gitignore` erhält Negativ-Pattern für die zwei getrackten Files unter `/docu/` (`api-contracts.md` plus Release-Notes), Rest des Ordners bleibt lokal.
- **`docu/2026-05-01-v0.7.0-release-notes.md`** — Release-Notes mit Highlights, Migrations-Hinweisen und Test-Stand für Frontend- und Backend-Entwickler.
- **`ApiErrorCode`-Katalog** — 23 standardisierte Fehlercodes mit deutschen Default-Meldungen in `backend/app/utils/api_errors.py` (`INVALID_ID`, `NOT_FOUND`, `VALIDATION_FAILED`, `BAD_REQUEST`, `METHOD_NOT_ALLOWED`, `AUTH_REQUIRED`, `AUTH_INVALID`, `AUTH_FORBIDDEN`, `RATE_LIMITED`, `TIMEOUT`, `SERVICE_UNAVAILABLE`, `NEO4J_UNAVAILABLE`, `LLM_UNAVAILABLE`, `ONTOLOGY_MISSING`, `ONTOLOGY_GENERATION_FAILED`, `SIMULATION_NOT_PREPARED`, `SIMULATION_ALREADY_RUNNING`, `PERSONA_REVIEW_REQUIRED`, `UPLOAD_TOO_LARGE`, `UNSUPPORTED_FORMAT`, `INTERNAL_ERROR`, `NOT_IMPLEMENTED`, `GRAPH_BUILD_IN_PROGRESS`). `json_error()` akzeptiert `ApiErrorCode` als Argument und fällt auf Default-Message zurück; neuer `message=`-Override-Kwarg ermöglicht punktuelle Anpassung. Backwards-Compat: 198 bestehende positional-string-Aufrufe funktionieren unverändert.
- **Frontend-Envelope-Mapper** — neuer `frontend/src/api/envelope.ts` (`ApiError`-Klasse mit `code`/`status`/`details`/`originalResponse`, `unwrap<T>()` Helper, `isApiError()` Type-Guard) und `frontend/src/api/errorMessages.ts` (Map aller 23 Codes auf deutsche UX-Texte plus `userMessageFor()`/`isRetryable()` Helfer). Response-Interceptor in `frontend/src/api/index.js` wirft jetzt strukturierte `ApiError`-Exceptions. `HistoryDatabase.vue` als Smoke-Komponente nutzt code-basierte Toast-Texte mit bedingtem Retry-Button (nur bei transient-Codes: `service_unavailable`, `neo4j_unavailable`, `llm_unavailable`, `rate_limited`, `timeout`, `ontology_generation_failed`).
- **Response-Schema-Tests** — neuer `backend/tests/api/test_response_schemas.py` mit 31 Tests über 7 Domänen (Project, Simulation, RunStatus, ReportStatus, GraphData, OntologyDefinition, Persona). Pure JSON-Schema-Validation ohne Live-Endpoints. `jsonschema>=4.0.0` als Dev-Dependency.
- **Endpoint-Coverage** — 16 Tests in `backend/tests/api/test_graph_endpoints.py` plus 23 in `backend/tests/api/test_simulation_endpoints.py` validieren `code`-Feld über alle migrierten Pfade.
- CI-Security-Stage ergänzt: Frontend-`npm audit`, Python-`pip-audit` auf Basis des `uv.lock`-Exports und Gitleaks Secret Scan laufen als eigener GitHub-Actions-Job.
- `.gitleaksignore` ergänzt zwei fingerprint-genaue False-Positive-Baselines aus der bestehenden Git-Historie.
- `docu/p1-security-ci-error-envelope-protokoll.md` dokumentiert P1-Umsetzung, Checks und Rollback.
- `docu/v1-development-log.md` dokumentiert die v1.0-Entwicklungsschritte.
- Tests für den Auth-Guard decken Open-Mode, fehlende Tokens sowie Header-/Bearer-/Query-Token ab.
- Simulationsstarts akzeptieren zusätzlich `simulation_days`; die UI schreibt daraus `time_config.total_simulation_hours`, während das bestehende Rundenlimit als optionaler Cap erhalten bleibt.
- Lokale Persona-Bibliothek: erzeugte oder manuelle Personas können gespeichert, gelistet, gelöscht und in späteren Simulationen wiederverwendet werden.

### Geändert

- **API-Layer einheitlich auf `ApiErrorCode` migriert** — `backend/app/api/graph.py` (27 Stellen) und alle 9 Simulation-Module (107 Stellen). Codes semantisch vergeben: `INVALID_ID` für Validierungsfehler, `NOT_FOUND` (404), `VALIDATION_FAILED` (400), `SERVICE_UNAVAILABLE` (503) für System-Ausfälle, `SIMULATION_ALREADY_RUNNING` / `PERSONA_REVIEW_REQUIRED` (409 Conflict). Frontend kann Fehler jetzt semantisch behandeln — `service_unavailable` und `neo4j_unavailable` triggern Retry-UI, `not_found` zeigt klare Toast-Meldung statt HTTP-Status-Dump.
- **Internationalisierung bereinigt** — Chinesische Punctuation aus dem API-Layer entfernt (`，` → `, `, `（）` → `()`, 6 Stellen). Pidgin-English-Capitalizations (`max_rounds Must be...` → `must`, `Or` → `or`) gleich mitkorrigiert.
- `_require_env_alive` in `simulation_interviews.py` liefert jetzt 503 (Service Unavailable) statt implizit 400 — semantisch korrekt für Subprocess-Ausfall.
- API-Error-Envelopes sind für 5xx-Fehler jetzt security-safe: ungefangene Exceptions liefern außerhalb von `Config.DEBUG=true` nur noch generische Meldungen plus `code`, während konkrete Exception-Details im Log bleiben.
- Backend-Lockfile sicherheitsseitig aktualisiert: `pip-audit`-Findings in 14 Python-Paketen durch kompatible `uv.lock`-Upgrades reduziert; 6 verbleibende Upstream-Pin-Findings sind eng im CI dokumentiert und gebaselined.
- API-Contract-Härtung begonnen: Auth-Fehler aus `token_required()` und `install_blueprint_guard()` nutzen jetzt die zentrale `json_error()`-Envelope mit `success: false`.
- `@handle_api_errors` setzt seine dokumentierte Contract-Regel jetzt auch technisch um: rohe `dict`-Returns werden in `json_success()` gewrappt.
- Framework-seitige `/api/*`-HTTP-Fehler und ungefangene API-Exceptions liefern jetzt ebenfalls standardisierte JSON-Envelopes statt HTML-Fehlerseiten.
- Ontologie-Generierung ist nicht mehr auf exakt 10 Entitätstypen fixiert; Defaults sind 8-16 Typen und per `ONTOLOGY_MIN_ENTITY_TYPES` / `ONTOLOGY_MAX_ENTITY_TYPES` konfigurierbar.

### Behoben

- **`graph.py:269` Bug**: `json_error("...", task_id=...)` warf seit jeher `TypeError` (task_id kein bekannter kwarg), wurde als 500 ausgeliefert. Jetzt sauber 409 Conflict mit `extra={"task_id": ...}`.

## [0.6.1] — 2026-04-27

Kleines Hygiene-Release nach v0.6.0: Dependency-Advisories im Frontend beseitigt, Versionsdrift korrigiert und Doku/Testzahlen synchronisiert.

### Geändert

- Frontend-Lockfile per kompatiblem `npm audit fix` aktualisiert: `axios` → 1.15.2, `follow-redirects` → 1.16.0, `postcss` → 8.5.12.
- `/api/status` liest die Backend-Version jetzt aus `app.__version__` statt aus einem alten Literal.
- README und Roadmap auf den aktuellen Quality-Gate-Stand gebracht: 207 Backend-Tests grün, 2 Redis-Integrationstests skippen ohne `TEST_REDIS_URL`.

### Sicherheit

- `npm audit --omit=dev` ist im Frontend wieder ohne Findings.
- README-Warnung korrigiert: Agora hat inzwischen optionalen `AGORA_AUTH_TOKEN`-Schutz und restriktive CORS-Defaults, bleibt aber nicht für öffentlichen Betrieb gedacht.

## [0.6.0] — 2026-04-26

Ship des v0.6-Backlogs: RPC/Interview-IPC-Migration auf Redis Pub/Sub (#17), Frontend Round-Slider für den Temporal-Graph (#10 optional), EPIC-03 Workspace-Konsolidierung vollständig (Layout-Shell + State-Composables), konfigurierbare Hybrid-Search-Weights, LLM-Retry-Resilienz, NER-→-Ontology-Mutation-Wiring (#11 Phase 2). 207 Backend-Tests, Frontend warning-frei.

### Hinzugefügt

- **Hybrid-Search-Weights konfigurierbar.** `Config.HYBRID_SEARCH_VECTOR_WEIGHT` (Default 0.7) und `Config.HYBRID_SEARCH_KEYWORD_WEIGHT` (Default 0.3) lesen aus den gleichnamigen env-Vars. `SearchService` nimmt beide als optionale Constructor-Argumente; `Neo4jStorage` reicht die Config-Werte automatisch durch. Class-Konstanten `VECTOR_WEIGHT`/`KEYWORD_WEIGHT` bleiben als Backward-Compat. Doku in `.env.example` + CLAUDE.md/AGENTS.md. Tests: `tests/test_search_service.py` (5).
- **Workspace-State-Composables (EPIC-03 ST-02 + ST-03).** Zwei neue Composables unter `frontend/src/composables/` ersetzen identische Boilerplate-Blöcke aus den 5 Pipeline-Views:
  - `useWorkspaceMode(initialMode)` kapselt `viewMode` + `leftPanelStyle` + `rightPanelStyle` + `toggleMaximize` + `workspaceModes`. Alle 5 Views (Main, Simulation, SimulationRun, Report, Interaction) nutzen es; identische 12-Zeilen-Blöcke pro Datei sind weg.
  - `useWorkspaceStatus({ initial, map, fallback })` kapselt `currentStatus` + `statusKind` + `statusText` + `updateStatus` mit konfigurierbarem `{ status: { kind, text-key } }`-Mapping; löst die `useI18n()`-Aufrufe gleich im Composable auf, sodass die Views nur noch `statusText` direkt rendern. SimulationView, ReportView und InteractionView konsumieren das Composable. SimulationRunView behält bewusst seine paused-Overlay-Computed (Status mit Round-Counter), MainView seine phasen-basierte Status-Logik (`error` + `currentPhase`) — beide Sonderfälle sind im Composable-Header dokumentiert.
  - Schließt EPIC-03 vollständig ab (ST-01 Layout-Shell war schon vor diesem Sprint erledigt).
- **Frontend Round-Slider für Temporal-Graph-Snapshots (#10 optional).** Neue Komponente `frontend/src/components/graph/GraphRoundSlider.vue` lebt direkt im `GraphPanel` und blendet sich automatisch ein, sobald der Graph mindestens eine Simulationsrunde gesehen hat (`maxRound > 0`). Filter läuft client-seitig: `filterEdgesAtRound` in `graphPanelData.js` mirrort die Backend-Snapshot-Semantik (`valid_from_round <= R AND (valid_to_round IS NULL OR valid_to_round > R)`) — kein zusätzlicher API-Round-Trip beim Scrubben. Live-Mode (Default) zeigt alle aktuellen Edges; Reset-Button springt zurück. `getGraphSnapshot` und `getGraphDiff` in `frontend/src/api/graph.js` ergänzt für späteren server-side Bedarf (Diff-View, große Graphen). Schließt einen offenen v0.6.0-Roadmap-Punkt ab.
- **Frontend `useSystemLog`-Composable** (`frontend/src/composables/useSystemLog.js`). Ersetzt fünf identische `addLog`/`systemLogs`-Implementierungen in `MainView` / `SimulationView` / `SimulationRunView` / `ReportView` / `InteractionView` durch eine Quelle der Wahrheit. Cap pro Call-Site konfigurierbar (100 vs. 200 — bestehendes Verhalten erhalten). Schließt den UI-Konsolidierungs-Teil von EPIC-03 ab.
- **TypeScript-PoC.** `frontend/tsconfig.json` mit `allowJs: true` für sukzessive Migration; `frontend/src/types/run.ts` als erstes typisiertes Schema für die Run-Registry-API; `frontend/src/api/runs.ts` als migriertes Pendant. Vite/esbuild kompiliert TS nativ — keine zusätzliche Dependency nötig. Bereitet EPIC-14 (Frontend-API-Schicht typisiert) vor.
- **Issue #17 Phase D — RPC/Interview-IPC auf Redis Pub/Sub migriert.**
  - `RedisEventBus.publish` / `subscribe` / `request_response` für `CHANNEL_RPC_COMMAND` und `rpc.response.*` laufen jetzt **hybrid**: Redis Pub/Sub für Live-Latenz + File-IPC parallel als Rolling-Upgrade-Pfad und Fallback. Backend bewertet beide Quellen mit `_await_response`, first-come-wins, der Verlierer wird via `_cleanup_rpc_artifacts` aufgeräumt um Doppel-Dispatch zu verhindern. `request_response` armiert die Pub/Sub-Subscription **vor** dem Publish, um Race-Conditions mit schneller antwortenden Subprozessen zu vermeiden.
  - Subprocess-Listener `backend/scripts/subprocess_redis_bridge.py` (`RedisIPCBridge`): async `redis.asyncio` Pub/Sub im OASIS-Eventloop, `publish_response`-Mirror, sauberes `aclose()`. Stays inactive wenn `REDIS_URL` unset oder Redis unerreichbar.
  - Cutover für alle drei OASIS-Subprocess-Scripts (`run_reddit_simulation.py`, `run_twitter_simulation.py`, `run_parallel_simulation.py`): `IPCHandler.send_response` → async mit Redis-Mirror, `_execute_command` extrahiert (gemeinsamer Pfad für File-Polling und Bridge), `dispatch_bus_event` als Bridge-Callback, `seen_command_ids` dedupliziert beide Pfade.
  - Tests: 3 neue Hybrid-Round-Trip-Tests in `test_event_bus_redis.py` (Backend-publish reicht raw-Redis-Subscriber durch, raw-Redis-publish wird von Backend-subscribe konsumiert, voller `request_response`-Round-Trip ohne File-I/O), File-Fallback-Test als Regression-Garantie für Rolling-Upgrade. 3 Bridge↔Bus-Integrationstests in `test_subprocess_redis_bridge.py` (End-to-end ohne OASIS, `REDIS_URL=None`-Pfad, `publish_response` reicht raw-Subscriber durch). Phase-B-Delegation-Tests (`test_event_bus_redis_rpc_delegation.py`) gelöscht — sie sicherten den alten File-Pfad ab und sind mit der Migration obsolet.
  - Backout-Plan unverändert: `EVENT_BUS_BACKEND=file` setzen → Container baut `FilePollingEventBus`, Subprocess-Bridge geht in Standby, alles läuft wie vor #17.
  - Plan-Dokument `docu/issue-17-rpc-redis-plan.md` reflektiert den Abschluss der Phasen 1–6.
- **Issue #11 Phase 2 — NER → OntologyMutationService verdrahtet.** `Neo4jStorage` bekommt einen Setter `set_ontology_mutation_service()` (Late-Binding, vermeidet die zirkuläre Dependency `OntologyManager → Neo4jStorage → Service`). In `add_text` filtert `_evaluate_ontology_mutations()` NER-Output gegen die aktuelle `entity_types`-Liste der Ontologie und reicht alles Unbekannte an `OntologyMutationService.evaluate_batch` weiter — der Service entscheidet per Mode (`disabled`/`review_only`/`auto`) ob nur geloggt, im Audit-Log gehalten oder direkt patcht. `AgoraContainer.ontology_mutation_service()` ist jetzt Singleton und wird in `create_app` eagerly konstruiert, damit das Late-Binding noch vor dem ersten Build greift. Service-Exceptions werden geschluckt — Ontologie-Mutation ist Best-Effort und darf Ingestion nie blockieren. Tests: `test_neo4j_ontology_wiring.py` (8).

### Geändert

- **Backend-Lint-Scope auf `app/ tests/` gehoben.** `npm run lint:backend` lief bisher als gescopter Whitelist-Rollout; jetzt deckt er den ganzen Backend-Baum ab. 31 Pre-existing Ruff-Findings dafür erschlagen: 16 auto-fixed (F401/F541/F841), 15 manuell (E402-Importsortierung in `neo4j_storage.py`, E741 `l` → `lbl`, E722 bare-except → `(JSONDecodeError, ValueError)`, F841 ungenutztes Listing). Erledigt das „schrittweise Ausweitung von Ruff Richtung Default-strict" aus dem CLAUDE.md-Backlog.

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
