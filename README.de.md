<p align="center">
  <a href="./README.md">English</a> · <strong>Deutsch</strong>
</p>

<div align="center">

<img src="./media/agora-logo-v2-light.png" alt="Agora Logo" width="520"/>

# 🏛️ AGORA

### Evidenzorientierte Multi-Agenten-Analyse für Stakeholder, Zielgruppen und komplexe Entscheidungen

**Dokumente → Knowledge Graph → Personas → Simulation → nachvollziehbarer Bericht**

[![Version](https://img.shields.io/badge/version-0.9.4-635BFF?style=flat-square)](./VERSION)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-111827?style=flat-square)](./LICENSE)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21830644-1682D4?style=flat-square)](https://doi.org/10.5281/zenodo.21830644)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5%2B-42B883?style=flat-square&logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.18%2B-4581C3?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com/)
[![E2E Smokes](https://img.shields.io/badge/E2E%20Smokes-20%2F20%20Green%20%F0%9F%9F%A2-brightgreen?style=flat-square)](./docs/STATUS.md)
[![Status](https://img.shields.io/badge/status-Stability%20Beta-F59E0B?style=flat-square)](./docs/STATUS.md)

[Demo](#demo) · [Was ist Agora?](#was-ist-agora) · [Funktionsweise](#funktionsweise) · [Prozess im UI](#-prozess-im-ui) · [Schnellstart](#schnellstart) · [Architektur](#architektur) · [Status](#projektstatus) · [Sicherheit](#sicherheit) · [Mitwirken](#projekt-unterstützen)

</div>

---

> [!IMPORTANT]
> **Agora sagt menschliches Verhalten nicht voraus.** Die Plattform erzeugt überprüfbare Szenarien, mögliche Einwände, Konfliktlinien und Datenlücken. Simulationsergebnisse ersetzen weder Interviews noch Nutzertests oder empirische Forschung.

## Demo

<p align="center">
  <a href="./media/agora-demo.mp4">
    <img src="./media/agora-demo-preview.gif" alt="Agora Demo: Simulation, Agentenreaktionen, Evidence Report und PDF-Export" width="100%">
  </a>
</p>

<p align="center">
 <strong><a href="./media/agora-demo.mp4">▶ Vollständige 43-Sekunden-Demo öffnen</a></strong><br>
  <sub>Realer Lauf zur Einführung des KI-Lernassistenten „LernKompass 2027“.</sub>
</p>

Die Demo zeigt:

1. laufende Multi-Agenten-Simulation mit Status und Ressourcenverbrauch,
2. simulierte Reaktionen und technische Laufzeitdaten,
3. einen strukturierten Report mit Risiken, Konflikten und Datenlücken,
4. den Export des Ergebnisses als PDF.

---

## Referenzlauf

Die aktuelle Referenz ist **Referenzlauf 7: AURORA mit Red-Team-Review**. Der Lauf untersucht für den fiktiven Städtischen Klinikverbund Falkenbrück den geplanten Produktivstart des KI-gestützten Triage- und Dokumentationssystems **Nexora Triage Assist**. Der Report wurde am **17. August 2026** als `report_b259e254ee3f` aus der 24-Runden-Simulation `sim_c2108c7f543e` erzeugt.

Neu sind in diesem Lauf zwei Pipeline-Stufen. Ein **eigenständiges Red-Team-Review** läuft nach dem Report und liefert 9 Befunde — unaufgelöste Spannungen zwischen Abschnitten, unbelegte Wirkungsbehauptungen und fehlende Gegenpositionen einzelner Stakeholdergruppen — dazu einen Echo-Index von 0,703, der misst, wie stark der Report die Eingabeformulierungen wiederholt. Und ungedeckte Präzision wird nicht mehr nur abgeschwächt: In fünf von sieben Abschnitten wurden **10 Faktenaussagen aus dem Fließtext entfernt und als Hypothese weitergeführt**.

Der Report bewertet vier Rollout-Varianten getrennt und empfiehlt einen **reversiblen Pilotbetrieb ausschließlich in Falkenbrück-Mitte**, gebunden an sieben benannte Nachweise vor der Freigabe, mit Verschiebung des gesamten Produktivstarts als Rückfalloption.

| Kennzahl | Wert |
|---|---|
| Simulation | `sim_c2108c7f543e`, 24 von 24 Runden |
| Reportlaufzeit | 16:46 min für 7 Abschnitte, zusätzlich 13 s Red-Team-Review |
| Agenteninterviews | `interview_agents` in allen 7 Abschnitten, 6–8 Personas je Abschnitt, 49 Antworten |
| Evidenzdatensätze | 116 (49 Interviewantworten, 31 Seed-Dokumente, 28 Graphrelationen, 8 Simulationsaktionen) |
| Claims | 29, jeder mit mindestens einem Evidenzbezug — sämtlich `low` Confidence |
| Hypothesen / Data Gaps | 136 / 126 |
| Red-Team-Befunde | 9, Echo-Index 0,703 |
| Export-IDs | abschnittsqualifiziert und kollisionsfrei (29/29 Claims, 126/126 Data Gaps, 136/136 Hypothesen) |

> [!NOTE]
> Dies ist bewusst **ein Referenzlauf und keine Hochglanz-Demo**. Er erfüllt eine Regressionserwartung aus Lauf 6 — alle 24 simulierten Persona-O-Töne verweisen jetzt auf eine konkrete `ev_`-Evidenz-ID statt auf einen generischen Seed-Anker — und dokumentiert die offenen Trust-Grenzen als Regressionsziele: Alle 29 Claims bleiben bei `low` Confidence, auch wenn mehrere Stakeholdergruppen dieselbe Aussage stützen; 92 von 116 Evidenzdatensätzen werden erhoben und angezeigt, tragen aber keinen Claim; alle 126 Data Gaps haben dieselbe Severity `medium`; und die Laufzeit stieg gegenüber Lauf 6 (16:46 min statt 8:19 min), was wegen der anderen Simulation kein direkter Reporter-Vergleich ist. Der Repository-Stand enthält nicht alle Artefakte und Replay-Daten für eine Reproduktion aus einem frischen Checkout.

**[→ Vollständige Notizen zu Referenzlauf 7](./docs/reference-runs/2026-08-17-aurora-red-team/README.de.md)** · **[English](./docs/reference-runs/2026-08-17-aurora-red-team/README.md)**

Frühere Läufe: [Referenzlauf 6](./docs/reference-runs/2026-08-14-aurora-report/README.de.md) (Same-Simulation-Reporter-Regression) · [Referenzlauf 5](./docs/reference-runs/2026-08-12-domain-migration-20-runden/README.de.md) · [Referenzlauf 4](./docs/reference-runs/2026-08-11-ki-lernassistent-20-runden/README.de.md) · [Lauf 3](./docs/reference-runs/2026-08-11-ki-lernassistent/README.md) · [Lauf 2](./docs/reference-runs/2026-08-09-domain-migration-v2/README.md) · [Lauf 1](./docs/reference-runs/2026-08-09-domain-migration/README.md)

---

## Was ist Agora?

Agora ist eine lokal oder hybrid betreibbare Analyseplattform. Sie verarbeitet Dokumente, Webseiten und Fragestellungen zu einem Wissensgraphen, erzeugt daraus überprüfbare Stakeholder-Personas und lässt diese in einer kontrollierten Multi-Agenten-Simulation interagieren.

Der anschließende Report trennt dokumentbelegte Aussagen von Hypothesen, unbelegten Behauptungen und fehlenden Informationen. Statt lediglich plausibel klingenden LLM-Text zu erzeugen, versucht Agora jede relevante Aussage auf Quellen, Graphobjekte und Simulationsereignisse zurückzuführen.

### Kernnutzen

| Problem | Agora-Ansatz |
|---|---|
| Kritische Stakeholder werden spät berücksichtigt | Konfliktlinien und Einwände vor einer Entscheidung explorieren |
| LLM-Berichte vermischen Fakten und Spekulation | Claims nach Evidenzgrad klassifizieren und mit Quellen verknüpfen |
| Varianten werden nur nach Bauchgefühl verglichen | Runs, Prompts, Modelle und Eingabevarianten gegenüberstellen |
| Entscheidungen beruhen auf unvollständigen Unterlagen | Datenlücken und nicht repräsentierte Gruppen sichtbar machen |
| Sensible Daten sollen das eigene Netz nicht verlassen | Lokaler Betrieb mit Neo4j, Redis und Ollama möglich |

### Geeignete Anwendungsfälle

- **Stakeholder- und Akzeptanzanalyse:** mögliche Widerstände, Interessen und Kommunikationsprobleme strukturieren.
- **Pre-Mortem:** untersuchen, warum ein Vorhaben scheitern könnte, bevor es umgesetzt wird.
- **Kommunikationsvarianten:** Botschaften, Narrative und Positionierungen miteinander vergleichen.
- **Produkt- und Konzeptreview:** Annahmen, Risiken und unberücksichtigte Zielgruppen identifizieren.
- **Forschung und Lehre:** Multi-Agenten-, GraphRAG- und Evidence-Gating-Workflows nachvollziehbar untersuchen.

---

## Funktionsweise

```mermaid
flowchart LR
    A[Dokumente und Webseiten] --> B[Knowledge Graph]
    B --> C[Stakeholder-Personas]
    C --> D[Multi-Agenten-Simulation]
    D --> E[Claims und Evidenzprüfung]
    E --> F[Report, Vergleich und Export]
```

### 1. Wissen aufnehmen

PDF-, Markdown- und Textdateien sowie Webseiten werden extrahiert und segmentiert. Bei **hochgeladenen Dateien** trägt jedes Segment seine Dokument- und Chunk-Herkunft durch Ingest, Graph-Aufbau und Retrieval (ADR-0013), und diese Herkunft erreicht den Report als auflösbaren Belegsanker — siehe Schritt 5. Live abgerufene Webseiten durchlaufen diesen Weg nicht: sie kommen als Rechercheergebnis in den Report und erhalten keine Dokument- oder Chunk-ID.

### 2. Knowledge Graph aufbauen

Neo4j speichert Entitäten, Beziehungen, Behauptungen, Quellenfragmente und Vektor-Embeddings. Dadurch können semantische Suche und Graphbeziehungen gemeinsam genutzt werden.

### 3. Personas erzeugen und prüfen

Agora leitet Stakeholder-Personas aus dem Wissensgraphen ab. Rollen, Interessen und Haltungen können vor dem Lauf geprüft, verändert oder neu generiert werden.

### 4. Simulation ausführen

Die OASIS-/CAMEL-Laufzeit orchestriert die Agenten. Redis überträgt Status, Ereignisse und Laufzeitdaten zwischen Simulation, Backend und Oberfläche.

### 5. Evidenzorientierten Report erstellen

Der Report verarbeitet Graph- und Simulationsdaten zu strukturierten Claims. Quellengattung, Confidence und Datenlücken werden gesondert dargestellt; jedes Evidence-Item nennt seine Gattung (Agentenzitat, Agentenaktion, Graph-Relation, Web-Quelle, Seed-Korpus). Ein Evidence-Item aus dem Seed-Korpus trägt einen auflösbaren Anker auf die konkrete Stelle im Ausgangsdokument ([#1154](https://github.com/arn0ld87/agora/issues/1154)); ein Graph-Fakt ohne belegte Herkunft bleibt Graph-Relation, statt einen geratenen Anker zu bekommen.

Confidence weist ihren eigenen Geltungsbereich aus: sie trennt Simulationskonsens von Quellenbindung, und `verified` verlangt eine Entailment-Prüfung am selben Evidence-Item, nicht bloß einen Ähnlichkeitswert. Eine nachträglich herabgestufte Aussage behält ihren Wortlaut und weist in der Aussagentabelle aus, unter welcher Stufe er entstanden ist. Der Berichtskopf nennt den Simulationsstand, auf dem der Bericht beruht — abgeschlossene Runden, geplante Gesamtzahl und ob die Simulation beim Start der Reportgenerierung noch lief.

### 6. Varianten vergleichen und exportieren

Runs können nach Modell, Prompt und Eingabevariante verglichen und in mehrere Formate exportiert werden (JSON, Markdown, CSV, ZIP). Jeder Export trägt dieselbe vertragsgeprüfte Evidenzsicht wie der Lesepfad; vertragswidrige Evidenz wird mit maschinenlesbarer Begründung zurückgehalten, statt als scheinbar geprüfte Datei auszuliefern.

Der stochastische Anteil eines Simulationslaufs ist geseedet und damit wiederholbar. Ein vollständiger Replay — gleicher Seed, gleicher Report — verlangt zusätzlich eine Aufzeichnung der Modellantworten und ist offen ([#763](https://github.com/arn0ld87/agora/issues/763)).

---

## 📸 Prozess im UI

Die Pipeline in der Agora-Weboberfläche folgt fünf aufeinander aufbauenden Schritten — Run starten, Upload, Personas, Report und Interaktion. Die folgenden Screenshots zeigen einen realen Lauf (`proj_c12f138aa04e` zum Thema SchulKI) von der Quelldatei bis zum 1‑zu‑1‑Gespräch mit den generierten Personas:

### 1. Run starten — Quelle wählen, Modell konfigurieren

Im Dashboard wird ein neuer Run angelegt: Quelldatei ablegen, Modellprofil und Sprache auswählen, Anzahl der Personas und Simulationsrunden einstellen, dann starten.

![Dashboard — Neuer Run mit Quelldatei, Profil, Sprache und Personas/Sim-Runden](./docs/assets/screenshots/process/01-dashboard-neuer-run.jpeg)

### 2. Upload — Wissensgraph aus Dokumenten aufbauen

Direkt nach dem Start extrahiert Agora aus den hochgeladenen Dokumenten Entitäten und Beziehungen und zeigt sie als interaktiven Graphen. Beziehungs‑Labels sind ein‑ und ausblendbar, der Graph ist als `.graphml`, `.svg`, `.png`, `.pdf` oder `.html` exportierbar.

| Frisch hochgeladen | Vollständig aufgebaut |
|---|---|
| ![Graph direkt nach Upload](./docs/assets/screenshots/process/02-graph-upload-frisch.jpeg) | ![Graph mit allen Entitäten und Beziehungen](./docs/assets/screenshots/process/03-graph-beziehungen.jpeg) |

Über den Relationship‑Inspector lässt sich jeder Knoten anklicken — die Beziehungen und Selbst‑Referenzen werden in einem seitlichen Panel sichtbar.

![Graph-Detail mit Relationship-Panel](./docs/assets/screenshots/process/04-persona-relationship-detail.jpeg)

### 3. Personas — Zielgruppen aus dem Graphen generieren

Aus dem Wissensgraphen werden hunderte Personas abgeleitet. Vor der Generierung werden LLM‑Modell, Agentensprache und die maximale Anzahl Agenten konfiguriert.

![Persona-Generierung: Modell, Sprache, Agentenanzahl](./docs/assets/screenshots/process/05-personas-konfiguration.jpeg)

Während der Generierung füllt sich eine Karten‑Übersicht mit Name, Rolle, Interessen und Tags. Jede Persona lässt sich vor dem Simulationslauf einzeln prüfen, bearbeiten, neu generieren oder freigeben.

| Generierte Personas | Persona-Detailansicht |
|---|---|
| ![Persona-Übersicht, 28/30 erzeugt](./docs/assets/screenshots/process/06-personas-generiert.jpeg) | ![Marko Petrović — Profil, Interessen, Biographie](./docs/assets/screenshots/process/07-persona-detail.jpeg) |

### 4. Report — Evidence-Gating & Section-Generierung

Während der Simulation laufen die Agenten‑ und Werkzeug‑Aufrufe parallel. Jede Report‑Section wird mit Evidenzbindung (ADR‑0002), Confidence und Quellenverweisen erzeugt; bei fehlgeschlagenem LLM‑Call liefert die Section stattdessen eine nachvollziehbare Fehlermeldung mit Verweis auf den Server‑Log.

![Report-Generierung mit Agent-Logs und Datenlücken](./docs/assets/screenshots/process/08-report-agent-logs.jpeg)

### 5. Interaktion — gezielte Nachfragen an die Personas

Nach Abschluss des Reports lassen sich einzelne Personas direkt ansprechen — entweder im 1‑zu‑1‑Gespräch oder als Umfrage. So können hypothesengetriebene Nachfragen gestellt und Evidenzlücken gezielt geschlossen werden.

![Interaktion: Agent auswählen, 1-zu-1-Gespräch führen](./docs/assets/screenshots/process/09-interaktion-1-zu-1.jpeg)

---

## 🏗️ Architektur

```mermaid
graph TD
    UI[Vue 3 + Vite + Pinia] <-->|REST und SSE| API[Flask + Pydantic v2]
    API --> REG[LLM Provider Registry]
    REG --> LOCAL[Ollama lokal]
    REG --> CLOUD[OpenAI-kompatible Provider]
    API --> NEO[(Neo4j Knowledge Graph)]
    API --> REDIS[(Redis Event Bus)]
    API --> OASIS[OASIS / CAMEL Runtime]
    OASIS --> REDIS
    OASIS --> NEO
    API --> EVIDENCE[Evidence-Gating Engine]
    EVIDENCE --> REPORT[Report, Vergleich und Export]
```

### Technologie-Stack

| Bereich | Technologie | Aufgabe |
|---|---|---|
| Frontend | Vue 3, Vite, Pinia, TypeScript, Zod | Oberfläche, Statusdarstellung und Eventverarbeitung |
| Backend | Flask, Pydantic v2, Python 3.14, `uv` | REST API, SSE, Contracts und Orchestrierung |
| Knowledge Graph | Neo4j 5.18+ | Entitäten, Relationen, Claims und Vektorindizes |
| Event Bus | Redis 5.0+ | Status, Pub/Sub, IPC und Simulationsereignisse |
| Simulation | OASIS / CAMEL AI | Multi-Agenten-Interaktionen und Rollensteuerung |
| LLM-Schicht | Provider Registry und `chat_json` | Ollama sowie OpenAI-kompatible Anbieter |
| Qualität | Pytest, Frontend-Tests, E2E-Smokes, GitHub Actions | Contracts, Migrationen und Kernabläufe absichern |

---

## ⚡ Schnellstart

### Voraussetzungen

- Git
- Linux oder macOS empfohlen
- ein konfigurierter LLM- und Embedding-Provider
- für den vollständigen Stack: Docker

### Lokales Setup

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
./install.sh

cp .env.example .env
# LLM-Endpunkte und Secrets in .env konfigurieren
bun run dev
```

### Docker-Setup

```bash
./install.sh --docker
```

| Dienst | Adresse | Funktion |
|---|---|---|
| Frontend | `http://localhost:5173` | Agora-Weboberfläche |
| Backend | `http://localhost:5001` | REST API und SSE Gateway |
| Readiness | `http://localhost:5001/readyz` | Backend-Status |
| Neo4j Browser | `http://localhost:7474` | Graph und Cypher Console |

> [!WARNING]
> Agora ist aktuell ein experimentelles Single-User-System. Die Anwendung nicht ungeschützt im öffentlichen Internet betreiben. Nutze Tailscale, WireGuard, ein VPN oder einen korrekt konfigurierten HTTPS-Reverse-Proxy.

---

## 📊 Projektstatus

**Aktuelle Version:** `0.9.4` Stability Beta

| Bereich | Stand |
|---|---|
| Backend | mehr als 4.700 gesammelte Unit- und Contract-Tests |
| Frontend | mehr als 180 Testdateien |
| E2E | 20 grüne Szenarien, darunter 6 verpflichtende Kern-Smokes |
| Main Branch | geschützt durch 17 Required Status Checks |
| Produkt-Frontend | Vue-v4-Routen sind die einzige ausgelieferte Oberfläche |
| Betriebsmodell | stabilisierter Single-User-Betrieb, noch keine allgemeine Produktionsfreigabe |

### Release-Pfad

| Version | Ziel | Status |
|---|---|---|
| `0.8.0` | funktionsfähige Technical Preview | abgeschlossen |
| `0.9.x` | Stabilisierung, Security- und Readiness-Gates | aktuell |
| `0.10.0` | reproduzierbare Runs, Replay, Budgets, Backup/Restore | geplant |
| `1.0.0` | stabile Verträge, Referenzlauf und nachgewiesener Produktnutzen | geplant |

Der verifizierte Ist-Zustand steht in [`docs/STATUS.md`](./docs/STATUS.md). Die verbindlichen nächsten Schritte stehen in [`ROADMAP.md`](./ROADMAP.md).

---

## ⚠️ Grenzen und verantwortungsvolle Nutzung

- **Personas sind simuliert.** Ihre Aussagen sind keine echten Kunden- oder Bürgermeinungen.
- **Confidence ist keine Wahrheitsskala.** Der Wert beschreibt die interne Evidenzbindung eines Claims.
- **Inputs bestimmen die Ergebnisse.** Datenqualität, Prompt, Modell und Seed können den Lauf erheblich verändern.
- **Ein Run ist keine Stichprobe.** Für belastbarere Aussagen sind mehrere Varianten und externe Reviews nötig.
- **Kleine Modelle sparen Kosten, reduzieren aber häufig die Qualität.** Besonders strukturierte Ausgaben und Evidenzzuordnung leiden.
- **Cloud-Provider erzeugen Datenschutz- und Kostenrisiken.** Datenflüsse und Auftragsverarbeitung müssen vorab geprüft werden.

Agora ist am nützlichsten als **Entscheidungsunterstützung vor realen Interviews, Fachreviews, Nutzertests oder Pilotprojekten**.

---

## 🔒 Sicherheit

- API-Zugriff über `AGORA_AUTH_TOKEN`
- zeitlich begrenzte, signierte Tickets für SSE und Downloads
- Secrets werden nicht in Reports, Logs oder Graphobjekte serialisiert
- HTTPS-Pflicht für credential-behaftete LLM- und Embedding-Endpunkte
- empfohlener Betrieb im lokalen Netz, über VPN oder hinter einem Reverse Proxy

Weitere Dokumentation:

- [`SECURITY.md`](./SECURITY.md)
- [`docs/security-hardening.md`](./docs/security-hardening.md)
- [`docs/dependency-risk-register.md`](./docs/dependency-risk-register.md)

---

## 🤝 Projekt unterstützen

Agora befindet sich zwischen funktionsfähiger Stability Beta und einer belastbaren Version 1.0. Besonders aufwendig sind wiederholte LLM-Läufe, Hardware für lokale Modelle, reproduzierbare Referenzsimulationen und fachliche Evaluationen.

Gesucht werden:

- **Forschungs- und Evaluationspartner**, die Multi-Agenten-Ergebnisse methodisch prüfen,
- **Compute- und Hardware-Sponsoren** für wiederholbare lokale Modellläufe,
- **Pilotpartner** mit echten, dokumentierten Stakeholder-Fragestellungen,
- **Open-Source-Mitwirkende** for Testing, UX, Security und Release Engineering,
- **Förder- und Kooperationspartner** für den Weg zu Version 1.0.

Kontakt und Mitarbeit:

- [GitHub Issues](https://github.com/arn0ld87/agora/issues)
- [Projektseite des Entwicklers](https://alexle135.de)
- [`AGENTS.md`](./AGENTS.md) für agentische Entwicklungsworkflows
- [`CLAUDE.md`](./CLAUDE.md) für Claude-Code-Aufgaben

---

<div align="center">

### ⚖️ Lizenz und Herkunft

Agora ist Open Source unter der **AGPL-3.0 Lizenz** ([`LICENSE`](./LICENSE)).  
Im März 2026 als Fork von [MiroFish](https://github.com/666ghj/MiroFish) (AGPL-3.0) entstanden, seit April 2026 eigenständig weiterentwickelt für professionelle DACH-Simulationen — Einzelheiten in [`NOTICE`](./NOTICE).  
Teile der Simulationslaufzeit basieren auf dem *CAMEL-AI-/OASIS-Ökosystem*.

*Entwickelt von [Alexander Schneider](https://alexle135.de)*

</div>