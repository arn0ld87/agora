# Agora / MiroFish-Offline — Priorisiertes Refactoring-Backlog

**Stand:** 2026-04-22  
**Basisdokument:** `docu/2026-04-22-refactoring-produkt-audit.md`  
**Ziel:** Aus dem Audit ein operativ umsetzbares Backlog mit Prioritäten, Epics, Stories, technischen Aufgaben, Abhängigkeiten und Akzeptanzkriterien ableiten.

---

## 1. Arbeitsweise für dieses Backlog

### Prioritäten
- **P0** = sofort, blockiert sauberes Weiterentwickeln
- **P1** = sehr wichtig, direkt nach P0
- **P2** = sinnvoll mittelfristig
- **P3** = strategisch / später

### Aufwand
- **XS** = 0.5–1 Tag
- **S** = 1–2 Tage
- **M** = 2–4 Tage
- **L** = 4–7 Tage
- **XL** = 1–2 Wochen

### Typen
- **Epic** = größeres Ziel / Themenblock
- **Story** = fachlich oder produktnah formuliertes Arbeitspaket
- **Task** = konkrete technische Umsetzung
- **Spike** = Untersuchung / Entscheidungsfindung

### Empfohlene Umsetzungsregel
1. **Erst P0 abschließen**
2. dann **P1 in Blöcken**
3. erst danach neue größere Features

---

## 2. Gesamt-Priorisierung

## P0 — zuerst umsetzen
1. Qualitäts-Gates (CI, Lint, Test-Grundlage)
2. `backend/app/api/simulation.py` aufspalten
3. gemeinsames Frontend-Workspace-Layout einführen
4. `frontend/src/components/GraphPanel.vue` zerlegen
5. Polling-Grundlogik zentralisieren
6. erste Testabdeckung für Kern-States und Repositories

## P1 — direkt danach
1. `report_agent.py` modularisieren
2. Simulationszustände und Persistenz konsolidieren
3. `Step2EnvSetup.vue` und `Step4Report.vue` zerlegen
4. standardisierte API-Fehler- und Response-Modelle
5. Graph-/Storage-Layer weiter schneiden

## P2 — mittelfristig
1. Branch Compare
2. Run Dashboard
3. Persona Review Flow
4. TypeScript für API-Modelle und Composables
5. Contract-Tests Backend ↔ Frontend

## P3 — strategisch
1. Graph Diff vor/nach Simulation
2. Evidence-/Confidence-Scoring
3. Export Center
4. WebSocket/SSE Live Updates
5. Replay / Reproduce Run

---

## 3. Epic-Übersicht

| Epic-ID | Titel | Priorität | Ziel |
|---|---|---:|---|
| EPIC-01 | Engineering Quality Foundation | P0 | sichere Refactoring-Basis |
| EPIC-02 | Simulation API Decomposition | P0 | monolithische API-Datei aufbrechen |
| EPIC-03 | Frontend Workspace Consolidation | P0 | duplizierte Views/Layout reduzieren |
| EPIC-04 | Graph UI Modularization | P0 | D3-/Graph-UI beherrschbar machen |
| EPIC-05 | Unified Polling and Async State | P0 | Polling und Statuslogik zentralisieren |
| EPIC-06 | Simulation Domain Cleanup | P1 | Status, Persistenz, Services bereinigen |
| EPIC-07 | Report Engine Modularization | P1 | Report-Subsystem modularisieren |
| EPIC-08 | Graph/Storage Refactor | P1 | Storage/DTO/Search schärfen |
| EPIC-09 | API Contracts and Error Standards | P1 | Response-Konsistenz |
| EPIC-10 | Test Expansion Program | P1 | Abdeckung für Kernpfade |
| EPIC-11 | Run Dashboard | P2 | operative Transparenz |
| EPIC-12 | Scenario Branch Compare | P2 | Branching produktiv nutzbar machen |
| EPIC-13 | Persona Review & Approval | P2 | bessere Kontrolle vor Simulation |
| EPIC-14 | Type Safety Upgrade | P2 | schrittweise Typisierung |
| EPIC-15 | Graph Diff & Confidence Layer | P3 | tiefere Analytik |

---

## 4. Detailliertes Backlog nach Epics

# EPIC-01 — Engineering Quality Foundation

**Priorität:** P0  
**Nutzen:** Ohne Qualitäts-Gates wird jedes größere Refactoring riskant.

## Story EPIC-01-ST-01 — CI-Grundpipeline einführen
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** M

