<div align="center">

<img src="./media/agora-logo.gif" alt="Agora" width="480"/>

# Agora

**Evidenzorientierte Multi-Agent-Analyseplattform für simulierte Zielgruppen-, Stakeholder- und Marktreaktionen.**

Dokumente, Webseiten und strategische Fragestellungen werden in einen Wissensgraphen überführt, daraus entstehen Personas, Simulationen und nachvollziehbare Reports mit Evidence-, Confidence- und Datenlücken-Bezug.

[![Repository](https://img.shields.io/badge/GitHub-arn0ld87%2Fagora-111?style=flat-square&logo=github)](https://github.com/arn0ld87/agora)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20or%20cloud-000?style=flat-square)](https://ollama.com/)
[![Version](https://img.shields.io/badge/Version-0.8.0-blue?style=flat-square)](./VERSION)

[Quick Start](#quick-start) · [Einsatz](#wofür-agora-gedacht-ist) · [Pipeline](#pipeline) · [Architektur](#architektur) · [Release-Weg](#release-weg-bis-100) · [Status](./docs/STATUS.md) · [Roadmap](./ROADMAP.md)

</div>

---

> **Aktueller Reifegrad: `0.8.0` Technical Preview.**
>
> Agora ist deutlich über einen einfachen Prototyp hinaus, aber noch nicht stabil genug für `1.0.0`: Fünf Kern-E2E-Smokes sind offen, Altpfade werden noch konsolidiert und die Produktwirkung ist noch nicht systematisch kalibriert.
>
> Agora ist ein experimentelles **Single-User-System**. Nicht ungeschützt ins öffentliche Internet stellen. Nutze VPN, Tailscale oder einen abgesicherten Reverse Proxy.

## Quick Start

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh
```

Danach `.env` anpassen und starten:

```bash
bun run dev
```

Docker startet den vollständigen Stack inklusive Neo4j und Redis:

```bash
./install.sh --docker
```

| Dienst | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:5001> |
| Backend Readiness | <http://localhost:5001/readyz> |
| Neo4j Browser | <http://localhost:7474> |

`./install.sh --help` zeigt alle Optionen. `./install.sh --check` führt die lokalen Qualitätsprüfungen aus.

## Was ist Agora?

Agora ist ein lokal oder hybrid betreibbares Analyse- und Simulationssystem. Es soll keine Zukunft vorhersagen und keine echte Marktforschung ersetzen. Es strukturiert mögliche Reaktionen, Einwände, Risiken und Datenlücken auf Grundlage der bereitgestellten Informationen, Modelle und Prompts.

Ein typischer Lauf erzeugt unter anderem:

- einen Wissensgraphen aus Dokumenten, Texten oder Webseiten
- differenzierte Persona- und Stakeholder-Profile
- simulierte Reaktionen und Diskussionsverläufe
- Segment- und Polarisierungsanalysen
- Claims mit Evidence- und Provenance-Bezügen
- Confidence-Werte für interne Evidenzbindung
- Hypothesen ohne ausreichende Belege
- Datenlücken und nächste Forschungsfragen
- Reports, Exporte und Audit-Trails

## Wofür Agora gedacht ist

Agora eignet sich vor allem als **strategisches Pre-Mortem- und Variantenwerkzeug**:

- Kommunikations- und Kampagnenentwürfe auf mögliche Einwände prüfen
- Stakeholder-Cluster und Polarisierung früh sichtbar machen
- Produktideen, Webseiten, Pitches oder Positionierungen vergleichen
- Narrative, Angebote oder Policies gegeneinander testen
- DACH-spezifische Sprache, Tonalität und Einwände untersuchen
- Hypothesen vor echten Interviews oder Nutzertests strukturieren

Agora ist am stärksten, wenn das Ergebnis anschließend durch echte Interviews, Fachreviews, Nutzertests oder vorhandene Vergleichsdaten geprüft wird.

## Pipeline

1. **Onboarding** — Profil, Provider, Modelle, Embeddings und Datenschutz konfigurieren
2. **Input** — PDF, Markdown, Text, Webseite oder Fragestellung einlesen
3. **Graph Build** — Entitäten, Aussagen und Beziehungen nach Neo4j extrahieren
4. **Persona Spawn** — Rollen, Haltungen, Interessen und Aktivitätsmuster ableiten
5. **Review** — Personas prüfen, ablehnen oder regenerieren
6. **Simulation** — Multi-Agenten-Lauf mit OASIS/CAMEL ausführen
7. **Aggregation** — Graphdaten, Agentenreaktionen und Metriken zusammenführen
8. **Report** — Claims, Evidence, Confidence, Hypothesen und Datenlücken erzeugen
9. **Compare** — Runs, Varianten und Graph-Diffs vergleichen
10. **Migration** — Embedding-Modelle versioniert und fortsetzbar neu indexieren

## Architektur

```text
Vue 3 + TypeScript + Pinia + Zod + Vite
  ├─ Onboarding und Run-Anlage
  ├─ AiModelPicker als kanonische Modellauswahl
  ├─ Runs-, Graph-, Simulation-, Compare- und Report-Oberflächen
  └─ Settings für Provider, Routing, Embeddings, Profil und Audit

Flask + Pydantic v2 + Python 3.14
  ├─ contracts/                 API- und Schema-Single-Source-of-Truth
  ├─ api/                       Auth, Graph, Simulation, Report, Runs, Settings
  ├─ services/                  Fachlogik, Evidence, Migrationen, Provider
  ├─ llm/providers/registry.py  zentrale Provider-Erkennung
  ├─ storage/                   Neo4j, Embeddings, Suche
  └─ scripts/                   OASIS-/CAMEL-Runner

Runtime
  ├─ Neo4j                     Knowledge Graph und Vector-Indizes
  ├─ Redis                     Events, IPC und Status
  ├─ Ollama lokal oder Cloud
  ├─ OpenAI-kompatible Provider
  ├─ OpenTelemetry / SigNoz optional
  └─ OASIS / CAMEL
```

Details: [`docs/architecture.md`](./docs/architecture.md)

## Betriebsmodi

| Modus | Beschreibung | Geeignet für |
|---|---|---|
| Lokal | gesamter Stack und Modelle auf einer Maschine | Datenschutz, Tests, Offline-Workflows |
| Hybrid | Infrastruktur selbst betrieben, ausgewählte Cloud-Modelle | Qualität, Kostenkontrolle, flexible Hardware |
| Server/VPS | dauerhafter Betrieb über VPN oder Reverse Proxy | längere Runs und Zugriff von mehreren eigenen Geräten |

## Voraussetzungen

- Node.js 20 oder neuer
- Bun 1.3 oder neuer
- Python 3.14
- `uv`
- Docker oder Docker Compose
- Neo4j 5.18 oder neuer
- Redis
- lokaler oder OpenAI-kompatibler LLM-Endpunkt

### Docker Compose

```bash
cp .env.docker.example .env

python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('AGORA_AUTH_TOKEN=' + secrets.token_urlsafe(32))"

docker compose up -d --build
```

### Host-Entwicklung

```bash
cp .env.example .env
bun run setup:all
bun run dev
```

Weitere Guides:

- [`docs/deployment-dev.md`](./docs/deployment-dev.md)
- [`docs/deployment.md`](./docs/deployment.md)
- [`docs/provider-runtime-settings.md`](./docs/provider-runtime-settings.md)

## Provider und Modelle

Agora trennt Chat-/Generierungsmodelle und Embedding-Konfigurationen. Unterstützt beziehungsweise vorgesehen sind:

- Ollama lokal
- Ollama Cloud
- OpenAI
- Gemini
- MiniMax
- weitere OpenAI-kompatible Gateways

Explizit konfigurierte Provider-Verbindungen und Routen sollen stets Vorrang vor automatischer URL- oder Modellnamen-Erkennung haben.

## Sicherheit

Grundannahmen:

- Single-User-Betrieb
- keine öffentliche SaaS-Plattform
- kein ungeprüfter Mehrbenutzerbetrieb
- keine Speicherung von Secrets in Reports oder Simulation-Artefakten

Schutzmaßnahmen:

- `AGORA_AUTH_TOKEN` setzen
- TLS am Reverse Proxy terminieren
- Zugriff über Tailscale oder VPN bevorzugen
- Upload- und Rate-Limits aktiv lassen
- Cloud-Datenflüsse bewusst prüfen
- Secrets niemals in Prompts oder Dokumentationen einfügen

Bereits vorhanden sind signierte SSE-/Download-Tickets, timing-sichere Tokenprüfung, Secret Stores, Rate-Limits, Readiness-Prüfungen und Security-Scans.

Details:

- [`SECURITY.md`](./SECURITY.md)
- [`docs/security-hardening.md`](./docs/security-hardening.md)
- [`docs/auth.md`](./docs/auth.md)
- [`docs/dependency-risk-register.md`](./docs/dependency-risk-register.md)

## Grenzen

- simulierte Persona-Aussagen sind keine echten Kundenmeinungen
- Confidence bewertet interne Evidenzbindung, nicht reale Wahrheit
- Ergebnisse hängen von Eingangsdaten, Modellen, Prompts und Seeds ab
- kleine Modelle erzeugen schneller generische oder schlecht belegte Aussagen
- Cloud-Provider bringen Datenschutz-, Compliance- und Kostenfragen mit
- ein einzelner Run zeigt keine statistisch belastbare Verteilung

## Release-Weg bis 1.0.0

| Version | Bedeutung | Zentrale Freigabekriterien |
|---|---|---|
| **0.8.0** | Technical Preview, aktueller Stand | Kernfunktionen vorhanden; offene E2E-, Altpfad- und Dokumentationsschuld ist sichtbar |
| **0.9.0** | Stability Beta | 6/6 Kern-Smokes grün, E2E als Required Check, eine Provider-/Routing-Wahrheit, Vue-v4 als einziges Produktfrontend, Dependency- und Dokumentations-SSoTs bereinigt |
| **0.10.0** | Release Candidate | reproduzierbare Runs, Kosten-/Zeitbudgets, Backup/Restore und Upgrade/Rollback dokumentiert, Kalibrierungsbaseline vorhanden, keine kritischen Release-Blocker |
| **1.0.0** | stabile Single-User-Version | stabile Verträge und Datenmigrationen, reproduzierbare Installation, belastbarer Referenzlauf, dokumentierte Kompatibilitätsregeln und nachgewiesener Produktnutzen |

Zwischen `0.10.0` und `1.0.0` werden keine großen neuen Produktbereiche begonnen. Die Phase dient ausschließlich Release-Härtung, Fehlerkorrektur und Dokumentation.

Die ausführbaren Schritte werden ausschließlich als [GitHub Issues](https://github.com/arn0ld87/agora/issues) gepflegt. Die strategische Reihenfolge steht in [`ROADMAP.md`](./ROADMAP.md).

Version-Cut folgt [`docs/runbooks/release-versioning.md`](./docs/runbooks/release-versioning.md).

## Dokumentationshierarchie

Es gibt vier aktive Ebenen:

1. **[`README.md`](./README.md)** — Produkt, Einstieg, Grenzen und Release-Linie
2. **[`docs/STATUS.md`](./docs/STATUS.md)** — verifizierter Istzustand
3. **[`ROADMAP.md`](./ROADMAP.md)** — Releases und strategische Reihenfolge
4. **[GitHub Issues](https://github.com/arn0ld87/agora/issues)** — konkrete, ausführbare Arbeit

ADRs, Architektur-, Security- und Runbook-Dokumente bleiben verbindliche Referenzen. Historische Planungsdokumente liegen im [`docs/archive/planning/`](./docs/archive/planning/)-Index und sind keine aktiven Taskquellen.

## Qualität prüfen

```bash
# vollständiges lokales Gate
bash scripts/pre-push-gate.sh

# gezielte Gates
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Der aktuelle Test-, Coverage- und E2E-Stand steht in [`docs/STATUS.md`](./docs/STATUS.md).

## Mitwirken

- [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- [`AGENTS.md`](./AGENTS.md)
- [`CLAUDE.md`](./CLAUDE.md)
- [`docs/runbooks/`](./docs/runbooks/)

## Herkunft und Lizenz

Agora entstand aus `MiroFish-Offline`, wurde aber bei Architektur, Verträgen, Betrieb und Produktziel grundlegend weiterentwickelt. OASIS-Komponenten stammen aus dem CAMEL-AI-Ökosystem.

Lizenz: **AGPL-3.0**, siehe [`LICENSE`](./LICENSE).
