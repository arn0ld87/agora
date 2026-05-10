# AGENTS.md

Guidance für Codex und andere Agent-Runtimes in diesem Repository.

> **Hinweis:** [`CLAUDE.md`](CLAUDE.md) ist die Schwesterdatei für Claude Code und bleibt fachlich synchron zu diesem Dokument. Verbindliche Test-Counts und Versionsstände: [`docu/STATUS.md`](docu/STATUS.md). Operative Findings/Slices: [`PLAN.md`](PLAN.md). Subagent-Heuristiken (Slice → Subagent → Akzeptanz): [`docu/plan.heuristic.md`](docu/plan.heuristic.md).

## Projekt

Agora ist ein **lokal-first** Multi-Agent-Simulator für DACH-Zielgruppenreaktionen. Pipeline: Dokument hochladen → Wissensgraph extrahieren → personalisierte Personas spawnen → Social-Media-Reaktionen simulieren (OASIS) → DACH-Report erzeugen. Fork-Linie: ursprünglich aus `nikmcfly/MiroFish-Offline`, seit v0.x ersetzt durch Neo4j (statt Zep Cloud) und Ollama-/OpenAI-kompatible Endpunkte (statt DashScope).

**Stack:** Flask (Python 3.11) + Pydantic v2 + Vue 3 + Vite + Pinia + Neo4j 5.18 CE + OASIS (`camel-oasis`) + Redis (Pub/Sub-IPC) + Ollama. Package-Manager: `uv` fürs Backend, `npm` fürs Frontend.

**Status:** v0.9.0+ post-tag · Layer 0–6 grün · Layer 7–8 teilweise · Layer 9–10 grün · M11 Phase 1–5b durch. **v1.0-Output-Vertrag-Plan** ([`PLAN.md`](PLAN.md)): Phase 1 + P2.1/P2.2/P3.1/P3.3/P3.4/P4.2 grün; offen P3.2-Verdrahtung, P4.1, P4.3, P4.4. Test-Counts und Layer-Status laufen ausschließlich über [`docu/STATUS.md`](docu/STATUS.md) — keine Inline-Zahlen mehr in README/CLAUDE.md/AGENTS.md.

## Sofort wichtig