**User Story**  
Als Maintainer möchte ich bei jedem Commit und jeder PR automatische Qualitätsprüfungen haben, damit Regressionen früh sichtbar werden.

**Akzeptanzkriterien**
- GitHub Action läuft bei Push/PR
- Backend-Tests werden ausgeführt
- Frontend-Build wird ausgeführt
- Pipeline scheitert bei Fehlern zuverlässig

### Tasks
- [ ] `/.github/workflows/ci.yml` anlegen
- [ ] Backend-Job mit `cd backend && uv run pytest`
- [ ] Frontend-Job mit `cd frontend && npm run build`
- [ ] Root-Readme/Docs um Qualitätsbefehle ergänzen

---

## Story EPIC-01-ST-02 — Python-Linting einführen
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** S

**User Story**  
Als Entwickler möchte ich statische Qualitätschecks für Python haben, damit Stil- und einfache Fehler früh auffallen.

**Akzeptanzkriterien**
- `ruff` ist in `backend/pyproject.toml` integriert
- lokaler Befehl für Lint vorhanden
- CI prüft Python-Lint

### Tasks
- [ ] `ruff` zu Dev-Dependencies hinzufügen
- [ ] `pyproject.toml` konfigurieren
- [ ] Dokumentation für `uv run ruff check` ergänzen
- [ ] CI-Job erweitern

---

## Story EPIC-01-ST-03 — Frontend-Linting vorbereiten
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** M

**User Story**  
Als Entwickler möchte ich Vue/JS-Linting haben, damit die Frontend-Struktur konsistent bleibt.

**Akzeptanzkriterien**
- ESLint läuft lokal
- `.vue`-Dateien werden geprüft
- CI enthält Frontend-Lint

### Tasks
- [ ] ESLint + Vue-Plugin installieren
- [ ] `frontend/package.json` um `lint` ergänzen
- [ ] Basisregeln für Composition API definieren
- [ ] Lint in CI aufnehmen

---

## Story EPIC-01-ST-04 — Root Quality Scripts standardisieren
**Typ:** Task  
**Priorität:** P0  
**Aufwand:** S

**Akzeptanzkriterien**
- Root `package.json` enthält klare Quality-Kommandos
- Entwickler müssen Befehle nicht erraten

### Tasks
- [ ] `npm run test:backend`
- [ ] `npm run lint:backend`
- [ ] `npm run build:frontend`
- [ ] optional `npm run check`

---

# EPIC-02 — Simulation API Decomposition

**Priorität:** P0  
**Nutzen:** Der größte monolithische Backend-Hotspot wird beherrschbar.

## Story EPIC-02-ST-01 — API-Splitting-Plan definieren
**Typ:** Spike  
**Priorität:** P0  
**Aufwand:** S

**User Story**  
Als Maintainer möchte ich vor dem Split eine stabile Modulgrenze festlegen, damit beim Umbau keine Route verloren geht.

**Akzeptanzkriterien**
- alle 39 Routen sind einer Ziel-Datei zugeordnet
- Import-/Blueprint-Strategie ist dokumentiert

### Tasks
- [ ] Route-Inventar aus `backend/app/api/simulation.py` erstellen
- [ ] Zielmodule definieren
- [ ] gemeinsame Helfer identifizieren

---

## Story EPIC-02-ST-02 — Lifecycle-Routen extrahieren
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** M

**Scope**
- `create_simulation`
- `get_simulation`
- `list_simulations`

**Akzeptanzkriterien**
- Verhalten unverändert
- Datei `simulation.py` wird spürbar kleiner
- vorhandene Endpunkte funktionieren weiter

---

## Story EPIC-02-ST-03 — Prepare-Routen extrahieren
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** L

**Scope**
- `prepare_simulation`
- `get_prepare_status`
- vorbereitungsnahe Helper

**Akzeptanzkriterien**
- Prepare-Flow bleibt kompatibel
- Status-/Task-Handling ist nicht dupliziert

---

## Story EPIC-02-ST-04 — Run-Control-Routen extrahieren
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** L

**Scope**
- `start_simulation`
- `stop_simulation`
- `pause_simulation`
- `resume_simulation`
- Run-Status-Endpunkte

**Akzeptanzkriterien**
- Start/Stop/Pause/Resume verhalten sich unverändert
- RunRegistry-Updates sind zentralisiert

---

## Story EPIC-02-ST-05 — Profiles/Interviews/Artifacts/Branches extrahieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** XL

