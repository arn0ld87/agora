<div align="center">

<img src="./media/logo.png" alt="Agora" width="220"/>

# Agora

**Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.**

Dokument hochladen, Wissensgraph extrahieren, Personas ableiten, Social-Media-Reaktionen simulieren und einen belegbaren DACH-Report erzeugen.

[![Repository](https://img.shields.io/badge/GitHub-arn0ld87%2Fagora-111?style=flat-square&logo=github)](https://github.com/arn0ld87/agora)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20or%20cloud-000?style=flat-square)](https://ollama.com/)
[![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen?style=flat-square)](./CHANGELOG.md)

[Deutsch](#deutsch) · [English](#english) · [Status](./docu/STATUS.md) · [Security](./docu/security-hardening.md)

</div>

---

> ## Status: v1.0.0 auf `main`
>
> Releasedatum: **2026-05-11** ([Release Notes](docu/2026-05-11-v1.0.0-release-notes.md)).
> Kern-Output-Vertrag-Phases stehen (P2.1/P2.2/P3.1/P3.3/P3.4/P4.2):
> Pflichtabschnitt-Validator, Persona-Mindestanzahl, Evidence-Anker-Pflicht, Low-Confidence-Marker,
> ReportV3-Persistenz mit Markdown-Renderer, Quote-Source-Marker, drei Vertrauensmodi
> (`strict`/`balanced`/`explorative`), CSV/ZIP-Export.
> Offene Sub-Slices (P3.2-Verdrahtung, P4.1 Report-Modi, P4.3 ZIP-Bundle, P4.4 E2E-Smokes) laufen unter M11.
>
> Agora ist ein **experimenteller Fork**. Graph-Build, Simulation und Report-Pipeline hängen stark an Modellqualität, JSON-Verhalten, Neo4j, Redis und OASIS-Subprozessen.
>
> **Nicht direkt ins öffentliche Internet stellen.** Agora v1 ist per [ADR-0001](docu/decisions/0001-auth-model.md) bewusst **Single-User-only**: Shared `AGORA_AUTH_TOKEN`, signed Tickets für SSE/Downloads, kein Multi-User-AuthN/AuthZ-Stack. Für Tailnet/LAN nur hinter Reverse-Proxy oder Tunnel betreiben.
>
> **Aktiv gepflegter Modellpfad:** `qwen3-coder-next:cloud` für LLMs und `qwen3-embedding:4b` mit `VECTOR_DIM=2560` für Embeddings. `nomic-embed-text` mit 768 Dimensionen bleibt als Fallback möglich.

> **Laufend:** [Design Language v4 — App-Shell-Port](docu/2026-05-11-design-v4-app-shell-epic.md) (Operator-Workbench-Dashboard, native v4-Tokens, Apple-System-Farben). Integration-Branch `feat/design-v4-epic`, Slices A–J geplant.

---

## Deutsch

### Was ist Agora?

Agora ist ein lokal-first Resonanzlabor für Texte, Pläne und Dossiers. Du lädst ein Dokument hoch, Agora baut daraus einen Knowledge Graph, erzeugt daraus differenzierte Personas und lässt diese Personas in einer OASIS-Simulation auf den Inhalt reagieren. Am Ende steht kein Bauchgefühl, sondern ein Report mit Zitaten, Confidence-Scores und Provenance-Ankern.

Typische Einsätze:

- Kommunikations- und Kampagnenentwürfe gegen Zielgruppenreaktionen prüfen
- Stakeholder-Cluster, Einwände und Polarisierung früh erkennen
- Varianten von Narrativen, Produkttexten oder Policies vergleichen
- DACH-spezifische Sprache, Timing-Profile und Report-Tonalität nutzen

### Pipeline

1. **Upload**: PDF, Markdown oder Text hochladen und Fragestellung definieren.
2. **Graph Build**: Entitäten, Beziehungen und Attribute werden extrahiert und in Neo4j geschrieben.
3. **Persona Spawn**: Agora generiert Personas mit Rolle, Haltung, Aktivitätsmuster und optionalem Review-Gate.
4. **Simulation**: OASIS läuft als Subprozess; Status, Aktionen und Logs laufen über Redis/File-IPC und SSE.
5. **Report**: ReportAgent verbindet Graph, Simulation, Interviews und optional Webtools zu einem belegbaren DACH-Report.
6. **Compare**: Graph-Diff, Branch-Compare und Runs Dashboard zeigen Drift, Verstärkung und Status über Runs hinweg.

### PDF-Export

PDF wird ausschließlich über den Browser-Print-Dialog erzeugt — Button „Als PDF drucken (Browser)" in Step 4 öffnet ein Standalone-HTML mit Print-CSS; kein server-seitiges PDF, keine Headless-Chrome-Pipeline.

<p align="center">
  <a href="./media/screenshots/graph-build.mp4">
    <img src="./media/screenshots/graph-build.gif" alt="Agora Graph-Build Demo" width="100%"/>
  </a>
  <br/>
  <sub><a href="./media/screenshots/graph-build.mp4">Graph-Build als MP4 öffnen</a></sub>
</p>

### Highlights v1.0.0

- **Output-Vertrag erzwungen**: Pflichtabschnitt-Validator + Persona-Floor (≥50) + Schema-Drift-Gate. Kein Report verlässt die Pipeline ohne Pflichtabschnitte oder mit zu wenig Personas.
- **Evidence-Härtung**: Jeder Claim außerhalb `low` braucht Evidence-Anker. Evidence-lose Claims wandern automatisch in `hypotheses[]` oder `data_gaps[]`. Low-Confidence ist im Markdown sichtbar markiert.
- **ReportV3-Persistenz + Markdown-Renderer**: Strukturierte Aggregation (Personas, Segmente, FrictionPoints, TrustSignals) aus dem `artifact_store`, deterministisches Markdown mit `simulated_quote`-Blockzitaten und Mode-Banner als Header.
- **Drei Vertrauensmodi**: `strict` (nur belegte Claims, harter Anchor-Validator), `balanced` (Default — belegte Claims + markierte Hypothesen), `explorative` (alles durch, EXPLORATIVE-Modus). Frontend-Selektor mit localStorage-Persistenz und i18n.
- **Export-Vollständigkeit**: Markdown, JSON, CSV (Personas/Segmente/Claims, RFC-4180), ZIP-Bundle (serverseitig via Python-stdlib, kein jszip), Browser-Print-PDF.
- **Live-Settings**: `GET`/`PUT /api/settings` mit Pydantic-Validierung, Secret-Redaction, `settings.changed`-Event-Bus. Services lesen via `settings_layer.get_*()` — Live-Übernahme ohne Container-Restart (`AGORA_PARALLEL_PERSONA_COUNT`, `AGORA_PERSONA_DETAIL_LEVEL`, `ONTOLOGY_MAX_TOKENS`).
- **CI-Hardening**: `step-security/harden-runner` (audit-mode) in 9 Workflows, `aquasecurity/trivy-action` für Container-Scans, `ossf/scorecard-action` für Supply-Chain-Score.
- **Compare- und Diff-Stack** (aus v0.9.x übernommen): Graph-Diff, Simulation-Compare, Runs Dashboard.
- **Production-Hardening** (aus v0.9.x übernommen): Reverse-Proxy-Sidecar, gevent, Bundle-Token-Gate, signed Tickets, Prod-Smoke auf `main`/Tags/`workflow_dispatch`.
- **Security-Watchlist**: CVE-Monitor wöchentlich, Hardstop 2026-07-30, Dependency Risk Register mit Eskalationspfad.

### Architektur auf einen Blick

```text
Vue 3 + Pinia + Zod + Vite
  └─ Frontend-Wizard, Runs Dashboard, Graph/Compare UI, Report UI

Flask API + Pydantic v2
  ├─ contracts/          Single Source of Truth für API-Verträge
  ├─ api/                Auth, Graph, Simulation, Report, Runs, Status
  ├─ services/           Graph Build, Personas, Simulation, Reports, Metrics
  ├─ storage/            Neo4j, Embeddings, NER, Search
  └─ scripts/            OASIS-Subprozess-Runner

Runtime
  ├─ Neo4j 5.18+         Knowledge Graph
  ├─ Redis               Pub/Sub-IPC im Compose-Default
  ├─ Ollama/OpenAI-API   LLM- und Embedding-Endpunkte
  └─ OASIS/CAMEL         Multi-Agent-Simulation
```

### Engineering-Status

Verbindliche Testzahlen, Coverage und Milestone-Status stehen in [`docu/STATUS.md`](docu/STATUS.md). Diese README kopiert keine Test-Counts inline.

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel + JSON-Schema-Dump | grün |
| 1 | Backend-Hardening, Quoten, Evidence-Dedup, Confidence | grün |
| 2 | DACH-Voice + Glossar v1 | grün |
| 3 | Reader-Honesty: Quotes, Provenance, Section-Dedup | grün |
| 4 | Frontend strict-Zod, Diff/Confidence-UI, Quoten | grün |
| 5 | Eval/Baseline-Suite + Snapshots | grün |
| 6 | Frontend-TypeScript-Migration | grün |
| 7 | Graph / Runs / Compare | weitgehend grün |
| 8 | Persona Review + Persona-Entity-Kontext | teilweise |
| 9 | Production Deployment | grün mit bewusst pausiertem PR-Smoke |
| 10 | Security Watchlist | grün |

#### Laufende Härtung (M11)

- **Coverage-Gate-Anhebung** (M11.2/M11.3): Backend 55 % → 85 % (monatlich +2 Punkte), Frontend 26 % → 80 % (mit Playwright E2E, M11.4+). Reports als Artifacts in CI.
- **Playwright-Smokes** (M11.4): Drei stabile E2E-Smokes — Health/Login, Upload+Graph, Minimalreport statt 90-Test-Pyramide.
- **Komplexitäts-Gate** (M11.5): `radon` Backend, `ESLint`/`size-limit` Frontend.
- **API-Envelope** (M11.6): Error-/Success-Envelopes vollständig durchziehen.
- **gevent ↔ OASIS-Subprozess-Smoke:** Bei OASIS-Pfad-Änderungen via `scripts/verify-deploy.sh` verifizieren.

Siehe [`docu/STATUS.md`](docu/STATUS.md) für Coverage-Roadmap und aktuelle Schwellen.

### Schnellstart

Vollständige Guides:
[`docu/deployment-dev.md`](./docu/deployment-dev.md) · [`docu/deployment-prod-like.md`](./docu/deployment-prod-like.md)

#### Voraussetzungen

- Node.js 18+
- Python 3.11+
- `uv`
- Neo4j 5.18+
- Ollama lokal oder ein OpenAI-kompatibler Endpoint

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Modelle auf dem Host vorbereiten (aktiv gepflegt)
ollama pull qwen3-coder-next:cloud
ollama pull qwen3-embedding:4b

# Dev-Stack: Agora + Neo4j + Redis
docker compose up -d --build
```

Endpoints:

| Dienst | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend Health | <http://localhost:5001/health> |
| Neo4j Browser | <http://localhost:7474> |

#### Lokal ohne Docker

```bash
npm run setup:all
npm run dev
```

#### Rebuild nach größeren Änderungen

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Named Volumes für Neo4j und Redis bleiben dabei erhalten.

### Wichtige Konfiguration

```env
# LLM / Ollama oder OpenAI-kompatibler Endpoint (aktiv gepflegt: qwen3-coder-next)
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen3-coder-next:cloud

# Embeddings (aktiv gepflegt: qwen3-embedding:4b)
EMBEDDING_MODEL=qwen3-embedding:4b
EMBEDDING_BASE_URL=http://localhost:11434
VECTOR_DIM=2560

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<setzen>

# Sprache / Region
AGENT_LANGUAGE=de
REPORT_LANGUAGE=German
TIME_PROFILE=dach_default

# Optional
PERSONA_REVIEW_ENABLED=false
ENABLE_AGENT_TOOLS=false
ENABLE_WEB_TOOLS=false
```

Embedding-Modell und `VECTOR_DIM` müssen zusammenpassen:

| Modell | VECTOR_DIM |
|---|---:|
| `nomic-embed-text` | 768 |
| `embeddinggemma:300m` | 768 |
| `qwen3-embedding:4b` | 2560 |
| `qwen3-embedding:8b` | 4096 |

**Fallback (älter):** Statt `qwen3-coder-next:cloud` kannst du auch `qwen2.5:32b` nutzen; die Token-Limits sind reduziert.

### Sicherheit

Agora reduziert die Angriffsfläche bewusst, ersetzt aber keinen Multi-User-Sicherheitsstack.

- `AGORA_AUTH_TOKEN` schützt `/api/*`.
- `?token=` ist im Non-Debug-Modus blockiert; SSE/Downloads nutzen signed Tickets.
- Rate-Limits schützen Ticket-, Upload-, Simulation-LLM- und Report-Trigger-Endpunkte.
- `ProxyFix` ist opt-in und wird im Repo-nginx-Sidecar mit genau einem trusted Proxy konfiguriert.
- Secrets werden nicht in Simulation-Artefakte serialisiert.
- Non-Debug-Start verlangt echte Werte für `SECRET_KEY`, `NEO4J_PASSWORD` und `AGORA_AUTH_TOKEN`.

Secret erzeugen:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Details:
[`docu/security-hardening.md`](./docu/security-hardening.md) ·
[`docu/auth.md`](./docu/auth.md) ·
[`docu/decisions/0001-auth-model.md`](./docu/decisions/0001-auth-model.md) ·
[`docu/dependency-risk-register.md`](./docu/dependency-risk-register.md)

### Entwicklung

```bash
npm run setup:all
npm run dev
npm run check

cd backend && uv run pytest
cd backend && uv run ruff check app/ tests/
cd backend && uv run python -m app.contracts.dump_schemas

cd frontend && npm run check
```

Wichtige Doku:

- [`docu/STATUS.md`](./docu/STATUS.md) — Single Source of Truth für Status, Tests, Coverage
- [`PLAN.md`](./PLAN.md) — operativer Findings- und Maßnahmenplan
- [`AGENTS.md`](./AGENTS.md) / [`CLAUDE.md`](./CLAUDE.md) — Agent-Runbooks
- [`docu/target-architecture.md`](./docu/target-architecture.md) — Zielarchitektur
- [`docu/glossary-wording.md`](./docu/glossary-wording.md) — DACH-Wording-Glossar
- [`CHANGELOG.md`](./CHANGELOG.md) — Release-Notizen

### Herkunft und Lizenz

Agora ist ein Fork / Derivat von [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), basierend auf [666ghj/MiroFish](https://github.com/666ghj/MiroFish). Die Simulations-Engine nutzt [OASIS](https://github.com/camel-ai/oasis) von CAMEL-AI.

Lizenz: AGPL-3.0, siehe [LICENSE](./LICENSE).

---

## English

### What is Agora?

Agora is a local-first multi-agent simulator for DACH audience response. Upload a document, extract a knowledge graph, derive personas, run an OASIS simulation, and generate a report with quotes, confidence scores, and provenance anchors.

It is built for careful local experimentation: Neo4j for graph memory, Flask/Pydantic for contracts, Vue/Pinia/Zod for the UI, Redis/File IPC for simulation state, and Ollama or OpenAI-compatible endpoints for LLMs.

### Current status

`main` is at **v1.0.0** (released 2026-05-11, see [Release Notes](docu/2026-05-11-v1.0.0-release-notes.md)). Core output-contract phases complete (P2.1/P2.2/P3.1/P3.3/P3.4/P4.2): required-sections validator, persona-minimum floor, evidence-anchor requirement, low-confidence markers, ReportV3 persistence with Markdown renderer, quote-source markers, three trust modes (`strict`/`balanced`/`explorative`), CSV export. Open sub-slices (P3.2 wiring, P4.1 report modes, P4.3 ZIP bundle, P4.4 E2E smokes) in progress under M11. Production hardening (reverse-proxy sidecar, gevent, signed tickets), CVE monitoring with the 2026-07-30 hardstop, and coverage gates documented in [`docu/STATUS.md`](docu/STATUS.md).

Agora v1 is **single-user-only** by architecture decision. Do not expose it directly to the public internet.

### Core workflow

1. Upload a PDF, Markdown file, or plain text.
2. Build a Neo4j knowledge graph from entities, relations, and attributes.
3. Generate personas from the graph.
4. Run OASIS as a subprocess and stream simulation state.
5. Generate a report from graph evidence, simulation traces, interviews, and optional web context.
6. Compare runs through graph diff, branch compare, and the runs dashboard.

### PDF export

PDF is generated exclusively through the browser print dialog — the "Print as PDF (browser)" button in Step 4 opens a standalone HTML with print CSS; no server-side PDF, no headless-Chrome pipeline.

### Quick start

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

ollama pull qwen3-coder-next:cloud
ollama pull qwen3-embedding:4b

docker compose up -d --build
```

Open:

- Frontend: <http://localhost:5173>
- Backend health: <http://localhost:5001/health>
- Neo4j Browser: <http://localhost:7474>

Local development:

```bash
npm run setup:all
npm run dev
npm run check
```

### License and attribution

Agora is an AGPL-3.0 fork/derivative of [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), based on [666ghj/MiroFish](https://github.com/666ghj/MiroFish). The simulation engine uses [OASIS](https://github.com/camel-ai/oasis) by CAMEL-AI.
