# Architektur

Agora ist ein lokal-first Fullstack-System für DACH-Zielgruppenreaktionen. Die Anwendung verbindet eine Vue-Oberfläche, eine Flask/Pydantic-API, Neo4j als Knowledge Graph, Redis als Event-/Ticket-Infrastruktur und OASIS/CAMEL als entkoppelte Simulationsruntime.

## Systemüberblick

```text
Browser
  -> Vue 3 / Vite / Pinia / Zod
  -> Flask API / Pydantic v2
  -> Services: Graph, Personas, Simulation, Report, Runs
  -> Runtime: Neo4j, Redis, Ollama/OpenAI-kompatibel, OASIS/CAMEL
```

Die Architektur ist bewusst lokal-first. Externe LLM-/Embedding-Endpunkte sind austauschbar, solange sie Ollama- oder OpenAI-kompatible APIs bereitstellen.

## Backend

Das Backend liegt unter `backend/` und läuft mit Python 3.11.

- `backend/app/contracts/` — Pydantic-v2-Verträge als Single Source of Truth
- `backend/app/api/` — Flask-Blueprints für Auth, Graph, Simulation, Report, Runs und Status
- `backend/app/services/` — Business-Logik für Graph Build, Personas, Simulation, Evidence, Reports und Metrics
- `backend/app/storage/` — Neo4j, Embeddings, NER und Search
- `backend/scripts/` — OASIS/CAMEL-Subprozess-Runner und Hilfsskripte
- `schemas/` — generierte JSON-Schemas aus den Pydantic-Verträgen

API-Verträge dürfen nicht als Dataclasses oder inline JSON-Schemas gepflegt werden. Neue API-Verträge gehören in `backend/app/contracts/` und werden über `python -m app.contracts.dump_schemas` exportiert.

## Frontend

Das Frontend liegt unter `frontend/` und läuft mit Vue 3, Vite, Pinia, TypeScript und Zod.

- `frontend/src/contracts/` — Zod-Spiegel der Backend-Verträge
- `frontend/src/api/` — API-Clients, Auth, Streams und Report-/Simulation-Endpunkte
- `frontend/src/composables/` — wiederverwendbare UI-/Datenlogik
- `frontend/src/components/` — Wizard, Report, Graph, Runs und UI-Komponenten
- `frontend/src/layouts/` — Workspace-Shells

Frontend-Code muss die Backend-Verträge strikt validieren. Harte UI-Strings in `Step*.vue` gehören in i18n-Dateien.

## Runtime-Komponenten

| Komponente | Rolle |
|---|---|
| Neo4j 5.18+ | Knowledge Graph, Entitäten, Relationen, Graph-Diff |
| Redis | Pub/Sub-IPC, retained Snapshots, signed-ticket single-use state |
| Ollama / OpenAI-kompatibel | LLM- und Embedding-Endpunkte |
| OASIS/CAMEL | Multi-Agent-Simulation als separater Subprozess |
| Docker Compose | Lokale und prod-ähnliche Runtime-Orchestrierung |
| Nginx-Sidecar | optionaler Reverse Proxy für prod-ähnliche Stacks |

## Pipeline

1. **Upload** — PDF, Markdown oder Text wird angenommen, validiert und im Upload-Bereich abgelegt.
2. **Graph Build** — Inhalte werden gechunked, Entitäten/Relationen extrahiert, Embeddings erzeugt und nach Neo4j geschrieben.
3. **Persona Spawn** — aus Graph und Simulationseinstellungen entstehen Personas mit Rolle, Haltung, Aktivitätsmuster und optionalem Review-Gate.
4. **Simulation** — OASIS/CAMEL läuft als Subprozess. Status, Aktionen und Logs laufen über Event-Bus und SSE ins Frontend.
5. **Report** — ReportAgent verbindet Graph-Evidence, Simulationstraces, Interviews und optional Web-Kontext zu einem DACH-Report mit Provenance.
6. **Compare** — Runs, Graph-Snapshots und Diffs machen Drift, Verstärkung und Unterschiede zwischen Varianten sichtbar.

## Datenflüsse

```text
Upload
  -> File Parser
  -> Graph Build Service
  -> Neo4j + Embedding Backend
  -> Persona/Simulation Config
  -> OASIS/CAMEL Subprocess
  -> Event Bus + Artifact Store
  -> Report Agent
  -> Report API + Export
```

SSE-Streams und Downloads nutzen signed Tickets. Neue URL-bound Auth-Pfade dürfen nicht über `?token=` laufen.

## Verträge

| Vertrag | Quelle | Konsument |
|---|---|---|
| Pydantic v2 | `backend/app/contracts/` | Backend-API und Tests |
| JSON Schema | `schemas/` | Drift-Check, CI, externe Validierung |
| Zod | `frontend/src/contracts/` | Frontend-API-Grenzen |

Schema-Änderungen brauchen:

```bash
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

## Weiterführende Doku

- [docs/development.md](development.md)
- [docs/deployment-dev.md](deployment-dev.md)
- [docs/deployment-prod.md](deployment-prod.md)
- [docs/security.md](security.md)
- [docs/status.md](status.md)
- [docs/adr/](adr/)
