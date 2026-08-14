# Architektur-Layer

Datei: `docs/runbooks/architecture-layers.md` · Stand: 2026-08-14

## Layer-Uebersicht

Agora ist in 11 Layer gegliedert (0–10). Layer-Reihenfolge ist bindend:
**Layer N+1 darf nicht OHNE Layer N implementiert sein.**

| Layer | Name | Status | Beschreibung |
|---|---|---|---|
| 0 | Contracts | Gruen | Pydantic v2 Models, Single Source of Truth |
| 1 | Storage | Gruen | Neo4j Read/Write/Search, Embeddings, NER, Hybrid Search |
| 2 | Persona & Prompts | Gruen | Persona-Services, Report-Prompts, Voice-Register |
| 3 | OASIS-Integration | Gruen | CAMEL-AI Subprozess, Agent-Tools, IPC, Event-Bus |
| 4 | API | Gruen | 13 Flask Blueprints, Signed Tickets, Rate Limiting |
| 5 | Frontend-Shell | Gruen | Vue 3 + TypeScript + Pinia + Vite, v4-Shell |
| 6 | Pipeline-UI | Gruen | Step-Components, SSE, Polling-Composables |
| 7 | Report-Generation | Gruen | ReportV3, Section-ReAct, Evidence-Gating (ADR-0002) |
| 8 | Export | Gruen | Markdown, JSON, CSV, ZIP, Streaming-ZIP |
| 9 | Production | Gruen | Docker Multi-Stage, nginx, gunicorn, Compose |
| 10 | Observability | Gruen | OpenTelemetry, Health-Endpoints, Structured Logging |

---

## Layer 0 — Contracts

**Verzeichnis:** `backend/app/contracts/`

Single Source of Truth. Alle API-Vertraege sind Pydantic v2 Models mit
`extra="forbid"`. Keine Dataclasses, keine Inline-Schemas.

Wichtige Dateien:
- `report_contract.py` — ReportV3, Claim, EvidenceSourceKind
- `simulation_contract.py` — RunConfig, SimulationState, FSM
- `graph_contract.py` — Entity, Relationship, Ontology
- `persona_contract.py` — PersonaProfile, SegmentDefinition
- `embedding_contract.py` — EmbeddingConfiguration
- `dump_schemas.py` → `schemas/` — auto-generierte JSON-Schemas

**Regel:** Jede Contract-Aenderung braucht `dump_schemas`-Run + Schema-Check.

---

## Layer 1 — Storage

**Verzeichnis:** `backend/app/storage/`

Neo4j-Adapter (getrennt Read/Write/Search), Embeddings, NER, Hybrid Search.

Wichtige Dateien:
- `neo4j_read.py` — Lese-Queries
- `neo4j_write.py` — Schreib-Operationen
- `neo4j_search.py` — Vektor- und Keyword-Suche
- `neo4j_storage.py` — Lifecycle, Health, Retry-Wrapper
- `neo4j_mappings.py` — Node/Edge-Mapping
- `embedding_service.py` — Embedding-Generierung (Ollama/OAI-compat.)
- `search_service.py` — Hybrid Search (Vector + Keyword)
- `ner_extractor.py` — Named Entity Recognition

---

## Layer 2 — Persona & Prompts

**Verzeichnisse:** `backend/app/services/persona_*.py`, `backend/app/services/report_prompts/`

Persona-Erzeugung, Eligibility, Demographics, Quality. Report-Prompt-Bausteine.

Wichtige Dateien:
- `persona_eligibility.py` — LLM-Eignungspruefung
- `persona_demographics.py` — demographische Generierung
- `persona_quality_service.py` — Qualitaetsbewertung
- `persona_quota_defaults.py` — Typbewusstes Capping
- `report_prompts/sections.py` — Evidence-Gating-Block (ADR-0002 Hartanker)
- `report_prompts/planning.py` — Report-Plan-Prompt
- `report_prompts/react.py` — ReAct-Loop-Prompt

---

## Layer 3 — OASIS-Integration

**Verzeichnisse:** `backend/app/services/simulation_*.py`, `backend/scripts/`

CAMEL-AI Subprozess-Management. Flask <> OASIS IPC via Event-Bus (Redis/File).

Wichtige Dateien:
- `simulation_runner.py` — Simulation starten/stoppen/pausieren
- `simulation_ipc.py` — IPC-Client fuer laufende Worker
- `event_bus.py` — Transport (Redis/InMemory/File, auto-detect)
- `scripts/_sim_common.py` — RNG-Seeding, Start-Hour-Offset
- `scripts/run_parallel_simulation.py` — Dual-Platform (Twitter+Reddit)
- `oasis_profile_generator.py` — OASIS-Persona-Profile

---

## Layer 4 — API

**Verzeichnis:** `backend/app/api/`

13 Flask Blueprints, Signed Ticket Auth, Rate Limiting. 176 Route-Dekoratoren.