**Akzeptanzkriterien**
- Domänen logisch getrennt
- pro Modul klare Verantwortlichkeit
- keine API-Datei > 600 LOC

---

# EPIC-03 — Frontend Workspace Consolidation

**Priorität:** P0  
**Nutzen:** Weniger Duplication, konsistentere UX, schnellere Änderungen.

## Story EPIC-03-ST-01 — Gemeinsames WorkspaceLayout bauen — **abgeschlossen**
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** M  
**Status:** ✅ done (alle 5 Pipeline-Views nutzen `WorkspaceLayout`/`WorkspaceHeader`/`WorkspaceSplit`/`WorkspaceBrandLink`/`WorkspaceModeSwitch`/`WorkspaceStepStatus`).

**User Story**  
Als Entwickler möchte ich ein gemeinsames Layout für die Pipeline-Views, damit Header, Statusanzeige und Split-Logik nur einmal gepflegt werden müssen.

**Akzeptanzkriterien**
- ✅ `MainView.vue`, `SimulationView.vue`, `SimulationRunView.vue`, `ReportView.vue`, `InteractionView.vue` verwenden dieselbe Layout-Shell
- ✅ View-spezifische Logik bleibt in den Views
- ✅ UX bleibt gleich oder wird konsistenter

### Tasks
- [x] `frontend/src/layouts/WorkspaceLayout.vue` anlegen
- [x] `WorkspaceHeader.vue` anlegen
- [x] `WorkspaceSplit.vue` anlegen
- [x] erste View migrieren
- [x] restliche Views migrieren

---

## Story EPIC-03-ST-02 — Status-/Header-Konfiguration declarative machen
**Typ:** Task  
**Priorität:** P0  
**Aufwand:** S  
**Status:** offen — Layout-Komponenten konsumieren bereits Slots/Props, aber alle 5 Views halten weiterhin eigene `currentStatus`/`statusKind`/`statusText`-Computed mit nahezu identischer Logik. Geplant: ein `useWorkspaceStatus`-Composable mit konfigurierbarem Status-Mapping.

**Akzeptanzkriterien**
- Views liefern nur Props/Config statt eigenes Header-Markup
- Statusformatierung konsistent

---

## Story EPIC-03-ST-03 — ViewMode-Logik zentralisieren
**Typ:** Task  
**Priorität:** P1  
**Aufwand:** S  
**Status:** offen — `viewMode` + `leftPanelStyle`/`rightPanelStyle`/`toggleMaximize` sind in allen 5 Views identisch dupliziert (~12 Zeilen je Datei). Geplant: `useWorkspaceMode(initialMode)`-Composable.

**Akzeptanzkriterien**
- `graph/split/workbench`-Logik lebt nicht mehr in fünf Views separat

---

# EPIC-04 — Graph UI Modularization

**Priorität:** P0  
**Nutzen:** Größter Frontend-Rendering-Hotspot wird wartbar.

## Story EPIC-04-ST-01 — GraphPanel in Unterkomponenten aufteilen
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** XL

**Zielstruktur**
- `GraphCanvas.vue`
- `GraphLegend.vue`
- `GraphDetailPanel.vue`
- `GraphToolbar.vue`
- `GraphHints.vue`

**Akzeptanzkriterien**
- `GraphPanel.vue` wird primär Kompositionsdatei
- D3-Rendering ist nicht direkt mit Detailpanel/Hint-Logik vermischt

---

## Story EPIC-04-ST-02 — D3-Logik in Composable extrahieren
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** L

**User Story**  
Als Entwickler möchte ich das Graph-Rendering aus der UI-Datei herauslösen, damit die Render-Logik separat test- und wartbar wird.

**Akzeptanzkriterien**
- `useD3Graph.js` oder ähnliches existiert
- Resize, Re-Render und Selection laufen über klar definierte Schnittstellen

---

## Story EPIC-04-ST-03 — Graph-DTO-Normalisierung im Frontend
**Typ:** Task  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- UI arbeitet mit stabilen Node-/Edge-ViewModels
- Legacy-Feldaliasse sind in einem Mapper gekapselt

---

# EPIC-05 — Unified Polling and Async State

**Priorität:** P0  
**Nutzen:** Weniger Boilerplate, weniger Leaks, stabileres UI-Verhalten.

## Story EPIC-05-ST-01 — generisches `usePolling` einführen
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** S

**Akzeptanzkriterien**
- Start/Stop/Cleanup zentral geregelt
- Komponenten definieren nur callback + interval

---

