# Architektur-Layer

Datei: `docs/runbooks/architecture-layers.md` · Stand: 2026-05-17

## Layer-Übersicht

Agora ist in 11 Layer gegliedert (0–10). Layer-Reihenfolge ist bindend:
**Layer N+1 darf nicht OHNE Layer N implementiert sein.**

| Layer | Name | Status | Beschreibung |
|---|---|---|---|
| 0 | Contracts | ✅ Grün | Pydantic v2 Models, Single Source of Truth |
| 1 | Storage | ✅ Grün | Neo4j-Adapter, Embeddings, NER, Hybrid Search |
| 2 | Persona-Prompts | ✅ Grün | Voice-Register, Wording-Glossar v1 |
| 3 | OASIS-Integration | ✅ Grün | CAMEL-AI Subprozess, Agent-Tools, IPC |
| 4 | API | ✅ Grün | Flask Blueprints, Signed Tickets |
| 5 | Frontend-Shell | ✅ Grün | Vue 3 + Pinia + Vite App-Shell |
| 6 | Pipeline-UI | ✅ Grün | Step-Components, SSE, Polling |
| 7 | Report-Generation | 🟡 Teilweise | ReportV3, Markdown-Renderer, Evidence-Gating |
| 8 | Export | 🟡 Teilweise | PDF/CSV/ZIP-Export |
| 9 | Production | ✅ Grün | Docker Multi-Stage, nginx, gunicorn, Compose |
| 10 | Observability | ✅ Grün | Health-Endpoints, Metrics-Pipeline |

---

## Layer 0 — Contracts

**Verzeichnis:** `backend/app/contracts/`

Single Source of Truth. Alle API-Verträge sind Pydantic v2 Models mit
`extra="forbid"`. Keine Dataclasses, keine Inline-Schemas.

Wichtige Dateien:
- `report_contract.py` — ReportV3, Claim, EvidenceSourceKind
- `simulation_contract.py` — RunConfig, SimulationState, FSM
- `graph_contract.py` — Entity, Relationship, Ontology
- `persona_contract.py` — PersonaProfile, SegmentDefinition
- `dump_schemas.py` → `schemas/` — auto-generierte JSON-Schemas

**Regel:** Jede Contract-Änderung braucht `dump_schemas`-Run + Schema-Check.

---

## Layer 1 — Storage

**Verzeichnis:** `backend/app/storage/`

Neo4j-Adapter, Embeddings, Named Entity Recognition, Hybrid Search (Vector + BM25).

Wichtige Dateien:
- `neo4j_adapter.py` — Graph-DB-Zugriff
- `embedding_service.py` — Embedding-Generierung (Ollama/OAI-compat.)
- `search_service.py` — Hybrid Search (Vector + Keyword)
- `ner_service.py` — Named Entity Recognition

---

## Layer 2 — Persona-Prompts

**Verzeichnis:** `backend/app/services/persona_prompts/`

Stimmen-Register, Wording-Glossar, Persona-Prompt-Templates.

Wichtige Konzepte:
- 4 Voice-Register: formal-de, neutral-de, technical-de, skeptisch-de
- Wording-Glossar v1: verbotene US-Marketing-Phrasen
- Anti-Dekorations-Regel: keine Adjektive ohne Evidence

---

## Layer 3 — OASIS-Integration

**Verzeichnis:** `backend/app/services/oasis/`, `backend/scripts/`

CAMEL-AI Subprozess-Management. Flask ↔ OASIS IPC via Event-Bus.

Wichtige Dateien:
- `sim_runner.py` — Simulation starten/stoppen
- `event_bus.py` — Transport (Redis/file auto-detect)
- `run_parallel_simulation.py` — Dual-Platform (Twitter+Reddit)
- `agent_tools.py` — Tool-Use für Social Agents

---

## Layer 4 — API

**Verzeichnis:** `backend/app/api/`

Flask Blueprints, Signed Ticket Auth, Rate Limiting.

Wichtige Dateien:
- `graph_routes.py` — Ontology, Entity, Search
- `simulation_routes.py` — Run-Start/Stop/Pause, SSE
- `report_routes.py` — Report-Generation + Chat
- `auth.py` — Signed Tickets (Redis-backed)

---

## Layer 5 — Frontend-Shell

**Verzeichnis:** `frontend/src/`

