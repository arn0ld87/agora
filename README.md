<div align="center">

<img src="./media/agora-logo.gif" alt="Agora" width="480"/>

# Agora

**Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.**

Dokument hochladen, Wissensgraph extrahieren, Personas ableiten, Reaktionen simulieren, belegbaren DACH-Report erzeugen.

[![Repository](https://img.shields.io/badge/GitHub-arn0ld87%2Fagora-111?style=flat-square&logo=github)](https://github.com/arn0ld87/agora)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20or%20cloud-000?style=flat-square)](https://ollama.com/)
[![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen?style=flat-square)](./CHANGELOG.md)

[Quickstart](#quickstart) · [Architektur](#architektur) · [Konfiguration](#konfiguration) · [Doku](./docs/) · [Status](./docs/STATUS.md)

</div>

---

> **Status:** v1.0.0 auf `main` (2026-05-11).
> Agora ist ein **experimenteller Fork**, bewusst **Single-User-only**
> ([ADR-0001](./docs/decisions/0001-auth-model.md)).
> **Nicht direkt ins öffentliche Internet stellen** — nur hinter Reverse-Proxy oder Tunnel.

## Was ist Agora?

Ein lokal-first Resonanzlabor für Texte, Pläne und Dossiers. Lade ein Dokument hoch — Agora baut daraus einen
Knowledge Graph, generiert differenzierte Personas und lässt diese in einer OASIS-Simulation auf den Inhalt
reagieren. Ergebnis: ein Report mit Zitaten, Confidence-Scores und Provenance-Ankern.

Typische Einsätze:

- Kommunikations- und Kampagnenentwürfe gegen Zielgruppenreaktionen prüfen
- Stakeholder-Cluster, Einwände und Polarisierung früh erkennen
- Varianten von Narrativen oder Policies vergleichen
- DACH-spezifische Sprache und Tonalität nutzen

## Pipeline

1. **Upload** — PDF, Markdown oder Text + Fragestellung
2. **Graph Build** — Entitäten/Beziehungen nach Neo4j
3. **Persona Spawn** — Rollen, Haltungen, Aktivitätsmuster
4. **Simulation** — OASIS als Subprozess (Status via Redis/SSE)
5. **Report** — Aggregation aus Graph, Simulation, Interviews
6. **Compare** — Graph-Diff, Branch-Compare, Runs Dashboard

## Architektur

```text
Vue 3 + Pinia + Zod + Vite
  └─ Wizard, Runs Dashboard, Graph- und Report-UI

Flask API + Pydantic v2
  ├─ contracts/    Single Source of Truth (API + Zod-Spiegel)
  ├─ api/          Auth, Graph, Simulation, Report, Runs
  ├─ services/     Graph Build, Personas, Reports, Metrics
  ├─ storage/      Neo4j, Embeddings, NER, Search
  └─ scripts/      OASIS-Subprozess-Runner

Runtime
  ├─ Neo4j 5.18+         Knowledge Graph
  ├─ Redis               Pub/Sub-IPC
  ├─ Ollama / OpenAI-API LLM- und Embedding-Endpunkte
  └─ OASIS / CAMEL       Multi-Agent-Simulation
```

Details in [`docs/architecture.md`](./docs/architecture.md).

## Quickstart

Voraussetzungen: Node.js 18+, Python 3.11+, `uv`, Neo4j 5.18+, Ollama lokal oder OpenAI-kompatibler Endpoint.

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Modelle vorbereiten (aktiv gepflegt)
ollama pull qwen3-coder-next:cloud
ollama pull qwen3-embedding:4b

# Dev-Stack starten
docker compose up -d --build
```

| Dienst | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend Health | <http://localhost:5001/health> |
| Neo4j Browser | <http://localhost:7474> |

Lokal ohne Docker:

```bash
npm run setup:all
npm run dev
```

Volle Setup-Guides: [`docs/deployment-dev.md`](./docs/deployment-dev.md) · [`docs/deployment.md`](./docs/deployment.md).

## Konfiguration

```env
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen3-coder-next:cloud

EMBEDDING_MODEL=qwen3-embedding:4b
EMBEDDING_BASE_URL=http://localhost:11434
VECTOR_DIM=2560

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<setzen>

AGENT_LANGUAGE=de
REPORT_LANGUAGE=German
TIME_PROFILE=dach_default
```

Embedding-Modell und `VECTOR_DIM` müssen zusammenpassen — Tabelle in [`docs/provider-runtime-settings.md`](./docs/provider-runtime-settings.md).

## Sicherheit

Agora reduziert die Angriffsfläche bewusst, ersetzt aber keinen Multi-User-Sicherheitsstack.

- `AGORA_AUTH_TOKEN` schützt `/api/*`, `?token=` ist im Non-Debug-Modus blockiert
- SSE und Downloads nutzen signed Tickets
- Rate-Limits auf Ticket-, Upload-, Simulation- und Report-Endpunkten
- Secrets werden nicht in Simulation-Artefakte serialisiert

Details: [`docs/security-hardening.md`](./docs/security-hardening.md) · [`docs/auth.md`](./docs/auth.md) · [`SECURITY.md`](./SECURITY.md).

## Mitarbeiten

Kurzeinstieg in [`CONTRIBUTING.md`](./CONTRIBUTING.md). Agenten-Setup (Claude Code, Codex): [`AGENTS.md`](./AGENTS.md).
Detail-Runbooks unter [`docs/runbooks/`](./docs/runbooks/).

## Herkunft und Lizenz

Fork/Derivat von [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) (basierend auf
[666ghj/MiroFish](https://github.com/666ghj/MiroFish)). Simulations-Engine: [OASIS](https://github.com/camel-ai/oasis) von CAMEL-AI.

Lizenz: **AGPL-3.0**, siehe [LICENSE](./LICENSE).