## Story EPIC-05-ST-02 — `useTaskPolling` für Graph/Prepare-Tasks
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** S

**Akzeptanzkriterien**
- Graph Build und Prepare nutzen denselben Polling-Mechanismus
- Cleanup bei Unmount sauber

---

## Story EPIC-05-ST-03 — `useIncrementalLogPolling` einführen
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** M

**Scope**
- Simulation Console Logs
- Report Agent Logs
- Report Console Logs

**Akzeptanzkriterien**
- Log-Zeilenstand wird sauber verwaltet
- keine duplizierte Scroll-/Append-Logik

---

## Story EPIC-05-ST-04 — SSE/WebSocket-Strategie untersuchen
**Typ:** Spike  
**Priorität:** P2  
**Aufwand:** S

---

# EPIC-06 — Simulation Domain Cleanup

**Priorität:** P1  
**Nutzen:** Fachlogik, Persistenz und Zustände werden klarer.

## Story EPIC-06-ST-01 — SimulationRepository einführen
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- `SimulationManager` liest/schreibt JSON nicht mehr direkt überall selbst
- `state.json`-Zugriffe kapsuliert

### Tasks
- [ ] Repository für Laden/Speichern anlegen
- [ ] Manager auf Repository umstellen
- [ ] File-Pfade zentralisieren

---

## Story EPIC-06-ST-02 — Statusübergänge formalisieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- erlaubte Transitionen zentral definiert
- verbotene Transitionen geben klaren Fehler zurück
- Tests decken Hauptübergänge ab

---

## Story EPIC-06-ST-03 — Prepare-Service extrahieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** L

**Scope**
- Entity-Read
- Persona-Generierung
- Config-Generierung
- Dateiausgabe

**Akzeptanzkriterien**
- `SimulationManager` wird orchestratorischer und kleiner

---

## Story EPIC-06-ST-04 — Branching-Service extrahieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- Branch-Logik in eigener Service-Datei
- Persona-Override-Logik separat testbar

---

# EPIC-07 — Report Engine Modularization

**Priorität:** P1  
**Nutzen:** Größter intelligenter Kern wird änderbar ohne Chaos.

## Story EPIC-07-ST-01 — Report-Models extrahieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- `Report`, `ReportSection`, `ReportOutline`, `ReportStatus` leben in `models.py`
- Modellklassen sind unabhängig von Tool-/Prompt-Code

---

## Story EPIC-07-ST-02 — Report-Logging trennen
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** S

**Akzeptanzkriterien**
- Logger-Klassen in eigener Datei
- Agent-Core enthält keine lange Logging-Implementierung mehr

---

## Story EPIC-07-ST-03 — Tool-Schema und Tool-Execution trennen
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- Tool-Beschreibung separat
- Tool-Ausführung separat
- Tool-Validation separat testbar

---

## Story EPIC-07-ST-04 — Prompt-Building modularisieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Akzeptanzkriterien**
- Planung, Sections, Chat und Reflection haben getrennte Prompt-Bausteine

---

## Story EPIC-07-ST-05 — Evidence-Layer explizit modellieren
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

---

# EPIC-08 — Graph/Storage Refactor

**Priorität:** P1  
**Nutzen:** bessere Trennung von Extraktion, Persistenz und DTO-Mapping.

## Story EPIC-08-ST-01 — `Neo4jStorage` in Read/Write/Search schneiden
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** L

**Akzeptanzkriterien**
- Schreiblogik, Leselogik und Suche liegen nicht mehr in einer Datei
- Mappings sind zentral wiederverwendbar

---

## Story EPIC-08-ST-02 — Ingestion-Pipeline in Schritte zerlegen
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** L

**Akzeptanzkriterien**
- `add_text()` ist nicht mehr ein großer Block
- NER / Embedding / Persistenz getrennt

---

## Story EPIC-08-ST-03 — Frontend-taugliche Graph-DTOs definieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

---

# EPIC-09 — API Contracts and Error Standards

**Priorität:** P1

## Story EPIC-09-ST-01 — Einheitliches Fehlerformat definieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** S

**Akzeptanzkriterien**
- definierte Fehlerstruktur für 4xx/5xx
- Frontend kann Fehler konsistent anzeigen

---

## Story EPIC-09-ST-02 — Response-Schemas für Kern-Endpoints definieren
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

**Scope**
- Project
- Simulation
- RunStatus
- ReportStatus
- GraphData

---

## Story EPIC-09-ST-03 — Frontend-Mapper für Backend-Responses einführen
**Typ:** Task  
**Priorität:** P1  
**Aufwand:** M

