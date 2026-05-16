<div align="center">

<img src="./media/agora-logo.gif" alt="Agora" width="480"/>

# Agora

**Hybride Multi-Agent-Analyseplattform für simulierte Zielgruppen-, Stakeholder- und Marktreaktionen.**

Dokumente, Webseiteninhalte oder strategische Fragestellungen hochladen, Wissensgraph extrahieren, Personas ableiten, Reaktionen simulieren und evidenzorientierte Reports erzeugen.

[![Repository](https://img.shields.io/badge/GitHub-arn0ld87%2Fagora-111?style=flat-square&logo=github)](https://github.com/arn0ld87/agora)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20or%20cloud-000?style=flat-square)](https://ollama.com/)
[![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen?style=flat-square)](./CHANGELOG.md)

[Quickstart](#quickstart) · [Betriebsmodi](#betriebsmodi) · [Architektur](#architektur) · [Konfiguration](#konfiguration) · [Sicherheit](#sicherheit) · [Doku](./docs/) · [Status](./docs/STATUS.md)

</div>

---

> **Status:** v1.0.0 auf `main`.
> Agora ist ein **experimenteller Fork** und aktuell bewusst **Single-User-only**
> ([ADR-0001](./docs/decisions/0001-auth-model.md)).
> **Nicht ungeschützt ins öffentliche Internet stellen.** Nutze VPN, Tailscale, Reverse Proxy und Auth-Token.

## Was ist Agora?

Agora ist ein Analyse- und Simulationssystem für Texte, Pläne, Webseiten, Kampagnen, Produkte und strategische Fragen.

Die Plattform baut aus Eingangsdaten einen Knowledge Graph, erzeugt daraus differenzierte Personas und simuliert deren Reaktionen in einer Multi-Agent-Umgebung. Das Ergebnis ist ein Report mit Segmentanalyse, simulierten O-Tönen, Confidence-Scores, Evidence-Bezügen, Hypothesen und Datenlücken.

Agora ist **lokal betreibbar**, aber nicht darauf beschränkt. In realistischen Setups läuft Agora häufig hybrid: Infrastruktur lokal oder auf einem eigenen Server, LLMs und Embeddings je nach Bedarf lokal, über Ollama Cloud oder über OpenAI-kompatible Provider.

## Wofür Agora gedacht ist

Typische Einsätze:

- Kommunikations- und Kampagnenentwürfe gegen Zielgruppenreaktionen prüfen
- Stakeholder-Cluster, Einwände und Polarisierung früh erkennen
- Produktideen, Webseiten, Pitches oder Positionierungen vorab simulieren
- Varianten von Narrativen, Angeboten oder Policies vergleichen
- DACH-spezifische Sprache, Tonalität und Einwände sichtbar machen
- Hypothesen, Risiken und Datenlücken vor echten Interviews strukturieren

Agora ersetzt keine echte Marktforschung. Es erzeugt simulierte Reaktionen auf Basis der Eingabedaten, Personas, Modelle und Prompts.

## Was Agora erzeugt

Ein Run kann unter anderem folgende Artefakte erzeugen:

- Executive Summary
- Segmentanalyse
- Persona-Reaktionen
- simulierte O-Töne
- Claims mit Confidence-Scores
- Evidence- und Provenance-Bezüge
- Hypothesen ohne ausreichende Evidence
- Datenlücken und suggested fixes
- Graphmetriken wie Cluster, Echo-Chamber-Index und Bridge Agents
- Audit-Trail für Reportaussagen
- PDF-/Report-Export

## Betriebsmodi

Agora ist providerneutral und kann lokal, hybrid oder serverbasiert betrieben werden.

| Modus | Beschreibung | Geeignet für |
|---|---|---|
| Lokal | Backend, Frontend, Neo4j, Redis, LLMs und Embeddings laufen auf eigener Maschine | Datenschutz, Tests, Offline-Workflows |
| Hybrid | Agora läuft lokal oder auf VPS, Modelle kommen über lokale und externe Provider | bessere Modellqualität, flexible Kostenkontrolle |
| Server/VPS | Agora läuft dauerhaft auf einem Server und wird über Tailscale, VPN oder Reverse Proxy genutzt | längere Simulationen, Zugriff von mehreren eigenen Geräten |

Empfehlung: Für Entwicklung lokal starten, für längere Runs einen VPS oder Server nutzen und den Zugriff über Tailscale oder VPN absichern.

## Pipeline

1. **Input** — PDF, Markdown, Text, Webseite oder Fragestellung
2. **Graph Build** — Entitäten, Aussagen und Beziehungen nach Neo4j
3. **Persona Spawn** — Rollen, Haltungen, Interessen und Aktivitätsmuster
4. **Simulation** — Multi-Agent-Simulation mit OASIS/CAMEL
5. **Aggregation** — Graphdaten, Agentenreaktionen und Metriken zusammenführen
6. **Report** — Claims, Evidence, Confidence, Hypothesen und Datenlücken erzeugen
7. **Compare** — Runs, Varianten, Graph-Diffs und Reportversionen vergleichen

## Architektur

```text
Vue 3 + Pinia + Zod + Vite
  └─ Wizard, Runs Dashboard, Graph-, Simulation- und Report-UI

Flask API + Pydantic v2
  ├─ contracts/    Single Source of Truth für API- und Frontend-Schemas
  ├─ api/          Auth, Upload, Graph, Simulation, Report, Runs
  ├─ services/     Graph Build, Personas, Reports, Metrics
  ├─ storage/      Neo4j, Embeddings, NER, Search
  └─ scripts/      OASIS-/CAMEL-Subprozess-Runner

Runtime
  ├─ Neo4j 5.18+              Knowledge Graph
  ├─ Redis                    Pub/Sub, IPC, Status-Events
  ├─ Ollama lokal/cloud       lokale oder Cloud-Modelle
  ├─ OpenAI-kompatible APIs   externe LLM- und Embedding-Endpunkte
  └─ OASIS / CAMEL            Multi-Agent-Simulation
```

Details in [`docs/architecture.md`](./docs/architecture.md).

## Quickstart

Voraussetzungen:

- Node.js 18+
- Python 3.11+
- `uv`
- Docker oder Docker Compose
- Neo4j 5.18+
- Redis
- lokaler oder OpenAI-kompatibler LLM-Endpunkt

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env

# Modelle vorbereiten, falls Ollama genutzt wird
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

Volle Setup-Guides:

- [`docs/deployment-dev.md`](./docs/deployment-dev.md)
- [`docs/deployment.md`](./docs/deployment.md)
- [`docs/provider-runtime-settings.md`](./docs/provider-runtime-settings.md)

## Konfiguration

Minimalbeispiel für Ollama lokal oder Ollama Cloud:

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

Beispiel für einen OpenAI-kompatiblen externen Provider:

```env
LLM_API_KEY=<api-key>
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL_NAME=<provider-model>

EMBEDDING_BASE_URL=https://api.example.com/v1
EMBEDDING_MODEL=<embedding-model>
VECTOR_DIM=<passende-dimension>
```

Wichtig: `EMBEDDING_MODEL` und `VECTOR_DIM` müssen zusammenpassen. Falsche Dimensionen führen zu kaputten oder unbrauchbaren Embedding-Indizes.

## LLM- und Embedding-Provider

Agora ist nicht auf einen einzelnen Provider festgelegt.

Unterstützte Zielarchitektur:

- Ollama lokal
- Ollama Cloud
- OpenAI API
- Gemini über kompatible Adapter
- andere OpenAI-kompatible Gateways
- getrennte Provider für Chat-Modelle und Embeddings

Empfehlung für produktive Runs: Ein stärkeres Cloud- oder API-Modell für Report-Synthese, ein günstiges oder lokales Modell für Vorverarbeitung und ein stabiles Embedding-Modell mit dokumentierter Dimension.

## Sicherheit

Agora reduziert die Angriffsfläche bewusst, ersetzt aber keinen Multi-User-Sicherheitsstack.

Aktuelle Grundannahmen:

- Single-User-Betrieb
- keine öffentliche SaaS-Plattform
- keine ungeprüfte Mehrbenutzerverwaltung
- keine Speicherung von Secrets in Report-Artefakten

Empfohlene Schutzmaßnahmen:

- `AGORA_AUTH_TOKEN` setzen
- keine ungeschützte Veröffentlichung ins öffentliche Internet
- Zugriff bevorzugt über Tailscale, VPN oder Reverse Proxy
- TLS am Reverse Proxy terminieren
- Upload-Größen begrenzen
- Rate-Limits aktivieren
- Logs regelmäßig prüfen
- Secrets nicht in Prompts, Reports oder Simulationen schreiben
- Cloud-Provider-Nutzung im UI und in der Dokumentation sichtbar machen

Bereits vorgesehene Sicherheitsmechanismen:

- `AGORA_AUTH_TOKEN` schützt `/api/*`
- `?token=` ist im Non-Debug-Modus blockiert
- SSE und Downloads nutzen signed Tickets
- Rate-Limits auf Ticket-, Upload-, Simulation- und Report-Endpunkten
- Secrets werden nicht in Simulation-Artefakte serialisiert

Details:

- [`docs/security-hardening.md`](./docs/security-hardening.md)
- [`docs/auth.md`](./docs/auth.md)
- [`SECURITY.md`](./SECURITY.md)

## Grenzen

Agora erzeugt Simulationen, keine objektive Wahrheit.

Wichtig:

- simulierte Persona-Aussagen sind keine echten Kundenmeinungen
- Confidence-Scores bewerten interne Evidenzbindung, nicht reale Wahrheit
- Reports hängen stark von Seed-Daten, Modellqualität und Prompts ab
- kleine Modelle erzeugen schneller generische oder schlecht belegte Aussagen
- Cloud-Provider können Datenschutz-, Compliance- und Kostenfragen auslösen
- starke Ergebnisse sollten mit echten Interviews, Nutzertests oder Fachreviews validiert werden

Agora ist am stärksten, wenn es als Entscheidungsunterstützung genutzt wird: für Risiken, Gegenargumente, Segmentmuster, Hypothesen und nächste Fragen.

## Entwicklungsstatus

Agora ist experimentell, aber bereits deutlich über einen einfachen Prototyp hinaus.

Aktueller Fokus:

- robustere Evidence-Bindung
- bessere Report-Qualität
- klare Trennung von Claims, Hypothesen und Datenlücken
- Provider-Konfiguration über UI und CLI
- stabilere Cloud-/Hybrid-Deployments
- bessere PDF-/Export-Ausgabe
- reproduzierbare Runs und Vergleichbarkeit

## Mitarbeiten

Kurzeinstieg in [`CONTRIBUTING.md`](./CONTRIBUTING.md).

Agenten-Setup für Claude Code, Codex und ähnliche Tools: [`AGENTS.md`](./AGENTS.md).

Runbooks: [`docs/runbooks/`](./docs/runbooks/).

## Herkunft und Lizenz

Fork/Derivat von [nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), basierend auf [666ghj/MiroFish](https://github.com/666ghj/MiroFish).

Simulations-Engine: [OASIS](https://github.com/camel-ai/oasis) von CAMEL-AI.

Lizenz: **AGPL-3.0**, siehe [LICENSE](./LICENSE).
