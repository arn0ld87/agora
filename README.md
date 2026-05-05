<div align="center">

<img src="./media/logo.png" alt="Agora" width="240"/>

# Agora

**Wie reagieren Stakeholder auf dein Dokument? — Frag 132 Personas, bevor du es veröffentlichst.**

Multi-Agenten-Resonanz-Simulator mit Knowledge-Graph-Backbone. Hybrid einsetzbar: lokal mit Ollama oder via Cloud-Endpoints (Ollama Cloud, OpenAI-kompatibel). Deutsche UI als Default.

Fork von [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), basierend auf [MiroFish](https://github.com/666ghj/MiroFish).

[![Repository](https://img.shields.io/badge/GitHub-arn0ld87%2Fagora-111?style=flat-square&logo=github)](https://github.com/arn0ld87/agora)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20or%20cloud-000?style=flat-square)](https://ollama.com/)
[![Version](https://img.shields.io/badge/Version-0.9.1--dev-orange?style=flat-square)](./CHANGELOG.md)

[Deutsch](#deutsch) · [English](#english)

</div>

---

> ## Status: v0.9.1-dev (post-tag Iteration auf `main`)
>
> Tag-Stand: `v0.9.0` vom 2026-05-01 ([Release Notes](docu/2026-05-01-v0.9.0-release-notes.md)).
> `main` ist seither in aktiver Layer-6-bis-8-Iteration — Frontend TypeScript komplett, Layer 7 (Compare- und Diff-Stack, Runs Dashboard) ausgeliefert, Layer 8 (Persona-Entity-Kontext) angefangen. Aktuelle Test-Counts und Coverage in [`docu/STATUS.md`](docu/STATUS.md).
>
> Agora ist ein **experimenteller Fork**. Graph-Build, Simulation und Report-Pipeline können bei langsamer Cloud, JSON-Mode-Aussetzern oder Modellwechseln Fehler produzieren.
>
> **Nicht öffentlich erreichbar machen.** Auth-Zielbild ist per Architektur-Entscheidung **Single-User-only** ([ADR-0001](docu/decisions/0001-auth-model.md)): ein Shared `AGORA_AUTH_TOKEN`-Bearer plus signed Tickets für SSE/Downloads. Kein Multi-User-Pfad in v1. CORS auf Localhost gelockt, Backend bindet defaultmäßig auf `127.0.0.1`. Für Tailnet/LAN: Reverse-Proxy ([`deploy/nginx/`](deploy/nginx/)) und Tailscale/Cloudflare Tunnel — nicht direkt im Internet exponieren.
>
> **Aktuell hauptsächlich getestet mit:**
>
> - LLM: `qwen3-coder-next:cloud` (Ollama Cloud)
> - Embedding: `qwen3-embedding:4b` (2560-dim, `VECTOR_DIM=2560` nötig)
>
> Der frühere Default `nomic-embed-text` (768-dim) funktioniert weiterhin, ist aber nicht mehr der aktiv gepflegte Pfad.
>
> **Docker:** `docker pull alexle135/agora-agora:latest` · [GHCR](https://github.com/arn0ld87/agora/pkgs/container/agora)

---

## Deutsch

### Was ist Agora?

Du lädst ein Dokument hoch — einen Pressetext, ein Whitepaper, einen Vertragsentwurf. Agora extrahiert daraus einen Wissensgraphen, erzeugt aus den Entitäten **hunderte Agenten-Personas** mit eigenen Rollen, Haltungen und Aktivitätsmustern, lässt sie auf Social-Media-artigen Plattformen über deinen Inhalt diskutieren, und liefert dir am Ende einen Report mit Originalzitaten, Confidence-Scores und Provenance-Ankern.

Kurz: **Resonanz-Simulation für Texte, bevor sie raus gehen.**

### Was ist neu seit dem letzten README-Update (2026-05-04)

Die wichtigsten Veränderungen seit der letzten README-Iteration, sortiert nach User-sichtbarem Impact:

- **🆚 Compare- und Diff-Stack ausgeliefert** — Graph- und Branch-Vergleiche jetzt mit API + UI
  - `GET /api/graph/<id>/diff` (#74) — Snapshot-Diff zwischen zwei Runden mit Pydantic-Contract
  - `GET /api/simulation/<id>/compare` (#66) — Kernmetriken zweier Runs nebeneinander
  - `GraphDiffPanel.vue` (#76) und `BranchComparePanel.vue` (#67) als Vergleichs-UIs
- **📊 Runs Dashboard mit Live-Polling** (#63) — neue View `/runs` mit Status-Pills (Aktiv / Abgeschlossen / Fehlerhaft), 5-s-Tab-aware-Polling, Click-through zu Detail-Views (`/runs/:id`)
- **🧬 Persona-Entity-Kontext-API** (#69, Backend-Hälfte) — `GET /api/simulation/<sim>/profiles/<username>/entity-context` zeigt, welche Knowledge-Graph-Entity in eine Persona eingeflossen ist. Frontend-Diff-UI folgt im nächsten Slice.
- **🛡️ CI-Hardening abgeschlossen** — Evidence-Quality-Gate hart geschaltet (kein `--soft` mehr), Backend-Coverage-Gate auf 53 %, Frontend-Coverage-Gate auf 24 %, Prod-Stack-Smoke + CVE-Monitor wöchentlich
- **⚡ Performance-Iteration** (#217) — Persona-Generation parallelisiert (`parallel_count` Default 5/3 → 10), neuer `AGORA_PERSONA_DETAIL_LEVEL` für Output-Größen-Steuerung, `@measure_llm_latency`-Decorator zur Latenz-Beobachtung
- **🩹 Stabilität** — Vector-Index droppt sich bei Dimension-Mismatch automatisch (#263), Embedding-Crash-Loop in CI gefixt (#276), Neo4j Startup-Retry bei Race-Condition, `/api/logs/stream` auf signed-tickets migriert (F2.2)
- **🔐 Auth-Zielbild für v1.0 entschieden** — [ADR-0001](docu/decisions/0001-auth-model.md): bewusst Single-User-only mit Shared-Token + Signed-Tickets, kein Multi-User-Pfad in v1
- **🧹 Refactoring** — `report_agent.py` 2400-LOC-Monolith zu Package-Split (#202), Frontend-TypeScript-Migration abgeschlossen (#73), letzte 14 `.js`-Dateien portiert

Vollständige Liste: [`CHANGELOG.md`](./CHANGELOG.md) und [`docu/STATUS.md`](./docu/STATUS.md).

### Workflow

So sieht eine Pipeline-Iteration aus:

1. **Upload & Modellwahl** — Dokument hochladen, Fragestellung formulieren, LLM-Modell und Agentensprache wählen.

2. **Graph aufbauen** — Agora chunked das Dokument, ruft das LLM für Named-Entity-Recognition + Relation-Extraction auf und schreibt den Graphen nach Neo4j. Du siehst den Graphen live mit Knoten, Kanten, Entity-Type-Legende und kannst ihn als GraphML / SVG / PNG / PDF exportieren.

   <p align="center">
   <a href="./media/screenshots/graph-build.mp4">
   <img src="./media/screenshots/graph-build.gif" alt="Live-Graph-Build mit 133 Knoten, 188 Kanten und 12 Entitätstypen" width="100%"/>
   </a>
   <br>
   <sub><a href="./media/screenshots/graph-build.mp4">▶ MP4 in voller Qualität (747 KB)</a></sub>
   </p>

3. **Personas erzeugen** — aus dem Graphen werden hunderte Agenten-Personas generiert. Jede mit Biografie, Meinung, Reaktionsgeschwindigkeit, Einfluss-Profil. Persona-Quote pro Segment optional erzwingbar; Limit für Agentenanzahl optional.

   <p align="center">
   <img src="./media/screenshots/persona-step.png" alt="Persona-Generation-Schritt mit LLM-Modellwahl, Agentensprache und Live-Counter" width="100%"/>
   </p>

4. **Simulation** — OASIS läuft als Subprozess. Aktionen erscheinen live im Console-Log, Pause/Resume nach Rundenende möglich. Laufdauer in Tagen + optionales Rundenlimit.

5. **Report** — der ReportAgent durchsucht Graph und Simulation, kann Agenten interviewen, optional Webtools nutzen. Report-Modell ist beim Generieren wechselbar. Jede Section trägt einen Confidence-Score plus klickbare Source-Anchors.

6. **Compare & Drift** — zwei Runs nebeneinander analysieren: Graph-Diff (welche Kanten sind dazugekommen, welche verstärkt?), Branch-Vergleich (Persona-Drift, Polarisations-Shift), Run-Dashboard mit Live-Status.

### Demo-Teaser

<div align="center">
<a href="./static/media/agora-teaser.mp4">
<img src="./static/media/agora-teaser-preview.gif" alt="Agora Demo-Teaser" width="100%"/>
</a>
<br>
<a href="./static/media/agora-teaser.mp4">Teaser als MP4 öffnen</a>
</div>

### Kernfunktionen

- **GraphRAG-Ingest**: PDF, Markdown oder Text hochladen; Entitäten und Beziehungen landen in Neo4j.
- **Flexible Ontologie-Generierung**: Entitätstypen sind nicht hart gecappt; Defaults 8–16 Typen plus Pflicht-Fallbacks `Person` und `Organization`.
- **Modellauswahl im Workflow**: Modell und Agentensprache pro Run wählbar, plus `.env`-Default. Eingefroren in `simulation_config.json` pro Simulation.
- **Persona Review**: Generierte Personas vor Simulationsstart prüfbar, editierbar, freigebbar. Quality-Heuristiken (Dubletten, fehlende Kernfelder, Rollen-Diversität). Mit `PERSONA_REVIEW_ENABLED=true` blockt der Simulationsstart bis alle Personas approved sind.
- **Run-Steuerung**: Laufdauer in Tagen + optional Rundenlimit, Start/Stop, Pause/Resume nach Rundenende, rohes OASIS-Console-Log.
- **ReportAgent**: Graph-Tools, Interviews, Panorama-Suche; Report-Modell beim Generieren/Regenerieren wechselbar; optional Tavily-Webtools.
- **Compare-Stack**: Graph-Diff zwischen Runden (`/api/graph/<id>/diff`), Branch-Compare (`/api/simulation/<id>/compare`), UIs `GraphDiffPanel` + `BranchComparePanel`.
- **Runs Dashboard**: Zentrale `/runs`-View mit Live-Polling (5 s, Tab-aware-Pause), Status-Pills, Click-through zu Detail.
- **Export-Center**: JSON + Markdown für Reports, CSV für Polarisationsmetriken, GraphML für Graphen, SVG / PNG / PDF für Graph-Ansicht.
- **Experimenteller Agent-Tool-Use**: Simulationsagenten können den Wissensgraphen abfragen (`ENABLE_AGENT_TOOLS=true`), default aus.
- **Secret-Guardrail**: Neo4j-Passwörter werden nicht in persistierte Simulation-Artefakte serialisiert.

### Engineering-Stand (Layer 0–10)

Test-Zahlen und Coverage werden in [`docu/STATUS.md`](docu/STATUS.md) gepflegt — diese README kopiert keine Zahlen mehr inline.

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts (`backend/app/contracts/`) + Zod-Spiegel + JSON-Schema-Dump | grün |
| 1 | Backend-Hardening: `chat_json` strict-Mode, `PersonaQuotaPlan`, Anti-Dekoration, Confidence-Cap | grün |
| 2 | DACH-Voice + Wording-Glossar v1, Voice-Lint im CI-Hartmacher | grün |
| 3 | Reader-Honesty: Original-Quotes, Provenance-Anker, Time-Series-Sampling, Section-Dedup | grün |
| 4 | Frontend strict-Zod, Diff/Confidence-UI, Persona-Quota-Editor | grün |
| 5 | Eval-Suite mit Snapshot-Pin, 5 Metriken (`evidence_coverage`, `claim_support_ratio`, …) | grün |
| 6 | Frontend-TypeScript-Migration (#71/#72/#73) — alle `.js` portiert | grün |
| 7 | Graph-Diff API/UI (#74/#76), Compare API/UI (#66/#67), Runs Dashboard (#63) | grün |
| 8 | Persona-Review-UX: Persona-Entity-Context API (#69 Backend), UI in Arbeit | teilweise |
| 9 | Production Hardening: Reverse-Proxy, gevent, Bundle-Token-Gate, signed-tickets, Prod-Stack-Smoke in CI | grün |
| 10 | Security Watchlist: CVE-Monitor, Hardstop 2026-07-30, Risk-Register | grün |

### Was wurde gegenüber MiroFish geändert?

| Bereich | Upstream MiroFish / MiroFish-Offline | Agora |
|---|---|---|
| Sprache / UI | Chinesischer Ursprung, später englische Migration | Deutsche UI als Default, Englisch als Fallback |
| Graph Memory | Zep / Graphiti-Ansatz im Ursprung | Eigene `GraphStorage`-Abstraktion mit Neo4j 5.18+ |
| LLMs | DashScope / OpenAI-orientiert | Ollama lokal oder beliebiger OpenAI-kompatibler Endpoint |
| Modelle | Primär per `.env` | Modell-Auswahl im Workflow + `.env`-Fallback |
| Simulation | Feste KI-Personas | Persona-Review-Workflow, Quote-Validation, Sprache/Modell pro Vorbereitung |
| Report | ReportAgent mit Graph-Tools | Report-Modell wechselbar, Confidence-Scores, Provenance-Anker, optional Webtools |
| Compare | Nicht im Upstream | Graph-Diff, Branch-Compare, Runs Dashboard |
| Region | China-Kontext | DACH / Europe-Berlin Timing-Profil + Wording-Glossar v1 |

### Schnellstart

> Vollständige Anleitungen mit Volume-Layout, Reverse-Proxy-Setup und Härtungs-Checkliste:
> [`docu/deployment-dev.md`](./docu/deployment-dev.md) · [`docu/deployment-prod-like.md`](./docu/deployment-prod-like.md).

#### Voraussetzungen

- Node.js 18+
- Python 3.11+
- `uv`
- Neo4j 5.18+
- Ollama (lokal) oder Ollama-Cloud-Account / OpenAI-kompatibler Endpoint

```bash
# Default-LLM (lokal) oder Cloud-Variante
ollama pull qwen2.5:32b
# Aktuell genutztes Embedding (2560 dim, erfordert VECTOR_DIM=2560)
ollama pull qwen3-embedding:4b
# Fallback (768 dim), falls du kein Qwen3-Embedding willst:
# ollama pull nomic-embed-text
```

#### Option A: Docker Compose (Dev-Default)

Compose startet Agora, Neo4j und Redis. Ollama läuft auf dem Host und wird aus dem Container über `host.docker.internal` erreicht. Veröffentlichte Ports binden auf `127.0.0.1`.

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# .env.example defaultet FLASK_DEBUG=false (secure-by-default).
#
# Dev: FLASK_DEBUG=true setzen, SECRET_KEY und NEO4J_PASSWORD dürfen
#      Platzhalter bleiben (Config.validate() warnt, blockt aber nicht).
#
# Hardened: FLASK_DEBUG=false lassen, echte Werte für SECRET_KEY,
#   NEO4J_PASSWORD und AGORA_AUTH_TOKEN erzeugen
#   (Einzeiler in der Sicherheits-Sektion unten).

docker compose up -d --build
```

**Endpoints:**

| Endpoint | URL | Bind |
|---|---|---|
| Frontend (Vite) | <http://localhost:5173> | `127.0.0.1` |
| Backend (Flask) | <http://localhost:5001/health> | `127.0.0.1` |
| Neo4j Browser | <http://localhost:7474> | `127.0.0.1` |
| Neo4j Bolt | `bolt://localhost:7687` | `127.0.0.1` |

Wer aus einem anderen Netzsegment (LAN, Tailscale) zugreifen will, setzt einen Reverse-Proxy davor — direkter Bind auf `0.0.0.0` ist im Default bewusst aus.

#### Nach größeren Umbauten den Container neu bauen

Wenn du Backend-/Frontend-Layer geändert hast (Dependencies, Pydantic-Schemas, Frontend-Bundle), reicht `docker compose up -d --build` manchmal nicht — Layer-Cache hält veraltete Stände. Dann komplett neu bauen, **ohne Daten-Volumes zu verlieren**:

```bash
cd ~/agora

# Stack stoppen, Daten behalten
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  down --remove-orphans

# Agora-Prod-Image komplett neu bauen
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  build --no-cache agora

# Stack neu starten
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --force-recreate --remove-orphans

# Status prüfen
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps
```

Named Volumes (Neo4j-Daten, Redis-Persistenz) bleiben erhalten. Nur das `agora`-Image wird ersetzt.

Weitere Dev-Kommandos:

```bash
# Container mit Dev-Override neu erstellen
docker compose up -d --force-recreate agora

# Wenn Docker-/Dependency-Layer geändert wurden
docker compose build agora && docker compose up -d --force-recreate --no-deps agora

# Wenn named volumes für Dependencies einmal resettet werden sollen
docker compose down -v && docker compose up -d
```

#### Option B: Lokal ohne Docker

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

npm run setup:all
npm run dev
```

### Wichtige Konfiguration

Alle Laufzeitwerte kommen aus `.env`.

```env
# LLM / Ollama oder OpenAI-kompatibler Endpoint
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agora

# Embeddings — aktuell getestet mit Qwen3-Embedding (2560 dim)
EMBEDDING_MODEL=qwen3-embedding:4b
EMBEDDING_BASE_URL=http://localhost:11434
VECTOR_DIM=2560
# Fallback (768 dim): EMBEDDING_MODEL=nomic-embed-text + VECTOR_DIM=768

# GraphRAG Performance
GRAPH_CHUNK_SIZE=1500
GRAPH_CHUNK_OVERLAP=150
GRAPH_PARALLEL_CHUNKS=4

# Persona-Generation Performance (#217 Stufe 2)
AGORA_PERSONA_DETAIL_LEVEL=standard   # minimal | standard | rich
# parallel_count default: 10 (vorher 5/3)

# Sprache / Region
AGENT_LANGUAGE=de
REPORT_LANGUAGE=German
TIME_PROFILE=dach_default

# Experimentell: Tool-Use innerhalb der Simulation
ENABLE_AGENT_TOOLS=false
MAX_TOOL_CALLS_PER_ACTION=2

# Optional: Live-Webtools im ReportAgent
# TAVILY_API_KEY=...
# ENABLE_WEB_TOOLS=true
```

### Modellwahl und Modellwechsel

- `LLM_MODEL_NAME` ist nur der Default.
- Die UI fragt `/api/simulation/available-models` ab und zeigt kuratierte Presets plus lokal verfügbare Ollama-Modelle.
- Modellwahl auf der Startseite und in Step 2 steuert Persona- und Config-Generierung.
- Eine vorbereitete Simulation nutzt das Modell aus ihrer `simulation_config.json`.
- Der ReportAgent akzeptiert ein Modell-Override beim Generieren, Regenerieren und Chatten.
- Wenn du eine bereits vorbereitete Simulation mit einem anderen Modell ausführen willst, bereite sie neu vor.

### Sicherheit

> **Warnung:** Agora ist explizit für `localhost` oder ein vertrauenswürdiges Netz (Tailscale, Wireguard, internes LAN) gedacht. Der `AGORA_AUTH_TOKEN`-Guard und die CORS-Whitelist reduzieren die Angriffsfläche, ersetzen aber keine echte Mehrbenutzer-Auth. Nicht direkt ins Internet hängen.

- Keine echten Secrets committen, `.env` bleibt lokal.
- `.env.example` enthält nur Placeholder (`change-me*`, `agora`, `neo4j`, `password`). `Config.validate()` lehnt diese im Nicht-Debug-Betrieb hart ab.
- Echten `SECRET_KEY` und `AGORA_AUTH_TOKEN` mit einem Einzeiler erzeugen:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- Neo4j-Passwörter werden nicht in `simulation_config.json` oder andere persistierte Simulation-Artefakte geschrieben.
- `backend/uploads/` ist nicht versioniert.
- Details: [`docu/security-hardening.md`](./docu/security-hardening.md), [`docu/decisions/0001-auth-model.md`](./docu/decisions/0001-auth-model.md), [`docu/dependency-risk-register.md`](./docu/dependency-risk-register.md).

### Architektur

```text
Flask API (47+ Routen, modular zerlegt)
  ├─ api/graph.py
  ├─ api/report.py
  ├─ api/runs.py                      ← Runs Dashboard (#63)
  ├─ api/status.py
  ├─ api/simulation_*.py              ← lifecycle, prepare, profiles, run, …
  └─ api/simulation_metrics.py        ← Polarisation, Bridge-Agents
        │
        ▼
Service Layer (AgoraContainer DI)
  ├─ GraphBuilderService / TemporalGraphService
  ├─ SimulationManager / SimulationRunner
  ├─ OasisProfileGenerator
  ├─ NetworkAnalyticsService / OntologyMutationService
  ├─ PersonaEntityContextService      ← neu (#69)
  ├─ ReportAgent (Package, post-#202) / GraphToolsService / WebTools
  └─ EventBus (Redis | File | InMemory)
        │
        ▼
GraphStorage Interface
  └─ Neo4jStorage (Read/Write/Search Mixins)
       ├─ EmbeddingService
       ├─ NERExtractor
       └─ SearchService
```

OASIS-Simulationen laufen als separate Subprozesse unter `backend/scripts/`. IPC, Pause/Resume und Run-State laufen über den `SimulationEventBus` (Redis Pub/Sub im Compose-Default, File-Polling als Fallback). Frontend bekommt Live-Updates per SSE (`/api/simulation/<id>/stream`) und Polling-Composable (`usePolling`, Tab-aware-Pause).

### Entwicklung

```bash
npm run setup:all
npm run dev
npm run check         # lint + tests + build (alles)
cd backend && uv run pytest
cd backend && uv run python -m compileall app scripts
cd backend && uv run python -m app.contracts.dump_schemas   # Schemas regenerieren
```

Doku-Index (Auswahl):

- Deployment: [`docu/deployment-dev.md`](./docu/deployment-dev.md) · [`docu/deployment-prod-like.md`](./docu/deployment-prod-like.md)
- Operations: [`docu/operations.md`](./docu/operations.md) · [`docu/backup-restore.md`](./docu/backup-restore.md)
- Release-Process: [`docu/release-process.md`](./docu/release-process.md)
- Auth & Security: [`docu/auth.md`](./docu/auth.md) · [`docu/security-hardening.md`](./docu/security-hardening.md) · [`docu/decisions/0001-auth-model.md`](./docu/decisions/0001-auth-model.md) · [`docu/dependency-risk-register.md`](./docu/dependency-risk-register.md)
- API-Verträge: [`docu/api-contracts.md`](./docu/api-contracts.md)
- Architektur: [`docu/target-architecture.md`](./docu/target-architecture.md)
- Status / Tests / Coverage: [`docu/STATUS.md`](./docu/STATUS.md)
- Wording-Glossar v1: [`docu/glossary-wording.md`](./docu/glossary-wording.md)

### Herkunft und Lizenz

Agora ist ein Fork / Derivat von:

- [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline)
- Upstream: [666ghj/MiroFish](https://github.com/666ghj/MiroFish)

Die Simulations-Engine nutzt [OASIS](https://github.com/camel-ai/oasis) von CAMEL-AI.

Lizenz: AGPL-3.0, siehe [LICENSE](./LICENSE).

---

## English

> **Status: v0.9.1-dev (post-tag iteration on `main`).**
> Tag is `v0.9.0` from 2026-05-01 ([release notes](docu/2026-05-01-v0.9.0-release-notes.md)). `main` has been in active layer-6-to-8 iteration since: full TypeScript frontend migration, Layer 7 (compare- and diff-stack, runs dashboard) shipped, Layer 8 (persona-entity-context) started.
> Agora is an active experimental fork. Graph build, simulation, and report pipeline can fail when Ollama is slow, JSON mode misbehaves, or models are switched mid-run. Not production-ready.
> **Single-User-only by architecture decision** ([ADR-0001](docu/decisions/0001-auth-model.md)) — shared `AGORA_AUTH_TOKEN` plus signed tickets, no multi-user path in v1. CORS localhost-locked, backend binds to `127.0.0.1` by default.
> Currently exercised with **LLM `qwen3-coder-next:cloud`** and **embedding `qwen3-embedding:4b` (2560 dim, requires `VECTOR_DIM=2560`)**.
>
> **Docker:** `docker pull alexle135/agora-agora:latest` · [GHCR](https://github.com/arn0ld87/agora/pkgs/container/agora)

### What is Agora?

Upload a document. Agora extracts a knowledge graph from it, generates **hundreds of agent personas** with their own roles, opinions, and activity profiles, lets them discuss your content on social-media-like platforms, and produces a structured report with verbatim quotes, confidence scores, and provenance anchors.

In short: **resonance simulation for text, before it ships.**

### What's new since the last README update (2026-05-04)

- **🆚 Compare- and diff-stack shipped** — `GET /api/graph/<id>/diff` (#74), `GET /api/simulation/<id>/compare` (#66), `GraphDiffPanel.vue` (#76), `BranchComparePanel.vue` (#67)
- **📊 Runs Dashboard with live polling** (#63) — new `/runs` view with status pills (active / done / failed), 5 s tab-aware polling, click-through to detail (`/runs/:id`)
- **🧬 Persona-entity-context API** (#69 backend) — `GET /api/simulation/<sim>/profiles/<username>/entity-context` shows which knowledge-graph entity fed into a persona. Frontend diff UI follows.
- **🛡️ CI hardening** — evidence-quality gate hard, backend coverage gate at 53 %, frontend coverage gate at 24 %, prod-stack-smoke and CVE-monitor on schedule
- **⚡ Performance** (#217) — persona generation parallelized (`parallel_count` 5/3 → 10), `AGORA_PERSONA_DETAIL_LEVEL`, `@measure_llm_latency` decorator
- **🩹 Stability** — vector-index drops on dim mismatch (#263), embedding-crash-loop fix (#276), Neo4j startup retry, `/api/logs/stream` on signed tickets (F2.2)
- **🔐 Auth target for v1.0** — [ADR-0001](docu/decisions/0001-auth-model.md): single-user-only, shared token + signed tickets, no multi-user path in v1
- **🧹 Refactor** — `report_agent.py` 2400-LOC monolith → package split (#202), full TypeScript migration finished (#73)

Full list: [`CHANGELOG.md`](./CHANGELOG.md), [`docu/STATUS.md`](./docu/STATUS.md).

### Workflow

1. **Upload & model selection** — drop a document, formulate the question, pick LLM and agent language.
2. **Graph build** — Agora chunks the document, calls the LLM for NER + relation extraction, writes to Neo4j. Live graph view with cluster legend; export as GraphML / SVG / PNG / PDF. ([demo clip](./media/screenshots/graph-build.mp4))
3. **Persona generation** — hundreds of agent personas derived from the graph, each with biography, stance, reaction speed, influence profile.
4. **Simulation** — OASIS runs as a subprocess. Live action stream, console log, pause/resume after a round.
5. **Report** — ReportAgent searches graph + simulation, can interview agents, optional web tools. Confidence per section, clickable source anchors.
6. **Compare & drift** — graph diff between rounds, branch comparison (persona drift, polarization shift), live runs dashboard.

### Engineering status (Layer 0–10)

Test counts and coverage live in [`docu/STATUS.md`](docu/STATUS.md) — this README no longer copies numbers inline.

| Layer | What | Status |
|---|---|---|
| 0 | Pydantic contracts + Zod mirror + JSON schema dump | green |
| 1 | Backend hardening: strict json_schema, persona quotas, anti-decoration, confidence cap | green |
| 2 | DACH voice + wording glossary v1, voice-lint as hard CI gate | green |
| 3 | Reader honesty: verbatim quotes, provenance anchors, time-series sampling, section dedup | green |
| 4 | Frontend strict-zod, diff/confidence UI, persona quota editor | green |
| 5 | Eval suite with snapshot pin, 5 metrics | green |
| 6 | Frontend TypeScript migration | green |
| 7 | Graph-diff API/UI, compare API/UI, runs dashboard | green |
| 8 | Persona-review UX: persona-entity-context API (#69 backend), UI in progress | partial |
| 9 | Production hardening: reverse proxy, gevent, bundle-token gate, signed tickets, prod-stack smoke | green |
| 10 | Security watchlist: CVE monitor, hardstop 2026-07-30, risk register | green |

### Quick Start

> Full guides: [`docu/deployment-dev.md`](./docu/deployment-dev.md) · [`docu/deployment-prod-like.md`](./docu/deployment-prod-like.md).

```bash
# Pull models on the host
ollama pull qwen2.5:32b
ollama pull qwen3-embedding:4b   # 2560 dim, requires VECTOR_DIM=2560

# Clone and start
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Dev: set FLASK_DEBUG=true, placeholders are tolerated
# Hardened: keep FLASK_DEBUG=false, generate real SECRET_KEY,
#           NEO4J_PASSWORD, AGORA_AUTH_TOKEN
docker compose up -d --build
```

Open: [Frontend](http://localhost:5173) · [Backend health](http://localhost:5001/health) · [Neo4j Browser](http://localhost:7474)

Local dev without Docker:

```bash
npm run setup:all
npm run dev
```

#### Rebuild the container after larger changes

```bash
cd ~/agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache agora
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Named volumes (Neo4j data, Redis persistence) survive — only the `agora` image is replaced.

### Configuration Highlights

```env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b
NEO4J_URI=bolt://localhost:7687
EMBEDDING_MODEL=qwen3-embedding:4b
VECTOR_DIM=2560

AGENT_LANGUAGE=de
REPORT_LANGUAGE=German
TIME_PROFILE=dach_default

AGORA_PERSONA_DETAIL_LEVEL=standard
ENABLE_AGENT_TOOLS=false
MAX_TOOL_CALLS_PER_ACTION=2
```

Optional web tools for the ReportAgent:

```env
TAVILY_API_KEY=...
ENABLE_WEB_TOOLS=true
```

### Model Switching

`LLM_MODEL_NAME` is the default only. The UI lists curated presets and locally installed Ollama models. The selected model is passed into simulation preparation and report generation. Prepared simulations keep their own `llm_model` in `simulation_config.json` — re-prepare a simulation when you want to run it with another model.

### Agent Tool-Use

Disabled by default. When enabled, agents may run a limited number of graph/context tool calls before producing an action. This can improve context but increases latency and LLM usage. If Neo4j credentials are unavailable at runtime, the tool-aware loop fails closed and falls back to standard OASIS `LLMAction`.

### GPU / CPU

Agora detects GPU usage automatically via the Ollama REST API (`/api/ps`) — no `nvidia-smi` or NVIDIA Container Toolkit required inside the container.

- **GPU active**: `/api/status` reports `ollama_uses_gpu: true` with VRAM usage in GB.
- **CPU-only**: when Ollama reports models without VRAM, status surfaces a hint.
- **Ollama unreachable**: status reports `ollama_uses_gpu: null`.

For GPU acceleration, run Ollama on the host with GPU access. Container-side GPU passthrough via NVIDIA Container Toolkit is optional (commented section in `docker-compose.yml`); not needed for host-side Ollama.

### Architecture snapshot

```text
Flask API (modular)
  ├─ api/graph.py · api/report.py · api/runs.py · api/status.py
  └─ api/simulation_*.py (lifecycle, prepare, profiles, run, metrics, …)
        │
        ▼
Service Layer (AgoraContainer DI)
  ├─ GraphBuilderService / TemporalGraphService
  ├─ SimulationManager / SimulationRunner
  ├─ NetworkAnalyticsService / OntologyMutationService
  ├─ PersonaEntityContextService          (new, #69)
  ├─ ReportAgent (package, post-#202) / GraphToolsService / WebTools
  └─ EventBus (Redis | File | InMemory)
        │
        ▼
Storage Layer → Neo4j / Ollama / Redis / OASIS subprocesses
```

### Development checks

```bash
npm run setup:all
npm run dev
npm run check
cd backend && uv run pytest
```

Doc index (selection):

- Deployment: [`docu/deployment-dev.md`](./docu/deployment-dev.md) · [`docu/deployment-prod-like.md`](./docu/deployment-prod-like.md)
- Operations: [`docu/operations.md`](./docu/operations.md) · [`docu/backup-restore.md`](./docu/backup-restore.md)
- Release process: [`docu/release-process.md`](./docu/release-process.md)
- Auth & security: [`docu/auth.md`](./docu/auth.md) · [`docu/security-hardening.md`](./docu/security-hardening.md) · [`docu/decisions/0001-auth-model.md`](./docu/decisions/0001-auth-model.md) · [`docu/dependency-risk-register.md`](./docu/dependency-risk-register.md)
- API contracts: [`docu/api-contracts.md`](./docu/api-contracts.md)
- Architecture: [`docu/target-architecture.md`](./docu/target-architecture.md)
- Status / tests / coverage: [`docu/STATUS.md`](./docu/STATUS.md)

### Attribution

Agora is a fork/derivative of [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), which itself is based on [666ghj/MiroFish](https://github.com/666ghj/MiroFish). The simulation engine uses [OASIS](https://github.com/camel-ai/oasis) from CAMEL-AI.

License: AGPL-3.0. See [LICENSE](./LICENSE).

---

<div align="center">
<sub>Maintained by</sub><br><br>
<a href="https://alexle135.de">
<img src="./media/credits/alexle135-brand.png" alt="AlexLE135.de — Systemintegration. Automatisierung. Infrastruktur." width="320"/>
</a>
</div>
