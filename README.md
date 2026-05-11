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

[Status](./docs/status.md) · [Architektur](./docs/architecture.md) · [Development](./docs/development.md) · [Security](./SECURITY.md)

</div>

---

## Was ist Agora?

Agora ist ein lokal-first Resonanzlabor für Texte, Pläne und Dossiers. Aus einem Upload baut Agora einen Knowledge Graph, erzeugt daraus differenzierte Personas, simuliert deren Social-Media-Reaktionen mit OASIS/CAMEL und erstellt daraus einen Report mit Zitaten, Confidence-Scores und Provenance-Ankern.

Typische Einsätze:

- Kommunikations- und Kampagnenentwürfe gegen Zielgruppenreaktionen prüfen
- Stakeholder-Cluster, Einwände und Polarisierung früh erkennen
- Varianten von Narrativen, Produkttexten oder Policies vergleichen
- DACH-spezifische Sprache, Timing-Profile und Report-Tonalität nutzen

Agora ist ein experimenteller Fork und kein gehosteter Multi-Tenant-Dienst. Modellqualität, JSON-Verhalten, Neo4j, Redis und OASIS-Subprozesse sind Teil des Laufzeitmodells.

## Kernfunktionen

- Upload von PDF, Markdown oder Text
- Knowledge-Graph-Aufbau mit Neo4j und Embeddings
- Persona-Generierung mit optionalem Review-Gate
- OASIS/CAMEL-Simulation als entkoppelter Subprozess
- Live-Status, Logs und Events über Redis/File-IPC und SSE
- Report-Erzeugung mit Evidence-Ankern, Confidence-Scores und DACH-Wording
- Export als Markdown, JSON, CSV, ZIP-Bundle und Browser-Print-PDF
- Graph-Diff, Simulation-Compare und Runs Dashboard

## Architektur-Kurzbild

```text
Vue 3 + Pinia + Zod + Vite
  -> Frontend-Wizard, Runs Dashboard, Graph/Compare UI, Report UI

Flask API + Pydantic v2
  -> API-Verträge, Auth, Graph, Simulation, Report, Runs, Status

Runtime
  -> Neo4j 5.18+, Redis, Ollama/OpenAI-kompatible Endpunkte, OASIS/CAMEL
```

Pipeline:

1. Upload
2. Graph Build
3. Persona Spawn
4. Simulation
5. Report
6. Compare

Details: [docs/architecture.md](./docs/architecture.md)

## Quickstart mit Docker Compose

Voraussetzungen:

- Docker + Docker Compose
- Ollama oder ein OpenAI-kompatibler LLM-/Embedding-Endpunkt
- `.env` auf Basis von `.env.example`

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

ollama pull qwen2.5:32b
ollama pull qwen3-embedding:4b

docker compose up -d --build
```

Endpoints:

| Dienst | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend Health | <http://localhost:5001/health> |
| Neo4j Browser | <http://localhost:7474> |

Für den lokalen Dev-Stack siehe [docs/deployment-dev.md](./docs/deployment-dev.md). Für gehärteten Single-User-Betrieb siehe [docs/deployment-prod.md](./docs/deployment-prod.md).

## Lokaler Dev-Start

```bash
npm run setup:all
npm run dev
```

Quality-Gate:

```bash
npm run check
```

Backend-Teilchecks:

```bash
cd backend && uv run pytest
cd backend && uv run ruff check app/ tests/
cd backend && uv run mypy app
```

Frontend-Teilcheck:

```bash
cd frontend && npm run check
```

Details: [docs/development.md](./docs/development.md)

## Wichtige Konfiguration

Agora liest Konfiguration aus `.env` am Repo-Root.

```env
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b

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

Embedding-Modell und `VECTOR_DIM` müssen zusammenpassen. Details stehen in [docs/development.md](./docs/development.md) und [docs/deployment-dev.md](./docs/deployment-dev.md).

## Security-Hinweis

Agora v1 ist **Single-User-only**. Der API-Schutz basiert auf einem geteilten `AGORA_AUTH_TOKEN`, nicht auf einem vollständigen Multi-User-AuthN/AuthZ-Stack.

- Nicht direkt ins öffentliche Internet stellen.
- Nur hinter Reverse Proxy, Tunnel oder Tailnet betreiben.
- In Non-Debug-Setups echte Werte für `SECRET_KEY`, `NEO4J_PASSWORD` und `AGORA_AUTH_TOKEN` setzen.
- `?token=` ist im Non-Debug-Modus blockiert; SSE und Downloads nutzen signed Tickets.
- Keine echten Tokens, Keys oder `.env`-Dateien in Issues, PRs, Logs oder Diffs posten.

Einstieg: [SECURITY.md](./SECURITY.md)
Details: [docs/security.md](./docs/security.md), [docs/security-threat-model.md](./docs/security-threat-model.md), [docs/adr/0001-auth-model.md](./docs/adr/0001-auth-model.md)

## Dokumentation

| Thema | Datei |
|---|---|
| Aktueller Status, Versionen, Tests, Coverage | [docs/status.md](./docs/status.md) |
| Architektur | [docs/architecture.md](./docs/architecture.md) |
| Entwicklung | [docs/development.md](./docs/development.md) |
| Dev-Deployment | [docs/deployment-dev.md](./docs/deployment-dev.md) |
| Prod-ähnliches Single-User-Deployment | [docs/deployment-prod.md](./docs/deployment-prod.md) |
| Security-Modell | [SECURITY.md](./SECURITY.md), [docs/security.md](./docs/security.md) |
| ADRs | [docs/adr/](./docs/adr/) |
| Agenten-Runbooks | [docs/runbooks/](./docs/runbooks/) |
| Historische Arbeitsprotokolle | [docs/archive/worklogs/](./docs/archive/worklogs/) |
| Operativer Plan | [PLAN.md](./PLAN.md) |
| Änderungen | [CHANGELOG.md](./CHANGELOG.md) |

## Herkunft und Lizenz

Agora ist ein Fork / Derivat von [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), basierend auf [666ghj/MiroFish](https://github.com/666ghj/MiroFish). Die Simulations-Engine nutzt [OASIS](https://github.com/camel-ai/oasis) von CAMEL-AI.

Lizenz: AGPL-3.0, siehe [LICENSE](./LICENSE).