Wichtige Module:
- `simulation_lifecycle.py`, `simulation_prepare.py`, `simulation_run.py`, `simulation_profiles.py` — Simulation (groesster Blueprint)
- `report.py` — Report-Generierung, Evidence, Export, Chat
- `graph_build.py`, `graph_data.py`, `graph_projects.py` — Graph-Operationen
- `runs.py`, `llm_routing.py` — Run-Management und LLM-Routing
- `llm_providers.py`, `embedding_configurations.py` — Provider-CRUD

---

## Layer 5 — Frontend-Shell

**Verzeichnis:** `frontend/src/`

Vue 3 + TypeScript + Pinia + Vite. v4-Shell mit AppShell, Topbar, Sidebar.

Wichtige Verzeichnisse:
- `components/v4/shell/` — AppShell, Topbar, Sidebar, PageHeader
- `stores/` — Pinia-Stores (settings, simulation, report, project)
- `contracts/` — Zod-Spiegel zu Pydantic-Contracts
- `router/index.ts` — eine Route je fachlicher Hauptfunktion (ADR-0010)

---

## Layer 6 — Pipeline-UI

**Verzeichnis:** `frontend/src/components/`

Step-Komponenten fuer die Pipeline, SSE-Integration, Polling-Composables.

Wichtige Dateien:
- `composables/usePolling.ts` — generisches Polling
- `composables/useRunsPolling.ts` — Run-Status-Polling
- `composables/useIncrementalLogPolling.ts` — Log-Streaming
- `composables/useEventStream.js` — SSE-Client mit Reconnect
- `v4/forms/AiModelPicker.vue` — kanonische Modellauswahl

---

## Layer 7 — Report-Generation

**Verzeichnis:** `backend/app/services/report_agent/`, `backend/app/services/report_*.py`

ReportV3-Modell, Section-ReAct-Loop, Evidence-Gating (ADR-0002, 5 Hartanker).

Wichtige Dateien:
- `report_agent/` — Orchestrator, Tool-Execution, Evidence-Binding
- `report_generation.py` — Generierungs-Lifecycle
- `report_export.py` — Multi-Format-Export
- `report_status.py` — Fortschritt und Phasenbericht
- `report_prompts/sections.py` — `<evidence_gating priority="hard">`-Block

---

## Layer 8 — Export

**Dateien:** `backend/app/services/report_export.py`, `backend/app/services/graph_export.py`

Markdown-, JSON-, CSV- und ZIP-Export. Streaming-ZIP fuer grosse Reports.

Alle Exportformate validieren Evidence ueber dieselbe kanonische Kette.
Vertragswidrige Evidenz liefert `evidence-omitted.json` statt `evidence-map.json`.

---

## Layer 9 — Production

**Verzeichnisse:** `deploy/`, `Dockerfile`, `docker-compose*.yml`

Multi-Stage Docker Build, nginx Reverse-Proxy, gunicorn mit `--preload` (fork-safe).

---

## Layer 10 — Observability

**Verzeichnis:** `backend/app/observability/`

OpenTelemetry-Integration, Health-Endpoints, Structured Logging.

Wichtige Dateien:
- `metrics.py` — OTEL-Metriken
- `tracing.py` — Distributed Tracing
- `logging_bridge.py` — Structured-Logging-Bridge
- `redis_propagator.py` — Trace-Context-Propagation ueber Redis

Konfiguration ueber `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` etc.

---

## Security

### AGORA_CORS_ALLOW_ALL

**Env-Variable:** `AGORA_CORS_ALLOW_ALL` (Default: `false`)

Setzt den CORS-Origin-Filter auf Wildcard (`*`) und deaktiviert
`Access-Control-Allow-Credentials`. Browser lehnen Wildcard + Credentials ab (CORS 8.7).

- **Nur in Entwicklung** zulaeissig (`FLASK_DEBUG=true`).
- In Produktion verweigert die App den Start (fail-closed, Issue #592).
- **Alternative fuer Prod:** `AGORA_EXTRA_ORIGINS` als komma-separierte Whitelist.

---

## Gotchas

### Kein CAMEL-Floor unterlaufen

`_resolve_memory_token_limit(model_name)` ist der EINZIGE Pfad fuer Token-Limits.
Hartkodierte Defaults in CAMEL/OASIS sind verboten.

### Kein Layer-Skip

Layer 7 braucht Layer 6 braucht Layer 4 braucht Layer 0. Keine Abkuerzung.

### Event-Bus-Double-Wiring

`EVENT_BUS_BACKEND=auto` probiert Redis, faellt auf File zurueck. Beide Pfade
muessen funktionieren — in CI gibt es kein Redis.

### Persona-Mindestanzahl

Die Pipeline validiert `PERSONA_MIN_COUNT` (Default: 8). Weniger Personas
brechen den Run ab.

### Embedding-Dimension-Match

`EMBEDDING_MODEL` und `VECTOR_DIM` muessen zusammenpassen. Backend prueft beim
Start mit einer echten Embedding-Probe.