---

# EPIC-10 — Test Expansion Program

**Priorität:** P1  
**Nutzen:** Refactoring ohne Blindflug.

## Story EPIC-10-ST-01 — Tests für `RunRegistry`
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** S

**Akzeptanzkriterien**
- create/update/list/get_latest_by_linked_id getestet
- Statusnormalisierung getestet

---

## Story EPIC-10-ST-02 — Tests für `ProjectManager`
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** S

**Akzeptanzkriterien**
- create/save/load/delete getestet
- File-Save-Sicherheitslogik getestet

---

## Story EPIC-10-ST-03 — Tests für `validation.py`
**Typ:** Story  
**Priorität:** P0  
**Aufwand:** XS

---

## Story EPIC-10-ST-04 — Tests für Simulation-State-Transitionen
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

---

## Story EPIC-10-ST-05 — Flask API Smoke Tests
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

---

## Story EPIC-10-ST-06 — Frontend Vitest Setup
**Typ:** Story  
**Priorität:** P1  
**Aufwand:** M

---

# EPIC-11 — Run Dashboard

**Priorität:** P2  
**Nutzen:** Große operative Verbesserung für Nutzer und Debugging.

## Story EPIC-11-ST-01 — Runs API evaluieren und ergänzen
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

## Story EPIC-11-ST-02 — Dashboard-View für Runs bauen
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** L

## Story EPIC-11-ST-03 — Resume/Restart-Aktionen aus UI
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

---

# EPIC-12 — Scenario Branch Compare

**Priorität:** P2  
**Nutzen:** Branching wird zu echtem Analysefeature.

## Story EPIC-12-ST-01 — Vergleichsmodell definieren
**Typ:** Spike  
**Priorität:** P2  
**Aufwand:** S

## Story EPIC-12-ST-02 — Compare API für Kernmetriken
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** L

## Story EPIC-12-ST-03 — Compare UI für zwei Branches
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** L

---

# EPIC-13 — Persona Review & Approval

**Priorität:** P2

## Story EPIC-13-ST-01 — Persona Review UI
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

## Story EPIC-13-ST-02 — Persona Diff gegen Entity-Kontext
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

## Story EPIC-13-ST-03 — Approve / Reject / Regenerate Workflow
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** L

---

# EPIC-14 — Type Safety Upgrade

**Priorität:** P2

## Story EPIC-14-ST-01 — Frontend API-Modelle in TypeScript
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** M

## Story EPIC-14-ST-02 — Composables zuerst migrieren
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** L

## Story EPIC-14-ST-03 — Kritische Features schrittweise migrieren
**Typ:** Story  
**Priorität:** P2  
**Aufwand:** XL

---

# EPIC-15 — Graph Diff & Confidence Layer

**Priorität:** P3

## Story EPIC-15-ST-01 — Graph Diff Modell und API
**Typ:** Story  
**Priorität:** P3  
**Aufwand:** L

## Story EPIC-15-ST-02 — Report Confidence Score
**Typ:** Story  
**Priorität:** P3  
**Aufwand:** M

## Story EPIC-15-ST-03 — UI für Diff und Confidence
**Typ:** Story  
**Priorität:** P3  
**Aufwand:** L

---

## 5. Empfohlene Sprint-Zuschnitte

## Sprint A — Refactoring-Sicherheit (P0)
**Ziel:** Qualitätsnetz und erste Strukturverbesserungen.

### Enthalten
- EPIC-01-ST-01
- EPIC-01-ST-02
- EPIC-01-ST-03
- EPIC-01-ST-04
- EPIC-10-ST-01
- EPIC-10-ST-02
- EPIC-10-ST-03

### Ergebnis
- CI vorhanden
- Linting vorhanden
- erste Tests vorhanden
- Refactoring kann sicherer beginnen

---

## Sprint B — Backend entmonolithisieren
**Ziel:** `simulation.py` beherrschbar machen.

### Enthalten
- EPIC-02-ST-01
- EPIC-02-ST-02
- EPIC-02-ST-03
- EPIC-02-ST-04

### Ergebnis
- API logischer geschnitten
- weniger Seiteneffekte
- bessere Testbarkeit

---

## Sprint C — Frontend-Shell und Graph stabilisieren
**Ziel:** größte UI-Wiederholungen und Graph-Hotspots entschärfen.