Vue 3 + TypeScript + Pinia + Vite. App-Shell mit Layout-System.

Wichtige Dateien:
- `App.vue` — Root-Component
- `layouts/` — Workspace, Dashboard
- `store/` — Pinia-Stores (settings, simulation, report)
- `contracts/` — Zod-Spiegel zu Pydantic-Contracts

---

## Layer 6 — Pipeline-UI

**Verzeichnis:** `frontend/src/components/`

Step-Komponenten für die Pipeline: Upload → Graph → Simulation → Report.

Wichtige Dateien:
- `StepUpload.vue` — Dokument-Upload
- `StepGraph.vue` — Wissensgraph-Visualisierung
- `StepSimulation.vue` — OASIS-Simulation-Feed
- `StepReport.vue` — Report-Rendering + Chat

---

## Layer 7 — Report-Generation

**Verzeichnis:** `backend/app/services/report_agent/`

ReportV3-Modell, Markdown-Renderer, Evidence-Gating (ADR-0002).

Status: Evidence-Gating aktiv (5 Anker), ReportV3 in Verwendung.
Offen: P3.2 (Markdown-Renderer aus ReportV3).

---

## Layer 8 — Export

**Verzeichnis:** `backend/app/services/export/`

PDF/CSV/ZIP-Export. PDF via Browser-Print (nicht serverseitig).

Status: Markdown-Export aktiv. CSV und ZIP-Bundle offen (P4.2, P4.3).

---

## Layer 9 — Production

**Verzeichnis:** `deploy/`, `Dockerfile`, `docker-compose*.yml`

Multi-Stage Docker Build, nginx Reverse-Proxy, gunicorn mit `--preload`.

Status: Aktiv und verifiziert. gunicorn fork-safety via `--preload` aktiv.

---

## Layer 10 — Observability

**Verzeichnis:** `backend/app/services/observability/`

Health-Endpoints, Metrics-Pipeline, Structured Logging.

Status: Health-Endpoints aktiv. Metrics-Pipeline geplant.

---

---

## Security

### AGORA_CORS_ALLOW_ALL

**Env-Variable:** `AGORA_CORS_ALLOW_ALL` (Default: `false`)

Setzt den CORS-Origin-Filter auf Wildcard (`*`) und deaktiviert gleichzeitig
`Access-Control-Allow-Credentials`. Hintergrund: Browser lehnen die Kombination
Wildcard-Origin + Credentials per Spec ab (CORS §8.7); flask-cors setzt
`supports_credentials=False` automatisch wenn `allow_all=true`.

**Verwendung:**

- **Nur in Entwicklung** zulässig, z.B. wenn Frontend und Backend auf
  unterschiedlichen Ports laufen und kein Cookie-Auth benötigt wird.
- **Niemals in Produktion** — auch nicht temporär. Die App verweigert den Start
  wenn `AGORA_CORS_ALLOW_ALL=true` im Produktionsmodus gesetzt ist, also wenn
  `FLASK_DEBUG` nicht `true` ist (fail-closed, Issue #592 — ohne explizites
  Dev-Signal greift der Guard).

**Alternative für Prod:** `AGORA_EXTRA_ORIGINS` als komma-separierte Whitelist,
z.B. `AGORA_EXTRA_ORIGINS=https://app.example.com,https://admin.example.com`.

---

## Gotchas

### Kein CAMEL-Floor unterlaufen

`_resolve_memory_token_limit(model_name)` ist der EINZIGE Pfad für Token-Limits.
Hartkodierte Defaults in CAMEL/OASIS sind verboten.

### Kein Layer-Skip

Layer 7 braucht Layer 6 braucht Layer 4 braucht Layer 0. Keine Abkürzung.

### Event-Bus-Double-Wiring

`EVENT_BUS_BACKEND=auto` probiert Redis, fällt auf File zurück. Beide Pfade
müssen funktionieren — in CI gibt es kein Redis.

### Persona-Mindestanzahl

Die Pipeline validiert `PERSONA_MIN_COUNT` (Default: 8). Weniger Personas
brechen den Run ab.

### Embedding-Dimension-Match

`EMBEDDING_MODEL` und `VECTOR_DIM` muessen zusammenpassen. Backend prueft beim
Start mit einer echten Embedding-Probe, sofern `AGORA_SKIP_EMBEDDING_PROBE`
den Preflight nicht ueberspringt.