- **Branch-Hygiene:** Nie auf `main` direkt pushen. Branch-Namen: `feat/task-XX-kurztitel`, `fix/<scope>-<slug>`, `chore/<scope>-<slug>`. Linear-FF-Merge auf `main`, keine Rewrites publizierter Commits.
- **Layer-Reihenfolge ist verbindlich.** Layer 1 ohne Layer 0 ist verboten. Detail-Tabelle siehe [`CLAUDE.md` § Architektur-Layer](CLAUDE.md#architektur-layer-status).
- **Tests sind die Spec.** Pflichttests vor Refactor lesen. TDD: erst RED, dann GREEN, dann Commit. Ausnahmen begründen.
- **Pakete unter Linux:** `nala` statt `apt`. Python-Deps via `uv`.
- **Keine US-Cloud-Lock-ins.** Ollama-/OpenAI-kompatible Fallbacks bleiben Pflicht.

## PR-Workflow (Pflicht)

Nach jedem `gh pr create`:

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews  --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

**Gemini-Code-Assist** reviewt automatisch innerhalb ~60–120 s. Findings nach Priorität:

1. **HIGH** — immer adressieren, bevor mergen. Direkt im selben Branch nachpatchen oder als Followup-Sub-Slice (`fix(scope): Gemini-Followup auf <PR#>`).
2. **MEDIUM** — je nach Scope. i18n-Misses, Exception-Specifity, stable-keys → meistens fixen. Style-Geschmack → explizit ablehnen im Arbeitsprotokoll, nicht stillschweigend ignorieren.
3. **LOW** — kann oft als „Out of Scope" gemerged werden, mit Verweis im Arbeitsprotokoll.

Erst nach Findings-Sichtung mergen — `git checkout main && git merge --ff-only <branch> && git push origin main`.

## Erwartete Tool-Nutzung (proaktiv)

- **code-review-graph** — Pflicht-First-Stop bei Code-Exploration, *bevor* `rg`/`grep`/`Read`/`Glob`. Tree-sitter-basierter persistenter Knowledge-Graph mit strukturellem Kontext (Caller, Dependents, Test-Coverage). Tool-Routing:

  | Frage | Graph-Tool | Statt |
  |---|---|---|
  | Code-Review eines Diff | `detect_changes` + `get_review_context` | komplette Files via `Read` |
  | Blast-Radius einer Änderung | `get_impact_radius` | manuelles Import-Tracing |
  | Welche Flows sind betroffen? | `get_affected_flows` | `rg` durch alle Service-Files |
  | Wer ruft `<symbol>` auf? | `query_graph` mit `pattern=callers_of` | `rg "<symbol>"` |
  | Caller/Callee/Tests für `<symbol>` | `query_graph` mit `pattern=callees_of` / `tests_for` | `rg` |
  | Funktion/Klasse finden | `semantic_search_nodes` | `rg "def <name>"` |
  | Architektur-Überblick | `get_architecture_overview` + `list_communities` | mehrere `Read` über `__init__.py` |
  | Refactor-Hot-Spots | `find_large_functions_tool` + `get_hub_nodes_tool` | manuelle `git grep` |
  | Refactor-Planung (Renames, Dead-Code) | `refactor_tool` | manuelle Cross-Repo-Suche |

  **Fallback auf `rg`/`grep`/`Read`** nur wenn der Graph die Frage nicht abdeckt: Bash-Skripte, GitHub-Workflow-yml, Markdown, Config-Files, generierte Schemas. Der Graph parst Code-Symbole — bei Nicht-Code-Files ist Direkt-Lesen korrekt.

  Workflow: Graph aktualisiert sich automatisch via Hooks. Bei Code-Review zuerst `detect_changes` für Risk-Score. Vor Refactor `get_minimal_context_tool` (token-spart gegenüber `Read` ganzer Files). Vor Slice-Cuts in verbleibenden Hot-Spots `get_hub_nodes_tool` für Schnitt-Grenzen. F8 Frontend-Hotspots sind bereits unter Schwelle (667 LOC / 797 LOC).

- **context7** — bei jeder Task, die Bibliotheken/Frameworks/SDKs/CLIs/Cloud-Services berührt (Flask, Pydantic v2, Vue 3, Vite, Pinia, Neo4j-Driver, OASIS/CAMEL, Ollama, OpenAI-kompatible Chat-/Tool-Call-APIs, pytest, uv, …): aktuelle Docs prüfen, **bevor** Code geschrieben wird.
- **GitHub-Suche / `gh`** — Debugging von Third-Party-Verhalten (OASIS-Eigenheiten, Neo4j-Vector-Search-Kanten, Ollama-Tool-Call-Payloads, Qwen/GPT-OSS-Reasoning-Blöcke, CAMEL-Memory-/Context-Edge-Cases) zuerst gegen Upstream-Issues/PRs spiegeln.
- **sequential-thinking** — automatisch für Multi-File-Refactors, pipelinespannende Änderungen (graph → env → simulation → report), Debugging über die Flask↔OASIS-Subprozess-Grenze, oder Tasks mit unklarem Lösungspfad.

Defaults, keine Eskalation. Wenn du eins davon überspringst, notiere kurz warum.

## Stack-Map

```
backend/                    Python 3.11, uv, Flask, Pydantic v2, pytest
  app/
    contracts/              Layer 0: Single Source of Truth (Pydantic v2, extra="forbid")
    api/                    HTTP-Routen (Flask Blueprints — auth, simulation_*, graph, report, runs, status)
    services/               Business-Logik
      report_agent.py       schema_version=2, EvidenceMapModel-Validation (Sub-Slice 02a-c)
      evidence_binder.py    Contradiction-Penalty, kein dekoratives Fallback (Sub-Slice 07)
      confidence_calculator.py  Match-Score-Cap + Verified-Quellen-Gate (Sub-Slice 08)
      oasis_profile_generator.py  voice_register-Pflichtfeld (Sub-Slice 10)
      prepare_service.py    PersonaQuotaPlan-Pipeline (Sub-Slice 20a/b/22)
      simulation_runner.py  OASIS_DB_PATH pro Sim (Sub-Slice 21)
      persona_review_service.py  Lifecycle pending|approved|rejected
      run_registry.py       Run-State-Persistenz
      event_bus.py          InMemory|FilePolling|RedisEventBus
    models/                 Dataclasses (legacy, werden migriert)
    storage/                Neo4j-Adapter, Embedding, NER, Search
    utils/llm_client.py     chat_json strict-Schema-Mode (Sub-Slice 05)
    utils/auth.py           Bearer + signed tickets, ?token= in Non-Debug abgelehnt (F2.2)
  tests/contracts/          Pflicht für jeden Vertrag
  tests/api/                Schema-Tests, jsonschema-basiert
  tests/services/
  tests/eval/               Baseline-Eval-Suite + Snapshots (Sub-Slice 17)
  scripts/                  OASIS-Subprozess + run_*_simulation.py
frontend/                   Vue 3 + TS + Pinia + Vitest + Zod
  src/
    contracts/              Zod-Spiegel zu backend/app/contracts/ (auto-generiert via dump_schemas)
      personaQuotaContract.ts  Sub-Slice 20c/24
      reportContract.ts        Sub-Slice 02b
    api/                    index.ts, graph.ts, simulation.ts, report.ts, runs.ts, stream.ts (signed tickets)
    composables/            10/10 TypeScript (#72 grün) — useEventStream, usePolling, useWorkspaceMode, …
    components/Step*.vue    Pipeline-Steps (667/797/877 LOC — Step2/4 erledigt per F8, Step3 noch offen)
    layouts/Workspace*.vue  Workspace-Shell (EPIC-03)
schemas/                    auto-generiert via `python -m app.contracts.dump_schemas`
deploy/
  nginx/agora.conf          Reverse-Proxy (SSE-Buffering aus, /healthz, statisch + /api/*)
  compose/docker-compose.prod-with-proxy.yml  Sidecar-Topologie
docu/                       Architektur, Logs, Plans, Arbeitsprotokolle, ADRs
prompts/                    UI-Prompt-Vorlagen
```

## Architektur-Layer (Status)

Verbindliche Detailtabelle: [`CLAUDE.md` § Architektur-Layer](CLAUDE.md#architektur-layer-status). Kurzfassung:

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel + JSON-Schema-Dump | grün |
| 1 | Backend-Hardening (Quoten, Evidence-Dedup, Confidence) | grün |
| 2 | DACH-Voice + Glossar v1 (`future prediction` weg) | grün |
| 3 | Reader-Honesty (Quotes, Time-Series, Section-Dedup) | grün |
| 4 | Frontend (Zod-strikt, Diff/Confidence-UI, Quoten) | grün |
| 5 | Eval/Baseline-Suite + v1→v2-Migration | grün |
| 6 | Frontend-TypeScript-Migration (API, Composables, Pinia) | grün |
| 7 | Graph / Runs / Compare | teilweise — offen: #74, #66, #67, #63 |
| 8 | Persona Review + UX | teilweise — offen: #69, #70, #137 |
| 9 | Production Deployment | grün mit bewusst pausiertem PR-Smoke — Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, ?token=-Block ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke auf `main`/Tags/`workflow_dispatch` ✅; PR-Trigger seit 2026-05-06 wegen ~30 min Laufzeit pausiert und vor Release neu zu bewerten |
| 10 | Security Watchlist (CVE-Tracking) | grün — CVE-Monitor-Workflow + Hardstop 2026-07-30 aktiv; Upstream-Pins blockieren weitere Closes |

## Pipeline (Vier-Stufen)

1. **Graph Build** — Dokument chunken → parallele `storage.add_text` (NER/RE → Embeddings → Neo4j). Tuning: `GRAPH_CHUNK_SIZE`, `GRAPH_CHUNK_OVERLAP`, `GRAPH_PARALLEL_CHUNKS`.
2. **Env Setup** — Persona- und Simulation-Config generieren; Konfiguration eingefroren in `uploads/simulations/<sim_id>/simulation_config.json`. Persona-Review-Gate (`PERSONA_REVIEW_ENABLED=true`) blockiert `POST /api/simulation/start` mit `409 persona_review_required`, solange nicht alle Personas `approved` sind.
3. **Simulation** — OASIS läuft als separater Subprozess; IPC über `SimulationEventBus` (Redis Pub/Sub Default seit Issue #17, File-Fallback bleibt). `SimulationRunner.register_cleanup()` killt Orphans beim Shutdown. `SimulationRunner` setzt `OASIS_DB_PATH` pro Sim (Sub-Slice 21).
4. **Report** — `ReportAgent` nutzt `GraphToolsService` und optional `WebTools`. Loop-Limits via `REPORT_AGENT_MAX_TOOL_CALLS` und `REPORT_AGENT_MAX_REFLECTION_ROUNDS`. EvidenceMapModel + Confidence-Calculator + Section-Dedup garantieren Reader-Honesty-Output.

### Event-Bus & SSE (#9 + #17)

- `backend/app/services/event_bus.py` — `SimulationEventBus` mit Channels `control`, `state`, `rpc.command`, `rpc.response.<id>`, `action`. Drei Adapter: `InMemoryEventBus` (Tests), `FilePollingEventBus` (offline-first), `RedisEventBus` (Compose-Default via `redis:7-alpine`). Backend-Wahl: `Config.EVENT_BUS_BACKEND` (`auto` | `redis` | `file`).
- **Live-Kanäle** `control`/`state` über Redis Pub/Sub mit retained Snapshot im Artifact-Store für späte Subscriber.
- **RPC-Kanäle** hybrid (Issue #17): Backend published parallel auf Redis + File, `_await_response` race't beide Quellen, first-come-wins. Subprocess-Listener `RedisIPCBridge` (`backend/scripts/subprocess_redis_bridge.py`) läuft im OASIS-Eventloop neben dem File-Polling. Ohne `REDIS_URL` bleibt die Bridge inaktiv.
- **SSE-Bridge** `GET /api/simulation/<id>/stream` mit 15-s-Heartbeat; Frontend nutzt `frontend/src/composables/useEventStream.ts`. Auth läuft über **signed tickets** (`?ticket=...`, single-use für Downloads / TTL-bound für SSE), nicht über `?token=`.

### Graph-Analytik

- **Temporal Graph (#10):** `RELATION`-Kanten tragen `valid_from_round`, `valid_to_round`, `reinforced_count`. `TemporalGraphService` liefert `get_snapshot`/`compute_diff`. APIs: `GET /api/graph/snapshot/<gid>/<round>`, `GET /api/graph/diff/<gid>?start_round=..&end_round=..`. Lazy Backfill stampt Pre-#10-Kanten auf `valid_from_round=0`.
- **Polarisation (#12):** `NetworkAnalyticsService` mappt OASIS-Aktionen auf einen `networkx`-Interaktionsgraph, liefert Louvain-Communities, Echo-Chamber-Index und Betweenness-basierte Bridge-Agents. API: `GET /api/simulation/<id>/metrics?window_size_rounds=&platform=`.
- **Ontology-Mutation (#11 Phase 1+2):** `OntologyManager` (thread-safe per-graph-Locks) + `OntologyMutationService` mit Modi `disabled`/`review_only`/`auto`. NER-Pipeline reicht unbekannte Entitäts-Typen automatisch durch (`Neo4jStorage.add_text` → `_evaluate_ontology_mutations()`). Service-Exceptions blockieren Ingestion nicht.

### Operability

- `GET /api/status` — `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp`, `auth_mode`.
- `Neo4jStorage` mit `neo4j_call_with_retry` (Exponential Backoff + Jitter, max 3 Retries bei `ServiceUnavailable`/`SessionExpired`/`TransientError`).
- `LLMClient.chat`/`describe_image` mit `llm_call_with_retry` gegen transiente Upstream-Fehler (`APIConnectionError`, `APITimeoutError`, `RateLimitError`, `APIStatusError` 5xx/408/429). 4xx fallen sofort durch. Knöpfe: `LLM_MAX_RETRIES`, `LLM_RETRY_INITIAL_DELAY`, `LLM_RETRY_MAX_DELAY`.
- 8-Zeichen Request-IDs, `RunRegistry` für Langläufer.
- Atomische JSON-Writes + defensive Reads (`utils/json_io.py`).
- `Neo4jStorage`-Startfehler werden in `app.extensions['neo4j_storage_error']` gespiegelt und über `/api/status` + `/api/simulation/available-models` ausgeliefert; UI zeigt den echten Fehler.

## Production-Deployment (Layer 9)

**Stand 2026-05-06:** Wesentliche Hardening-Pfade sind im Repo aktiv. Der Proxy-Stack-Smoke existiert in `docker-image.yml::prod-proxy-smoke` fuer `main`/Tags/`workflow_dispatch`; der PR-Trigger ist wegen ca. 30 Minuten Laufzeit pro Iteration bewusst pausiert und vor dem finalen Release-Gate neu zu bewerten.

### Aktiv (code-verifiziert)

- **Reverse-Proxy** als Sidecar: [`deploy/nginx/agora.conf`](deploy/nginx/agora.conf) (SSE-`proxy_buffering off`, `/healthz` direkt, `/api/*` → Backend, `/` → statisches Bundle). Topologie: [`deploy/compose/docker-compose.prod-with-proxy.yml`](deploy/compose/docker-compose.prod-with-proxy.yml).
- **Gunicorn `-k gevent`** in `Dockerfile` `prod`-Stage. SSE und Long-Requests blockieren keine Sync-Worker mehr. Caveat: gevent-Monkey-Patching ↔ OASIS-Subprozess-Entkopplung muss bei jedem Slice-Touch per Smoke verifiziert werden (`scripts/verify-deploy.sh`).
- **Bundle-Token-Gate:** `Dockerfile` ARG `ALLOW_BUILD_TIME_TOKEN=false` (Default) — `VITE_AGORA_TOKEN` wird **nicht** ins Bundle einkompiliert. Frontend muss den Token zur Laufzeit setzen (`setAgoraToken()` in `frontend/src/api/index.ts`). Compose: `docker-compose.prod.yml` reicht den Gate-ARG durch.
- **`?token=` in Prod blockiert** (`backend/app/utils/auth.py::_extract_token`): bei `current_app.debug == False` wird der Query-Token abgelehnt; SSE/Downloads müssen **signed tickets** (`?ticket=`) nutzen, ausgegeben über `POST /api/auth/ticket` (60 s TTL, scope-bound, single-use).
- **Frontend signed tickets:** `frontend/src/api/stream.ts` holt das Ticket via `POST /api/auth/ticket` und hängt `?ticket=<scoped>` an die SSE-URL.
- **Loopback-Default:** `docker-compose.yml` und `docker-compose.prod.yml` binden Backend/Neo4j auf `127.0.0.1`. Override für Tailnet/LAN: `AGORA_BIND_HOST=0.0.0.0` oder `docker-compose.override.yml`.
- **Container-Hardening:** `no-new-privileges`, `cap_drop: ALL`, tmpfs für Runtime-Pfade, Pflicht-Passwörter (Compose-Validation lehnt Defaults ab).
- **Config fail-fast:** `Config.validate()` lehnt Start ab bei fehlendem `SECRET_KEY`, `NEO4J_PASSWORD`, `AGORA_AUTH_TOKEN` im Non-Debug-Modus. Placeholder-Werte werden erkannt.

### Offen / nächster Slice

- **Final-Release-Smoke-Gate:** PR-Trigger oder Release-Candidate-Trigger fuer `docker-image.yml::prod-proxy-smoke` vor v1.0 neu aktivieren oder durch ein gleichwertiges finales Gate ersetzen.
- **CVE-Monitor + Hardstop** (M10.1/M10.2): wöchentlicher `pip-audit` ohne `--ignore-vuln`, Hardstop am 2026-07-30 — Issues #121–#126.

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

# Quality-Gate (lint + test + build)
npm run check

# Backend-Spezifika
cd backend && uv sync --group dev
cd backend && uv run pytest -x -q
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run python -m app.contracts.dump_schemas
cd backend && uv run ruff check . && uv run mypy app

# Frontend-Spezifika
cd frontend && npm ci
cd frontend && npm run check
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npm run build

# Container (Prod-Stack inkl. Proxy)
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
docker exec agora curl -fsS http://localhost:5001/health

# Schema-Drift-Check (CI lokal simulieren)
git diff --exit-code schemas/    # nach dump_schemas darf nichts driften
```

## Konfiguration

Alles läuft über `.env` am Repo-Root, geladen von `backend/app/config.py`.

**Pflicht im Non-Debug:** `LLM_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`, `SECRET_KEY`, `AGORA_AUTH_TOKEN` (Override: `AGORA_ALLOW_ANONYMOUS=true` für Lab/Klassenraum).

Wichtige nicht-offensichtliche Knöpfe:

- **`EMBEDDING_MODEL` ↔ `VECTOR_DIM` müssen zusammenpassen** (fail-fast beim Startup inkl. echter Probe gegen das Embedding-Backend):
  - `nomic-embed-text` → 768
  - `embeddinggemma:300m` → 768
  - `qwen3-embedding:4b` → 2560
  - `qwen3-embedding:8b` → 4096
- `LLM_MODEL_NAME` — Default `qwen2.5:32b`; für Ollama Cloud empfohlen `qwen3-coder-next:cloud`.
- `OLLAMA_THINKING=false` — strippt Reasoning-Blöcke bei Qwen3/GPT-OSS/DeepSeek-R1.
- `LLM_DISABLE_JSON_MODE=true` — deaktiviert `response_format=json_object`; Markdown-Fences werden in `chat_json()` gestrippt.
- `LLM_CONTEXT_LIMIT` / `LLM_MODEL_CONTEXT_LIMITS_JSON` — überschreiben die Pro-Modell-Heuristik aus `backend/scripts/agent_tools.py::_heuristic_context_limit()`. Wichtig für CAMEL-`ScoreBasedContextCreator`-Floor; ohne Override kappt CAMEL bei 8192.
- `GRAPH_CHUNK_SIZE=1500`, `GRAPH_CHUNK_OVERLAP=150`, `GRAPH_PARALLEL_CHUNKS=4` — Graph-Build-Tuning.
- `ONTOLOGY_MAX_TOKENS=12288` — Output-Budget für `/api/graph/ontology/generate`. Cloud-Reasoning-Modelle emittieren 5–10 k Tokens; mit 4096 wurde die JSON-Antwort mid-string abgeschnitten.
- `HYBRID_SEARCH_VECTOR_WEIGHT=0.7`, `HYBRID_SEARCH_KEYWORD_WEIGHT=0.3` — Mischung im `SearchService`. Müssen sich nicht zu 1.0 summieren (Normalisierung pro Seite).
- `REPORT_LANGUAGE=German`, `AGENT_LANGUAGE=de`, `TIME_PROFILE=dach_default` — DACH-Defaults.
- `ENABLE_AGENT_TOOLS=false` — experimentelles OASIS-Tool-Use, opt-in.
- `PERSONA_REVIEW_ENABLED=false` — Persona-Review-Gate. Wenn `true`, blockiert `POST /api/simulation/start` mit `409 persona_review_required`.
- `AGORA_AUTH_TOKEN` — API-Token-Schutz für `/api/*`. Außerhalb von `FLASK_DEBUG=true` Pflicht.
- **Signed Tickets (P0.2):** SSE und Downloads akzeptieren statt `?token=<bearer>` ein `?ticket=<signed>`. Tickets via `POST /api/auth/ticket` (Header-Auth) gegen `SECRET_KEY`, 60 s gültig, scope-bound (`sse:<sim_id>` / `download:report:<id>`), single-use für Downloads. **`?token=` ist im Non-Debug-Modus deaktiviert (F2.2).**
- `AGORA_EXTRA_ORIGINS` / `AGORA_CORS_ALLOW_ALL=true` — CORS standardmäßig auf `localhost:5173` / `127.0.0.1:5173` gelockt.
- `AGORA_LOG_FORMAT=text|json` — opt-in JSON-Logs.
- `AGORA_BIND_HOST=0.0.0.0` — Override zum Default `127.0.0.1` für Tailnet/LAN-Deploys.
- `EVENT_BUS_BACKEND=auto|redis|file` — IPC-Adapter-Wahl. `REDIS_URL` aktiviert die Redis-IPC-Bridge.
- `TAVILY_API_KEY` + `ENABLE_WEB_TOOLS=true` — optionaler Live-Web-Kontext für den ReportAgent.

## Subagent-Routing (Codex / Multi-Runtime)

Optimierungsziel ist **Rework-Vermeidung**, nicht Token-Sparen. Layer-0-Drift oder Wording-Glossar-Verstöße kosten in der Re-Review mehr als ein direkter Senior-Modell-Run gespart hätte.

| Aufgabe | Modell-Profil | Subagent-Profil |
|---|---|---|
| Architektur-Entscheidung, Cross-Layer-Refactor, ambige Specs | senior | (Lead) |
| Code-Review kritischer Pfade (contracts, evidence_binder, report_agent) | senior | `code-reviewer` |
| Refactor 2+ Dateien, Pydantic-Migration | mid | `agora-refactor-worker` |
| Pydantic-Tests, FSM-Übergänge, Persona-Quoten | mid | `agora-test-worker` |
| Vue/Pinia/Zod-Spiegel | mid | `agora-frontend-worker` |
| Read-only Audit (Evidence, Wording-Glossar) | mid | `agora-evidence-auditor` |
| Dokumentation, CHANGELOG, Arbeitsprotokolle | klein | `agora-doc-worker` |

Detail-Mapping mit Akzeptanzkriterien je Slice: [`docu/plan.heuristic.md`](docu/plan.heuristic.md).

### Senior-Trigger (überstimmen das Default-Routing)

- Layer-0 (Pydantic-Contracts) wird angefasst
- Mehrere Layer gleichzeitig betroffen
- Wording-/Prompt-Semantik (Layer 2, Glossar v1)
- Spec ist ambig oder Tests fehlen
- Pre-PR-Self-Review **vor** `gh pr create` (fängt Drift bevor Gemini sie sieht)

## Conventions & Gotchas

- **Neo4j muss 5.18+** sein.
- Backend-Env-Änderungen wirken erst nach **Backend-Restart**, nicht nach Flask-Reload.
- Uploads: `backend/uploads/`; Simulationen: `backend/uploads/simulations/<sim_id>/`.
- Erlaubte Upload-Extensions: `pdf`, `md`, `txt`, `markdown`. `MAX_CONTENT_LENGTH = 50 MB`.
- Secrets werden **nicht** in `simulation_config.json` oder andere persistierte Artefakte serialisiert.
- Upstream-Chinesisch in Attribution/Migrations-Inventaren kann bleiben; Runtime-Defaults gehen von DACH aus.
- **Vector-Index Dimension-Drift (Issue #263):** Bei Embedding-Modell-Wechsel mit anderer Dimension erst Indexe droppen, dann neu anlegen. `CREATE VECTOR INDEX … IF NOT EXISTS` matcht nur über Index-Namen, nicht über Dimensionen.
- **CAMEL-`ScoreBasedContextCreator`-Floor:** Neue OASIS/CAMEL-Runner-Skripte müssen `apply_camel_context_floor()` + `enforce_memory_token_limit()` nach `generate_*_agent_graph(...)` aufrufen. Sonst kappt CAMEL jeden Agent-Memory bei 8192 Tokens, unabhängig vom realen Modell-Context. Floor zentral in `backend/scripts/_sim_common.py`.

## Verboten

- Dataclasses für API-Verträge → Pydantic v2 (`extra="forbid"`).
- Inline-JSON-Schemas → immer aus Pydantic ableiten via `model_json_schema()`.
- `apt` (nutze `nala`).
- US-Marketing-Phrasen in Reports („revolutionary", „seamless", „prediction of the future").
- Wording-Glossar v1 verletzen (siehe [`docu/glossary-wording.md`](docu/glossary-wording.md), Issue #175): `prediction`, `rehearsal`, `god's eye view`, `high-fidelity digital world`, `public opinion prediction`, `Agentic-Prediction-Engine` → durch Glossar-Equivalente ersetzen.
- `print()` in Prod-Code → strukturiertes Logging via `app.logger`.
- Schema-Strings inline kopieren → über Re-Export aus `app.contracts`.
- `git push --no-verify` ohne explizite User-Freigabe.
- Auf `main` mergen ohne Gemini-Findings-Sichtung.
- Hartkodierte UI-Strings in `Step*.vue` — immer `vue-i18n` (`t(...)`) + Keys in `de.json`+`en.json`.
- Hartkodierte `token_limit`-Defaults in CAMEL-/OASIS-Anbindungen (8192, 4096, 16384) — immer aus `_resolve_memory_token_limit(model_name)` lesen.
- Neue Query-Tokens (`?token=`) in URLs — Signed Tickets (`?ticket=`) sind der einzige URL-bound Auth-Pfad.
- Neue „temporäre" CVE-Ignores ohne Issue, Owner, Deadline und Hardstop-Datum.

## Referenz

- [`docu/STATUS.md`](docu/STATUS.md) — Test-Counts, Versionen, aktiver Milestone (Single Source of Truth).
- [`PLAN.md`](PLAN.md) — Konsolidierter Findings- & Maßnahmenplan (F1–F14 + M9–M13).
- [`docu/plan.heuristic.md`](docu/plan.heuristic.md) — Subagent-Mapping pro Slice.
- [`CLAUDE.md`](CLAUDE.md) — Schwester-Datei für Claude Code.
- [`docu/target-architecture.md`](docu/target-architecture.md) — Soll-Bild nach dem Refactoring.
- [`docu/security-hardening.md`](docu/security-hardening.md) — Security-Baseline.
- [`docu/glossary-wording.md`](docu/glossary-wording.md) — Wording-Glossar v1.
- [`docu/agent-tools-integration.md`](docu/agent-tools-integration.md) — OASIS-Agenten + GraphTools/WebTools.
- [`docu/graphrag-speedup.md`](docu/graphrag-speedup.md) — Ollama-Cloud-Tuning / Graph-Build-Speedup.
- [`docu/analytics.md`](docu/analytics.md) — Polarisations-/Echo-Chamber-Metriken.
- [`docu/decisions/`](docu/decisions/) — ADRs (Architecture Decision Records).
- [`docu/history/`](docu/history/) — Archivierte Audits, Reviews, alte Pläne.
- [`CHANGELOG.md`](CHANGELOG.md) — Release-Notes.