### Enthalten
- EPIC-03-ST-01
- EPIC-03-ST-02
- EPIC-04-ST-01
- EPIC-04-ST-02
- EPIC-05-ST-01
- EPIC-05-ST-02

### Ergebnis
- gemeinsame Workspace-Struktur
- Graph-Feature modularer
- weniger doppeltes Polling

---

## Sprint D — Report und Simulation Domain Cleanup
**Ziel:** größte Service-Hotspots fachlich schneiden.

### Enthalten
- EPIC-06-ST-01
- EPIC-06-ST-02
- EPIC-06-ST-03
- EPIC-07-ST-01
- EPIC-07-ST-02
- EPIC-07-ST-03

---

## Sprint E — Produktverbesserungen mit hohem Nutzen
**Ziel:** sichtbarer Mehrwert nach Strukturarbeit.

### Enthalten
- EPIC-11-ST-01
- EPIC-11-ST-02
- EPIC-12-ST-01
- EPIC-12-ST-02
- EPIC-13-ST-01

---

## 6. Kritische Abhängigkeiten

| Von | Nach | Grund |
|---|---|---|
| EPIC-01 | alle anderen | Qualitätssicherung zuerst |
| EPIC-02 | EPIC-06 / EPIC-09 | erst API schneiden, dann sauber standardisieren |
| EPIC-03 | EPIC-04 / EPIC-05 | Layout-Konsolidierung erleichtert Modulbau |
| EPIC-05 | EPIC-11 | Run Dashboard profitiert von zentralem Async-State |
| EPIC-06 | EPIC-12 | Branch Compare braucht saubere Simulationsdomäne |
| EPIC-07 | EPIC-15 | Confidence/Evidence nur sinnvoll bei modularer Report-Engine |
| EPIC-09 | EPIC-14 | Typisierung braucht stabile Contracts |

---

## 7. Definition of Done für Backlog-Items

Ein Item gilt nur als fertig, wenn:

- [ ] Code strukturell umgesetzt ist
- [ ] relevante Tests ergänzt/angepasst wurden
- [ ] bestehende Verifikation läuft
- [ ] Dokumentation aktualisiert wurde, falls nötig
- [ ] keine neue Datei unnötig monolithisch geworden ist
- [ ] bei Frontend-Items Cleanup von Polling/Unmount mitgedacht wurde

---

## 8. Sofort startbares Mini-Backlog

Wenn du **jetzt direkt mit Umsetzung starten** willst, würde ich genau diese Reihenfolge nehmen:

### Ticket 1
**EPIC-01-ST-01 — CI-Grundpipeline einführen**

### Ticket 2
**EPIC-10-ST-01 — Tests für `RunRegistry`**

### Ticket 3
**EPIC-10-ST-02 — Tests für `ProjectManager`**

### Ticket 4
**EPIC-02-ST-01 — API-Splitting-Plan definieren**

### Ticket 5
**EPIC-02-ST-02 — Lifecycle-Routen aus `simulation.py` extrahieren**

### Ticket 6
**EPIC-03-ST-01 — `WorkspaceLayout.vue` einführen**

### Ticket 7
**EPIC-04-ST-01 — `GraphPanel.vue` zerlegen**

---

## 9. Empfehlung für die praktische Umsetzung

### Wenn Fokus auf Stabilität liegt
Reihenfolge:
1. EPIC-01
2. EPIC-10
3. EPIC-02
4. EPIC-06
5. EPIC-07

### Wenn Fokus auf sichtbarer UX-Verbesserung liegt
Reihenfolge:
1. EPIC-03
2. EPIC-04
3. EPIC-05
4. EPIC-11
5. EPIC-12

### Wenn Fokus auf Produktreife liegt
Reihenfolge:
1. EPIC-01
2. EPIC-02
3. EPIC-03
4. EPIC-07
5. EPIC-11
6. EPIC-12
7. EPIC-13

---

## 10. Abschluss

Dieses Backlog ist absichtlich so geschrieben, dass es sofort weiterverwendet werden kann für:
- GitHub Issues
- Sprint Planning
- Milestones
- ADR-basierte Refactoring-Reihenfolge
- technische Roadmap

Der wichtigste operative Grundsatz bleibt:

> **Nicht erst neue große Features bauen, solange die größten Struktur-Hotspots ungebremst wachsen.**

Darum ist die empfohlene Startreihenfolge klar:

1. **Quality Foundation**
2. **Simulation API Split**
3. **Workspace + Graph UI Cleanup**
4. **Simulation/Report Domain Cleanup**
5. **erst dann größere neue Analysefeatures**
