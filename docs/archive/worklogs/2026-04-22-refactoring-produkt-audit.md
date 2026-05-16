# Agora / MiroFish-Offline — Refactoring-, Qualitäts- und Feature-Audit

**Datum:** 2026-04-22  
**Repository:** `/mnt/brain/Projekte/MiroFish-Offline`  
**Ziel:** Sehr genauer, kleinteiliger Refactoring-Plan für das gesamte Produkt inklusive Verbesserungs- und Feature-Vorschlägen.

---

## 1. Kurzfazit

Das Produkt hat bereits eine **brauchbare Zielarchitektur** und klare fachliche Pipeline:

1. Dokument-Upload / Ontology-Generierung
2. Graph-Build in Neo4j
3. Persona- und Simulations-Setup
4. OASIS-Simulation im Subprozess
5. Report-Generierung
6. Interaktion / Interviews

Die **größten Probleme** liegen aktuell nicht in der Produktidee, sondern in der **Code-Struktur, Wartbarkeit und Testbarkeit**:

- mehrere **monolithische Backend-Dateien**
- mehrere **übergroße Vue-Komponenten** mit gemischter Zuständigkeit
- **duplizierte View-Layouts** und wiederholte Polling-Logik
- **zu wenig Tests**
- **keine durchgehende Qualitäts-Pipeline** für Linting/Typing/Frontend-Tests
- fachliche Zustände werden gleichzeitig in **JSON-Dateien, In-Memory-Objekten und Run-Registry** gehalten

Wenn das Produkt weiter wachsen soll, ist jetzt der richtige Zeitpunkt für ein **strukturiertes Refactoring in Phasen**, statt weiter Features auf die bestehende Struktur zu stapeln.

---

## 2. Analysebasis

Diese Einschätzung basiert auf einer Codeanalyse der zentralen Backend-, Frontend- und Infrastrukturdateien.

### 2.1 Gelesene Kernbereiche

#### Backend
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/api/graph.py`
- `backend/app/api/simulation.py`
- `backend/app/api/report.py`
- `backend/app/services/graph_builder.py`
- `backend/app/services/simulation_manager.py`
- `backend/app/services/simulation_runner.py`
- `backend/app/services/report_agent.py`
- `backend/app/services/graph_tools.py`
- `backend/app/services/simulation_config_generator.py`
- `backend/app/services/oasis_profile_generator.py`
- `backend/app/storage/neo4j_storage.py`
- `backend/app/storage/search_service.py`
- `backend/app/utils/llm_client.py`
- `backend/app/utils/file_parser.py`
- `backend/app/utils/auth.py`
- `backend/app/services/run_registry.py`
- `backend/app/models/project.py`
- `backend/app/models/task.py`

#### Frontend
- `frontend/src/views/Home.vue`
- `frontend/src/views/MainView.vue`
- `frontend/src/views/SimulationView.vue`
- `frontend/src/views/SimulationRunView.vue`
- `frontend/src/views/ReportView.vue`
- `frontend/src/views/InteractionView.vue`
- `frontend/src/views/Process.vue`
- `frontend/src/components/GraphPanel.vue`
- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step3Simulation.vue`
- `frontend/src/components/Step4Report.vue`
- `frontend/src/components/Step5Interaction.vue`
- `frontend/src/api/index.js`
- `frontend/src/api/report.js`
- `frontend/src/api/simulation.js`
- `frontend/src/store/pendingUpload.js`
- `frontend/src/router/index.js`
- `frontend/vite.config.js`

#### Qualität / Infra / Tests
- `package.json`
- `frontend/package.json`
- `backend/pyproject.toml`
- `docker-compose.yml`
- `.github/workflows/docker-image.yml`
- `backend/tests/test_gpu_probe.py`
- `backend/tests/test_simulation_runtime.py`
- `docs/graphrag-speedup.md`

### 2.2 Struktur- und Größenbefunde

#### Größte Backend-Dateien
- `backend/app/api/simulation.py` → **3251 LOC**
- `backend/app/services/report_agent.py` → **2876 LOC**
- `backend/app/services/simulation_runner.py` → **1840 LOC**
- `backend/app/services/graph_tools.py` → **1496 LOC**
- `backend/app/services/oasis_profile_generator.py` → **1319 LOC**
- `backend/app/services/simulation_config_generator.py` → **1050 LOC**

#### Größte Frontend-Dateien
- `frontend/src/views/Process.vue` → **2060 LOC**
- `frontend/src/components/GraphPanel.vue` → **1433 LOC**
- `frontend/src/components/Step2EnvSetup.vue` → **1146 LOC**
- `frontend/src/components/Step4Report.vue` → **1020 LOC**
- `frontend/src/views/Home.vue` → **758 LOC**

#### API-Oberfläche
- `graph.py` → **10 Routen**
- `simulation.py` → **39 Routen**
- `report.py` → **21 Routen**
- `runs.py` → **5 Routen**
- Summe zentrale API-Routen → **75**

#### Testlage
- Backend-Tests gefunden: **2**
- Frontend-Tests gefunden: **0**
- Lint/Typecheck-Scripts im Frontend: **nicht vorhanden**
- CI-Workflow für Build/Test/Lint: **nicht vorhanden**
- Vorhandener GitHub-Workflow: **nur Docker Image Build/Push**

---

## 3. Positives, das erhalten bleiben sollte

Bevor refactored wird: Es gibt etliche gute Grundlagen, die **nicht zerstört**, sondern ausgebaut werden sollten.

### 3.1 Gute Architekturansätze
- Flask läuft bereits als **Application Factory** (`backend/app/__init__.py`)
- Neo4j wird per **DI über `app.extensions['neo4j_storage']`** eingebunden
- Run-Zustände werden zusätzlich in einer **persistenten RunRegistry** gehalten
- Die Produktpipeline ist fachlich klar voneinander abgrenzbar
- Graph-Build wurde bereits sinnvoll parallelisiert
- Sicherheitsverbesserungen wie Token-Auth und Label-Sanitizing sind vorhanden
- Die Frontend-UX hat eine erkennbare Produkthandschrift statt generischem CRUD-Look

### 3.2 Gute technische Entscheidungen
- `execute_read` / `execute_write`-artige Neo4j-Patterns werden genutzt
- OpenAI-kompatibler LLM-Client reduziert Provider-Kopplung
- Dateibasierte Persistenz macht das Produkt lokal und offline-nah nutzbar
- Report-/Simulation-Laufartefakte sind für Debugging grundsätzlich gut greifbar

### 3.3 Gute Produktstärken
- Branching von Simulationen ist bereits ein starkes Feature
- Graph, Simulation, Report und Interview bilden zusammen einen echten Workflow
- Report-Evidence ist ein guter Ansatz für Nachvollziehbarkeit

---

## 4. Hauptprobleme im aktuellen Zustand

## 4.1 Backend: Monolithische Controller-Dateien

### Problem
`backend/app/api/simulation.py` ist faktisch ein **Mini-Subsystem in einer Datei**.

Dort vermischen sich:
- Request-Validierung
- Business-Logik
- Dateizugriffe
- Run-Registry-Updates
- Zustandskorrekturen
- Error-Recovery
- Response-Mapping
- Interview-/Log-/Timeline-Endpunkte

### Auswirkungen
- schwer testbar
- hohes Regressionsrisiko
- neue Entwickler finden Zuständigkeiten schlecht
- Änderungen an einer Stelle brechen leicht andere Endpunkte

### Refactoring-Ziel
`simulation.py` in mehrere Module aufteilen:

- `api/simulation_lifecycle.py`
- `api/simulation_prepare.py`
- `api/simulation_run.py`
- `api/simulation_profiles.py`
- `api/simulation_interviews.py`
- `api/simulation_artifacts.py`
- `api/simulation_branches.py`

---

## 4.2 Backend: Services mit zu vielen Verantwortungen

### Besonders kritisch
- `report_agent.py`
- `simulation_runner.py`
- `graph_tools.py`
- `oasis_profile_generator.py`
- `simulation_config_generator.py`

### Beobachtung
Diese Dateien enthalten gleichzeitig:
- Datenmodelle
- Formatierung
- Tool-Definitionen
- Prompting
- Parsing
- Logging
- Dateispeicherung
- Orchestrierung

### Beispiel `report_agent.py`
Dort liegen in einer Datei:
- Logging-Klassen
- Report-/Outline-/Section-Datamodelle
- Agenten-Logik
- Tool-Ausführung
- Parsing von Tool-Calls
- Persistence-nahe Operationen via `ReportManager`

### Refactoring-Ziel
Beispielhafte Zielstruktur:

```text
backend/app/services/report/
  models.py
  logger.py
  tool_schema.py
  tool_executor.py
  prompt_builder.py
  section_generator.py
  planner.py
  report_agent.py
  report_manager.py
```

Dasselbe Muster gilt für Simulation und Graph-Tools.

---

## 4.3 Zustandsmanagement ist verteilt und teilweise redundant

### Aktueller Zustand
Zustände liegen parallel in:
- `state.json`
- `run_state.json`
- `TaskManager` (in-memory)
- `RunRegistry` (persistiert)
- Projektdateien (`project.json`)
- teils zusätzlich implizit im Dateisystemzustand

### Problem
Mehrere Quellen definieren „Wahrheit“ gleichzeitig.

Beispiele:
- Simulation ist laut `state.json` bereit, aber Run-State sagt etwas anderes
- Task ist im Speicher abgeschlossen, aber nach Restart nicht mehr auflösbar
- RunRegistry und SimulationState können auseinanderlaufen

### Refactoring-Ziel
**Single Source of Truth je Domäne**:

- Projektzustand → `project.json`
- Simulationszustand → `state.json`
- Run-Zustand → `run_registry/<run>.json`
- TaskManager nur noch als **Runtime-Cache**, nicht als primäre Fachpersistenz

Zusätzlich: klare Mapper
- `SimulationStateMapper`
- `ProjectStateMapper`
- `RunManifestMapper`

---

## 4.4 Frontend: Zu große Komponenten mit Mischverantwortung

### Kritische Dateien
- `frontend/src/views/Process.vue`
- `frontend/src/components/GraphPanel.vue`
- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step4Report.vue`
- `frontend/src/components/Step5Interaction.vue`

### Problemtypen
- Rendering + API-Aufrufe + Polling + State + Business-Logik in derselben Datei
- D3-Graph-Logik tief im UI eingebettet
- wiederholte Zeit-/Status-/Logikmuster
- hoher kognitiver Load

### Beispiel `Process.vue`
Enthält zugleich:
- vollständiges Seitenlayout
- D3-Graph-Rendering
- Polling-Logik
- Routing
- Projektinitialisierung
- Graph-Build-Workflow
- Detailpanel-Logik
- Formatierung

Das ist für Wartung zu viel.

### Refactoring-Ziel
Frontend in drei Schichten teilen:

1. **View Shells**
2. **Feature Components**
3. **Composables / Stores / API-Adapter**

Beispiel:

```text
frontend/src/features/graph/
  components/
    GraphCanvas.vue
    GraphLegend.vue
    GraphDetailPanel.vue
    GraphToolbar.vue
  composables/
    useGraphData.js
    useGraphPolling.js
    useD3Graph.js
```

---

## 4.5 Frontend: Wiederholtes Layout in mehreren Views

### Beobachtung
Starke strukturelle Wiederholung zwischen:
- `MainView.vue`
- `SimulationView.vue`
- `SimulationRunView.vue`
- `ReportView.vue`
- `InteractionView.vue`

Zusätzlich haben `MainView.vue` und `SimulationView.vue` bereits **134 gemeinsame nicht-leere Zeilen**.

### Problem
- Layout-Änderungen müssen an 5 Stellen nachgezogen werden
- gleiche Header-/Split-/GraphPanel-Struktur mehrfach gepflegt
- hohes Risiko inkonsistenter UX

### Refactoring-Ziel
Ein gemeinsames Layout-Framework:

```text
frontend/src/layouts/
  WorkspaceLayout.vue
  WorkspaceHeader.vue
  WorkspaceSplit.vue
```

Dann liefern die Views nur noch:
- Titel / Schritt
- Status
- rechte Workbench-Komponente
- optionale Aktionen

---

## 4.6 Polling ist dupliziert und unkoordiniert

### Beobachtung
Polling kommt mehrfach vor in:
- `MainView.vue`
- `Process.vue`
- `Step2EnvSetup.vue`
- `Step3Simulation.vue`
- `Step4Report.vue`
- `SimulationRunView.vue`

### Problem
- uneinheitliche Intervalle
- potenziell unnötige Requests
- schwer stoppbar bei Route-Wechsel
- Fehlerbehandlung nicht zentralisiert

### Refactoring-Ziel
Zentraler Polling-/Job-Mechanismus:

```text
frontend/src/composables/
  usePolling.js
  useTaskPolling.js
  useRunPolling.js
  useIncrementalLogPolling.js
```

Optional mittelfristig:
- SSE oder WebSocket statt Polling

---

## 4.7 Fehlende Typisierung im Frontend

### Beobachtung
Frontend ist rein in `.js` / `.vue` ohne TypeScript.

### Problem
Bei komplexen Response-Payloads ist das riskant, z. B. bei:
- Report-Evidence
- Simulation-Status
- Graph-Edges/Nodes
- Interview-Responses

### Refactoring-Ziel
Schrittweise Migration auf TypeScript:
- zuerst API-Modelle
- dann Composables
- dann kritische Komponenten

Nicht Big Bang, sondern inkrementell.

---

## 4.8 Testabdeckung ist für das Produkt viel zu niedrig

### Ist-Zustand
Nur 2 Backend-Tests:
- `test_gpu_probe.py`
- `test_simulation_runtime.py`

### Fehlend
- API-Tests für Graph/Simulation/Report
- Service-Tests für Parser, Statusübergänge, Registry
- Failure-/Recovery-Tests
- Frontend-Komponententests
- Integrations-/Smoke-Tests

### Risiko
Bei jedem größeren Refactoring ist die Wahrscheinlichkeit hoch, dass Seiteneffekte unbemerkt bleiben.

---

## 4.9 CI/CD ist unvollständig

### Aktueller Zustand
GitHub Actions enthält nur:
- `docker-image.yml`

### Fehlend
- Backend-Testjob
- Frontend-Buildjob
- Lintjob
- Sicherheits-/Dependency-Checks
- schnelle PR-Signale

### Refactoring-Ziel
Mindestens folgende Pipeline:
1. Backend unit tests
2. Frontend build
3. Python lint/format check
4. JS/Vue lint check
5. optional security scan

---

## 4.10 Teilweise Sprach- und Konsistenzbrüche im Code

### Beobachtung
Es gibt gemischte Kommentare / Response-Texte / TODOs in:
- Englisch
- Deutsch
- teils verbliebene chinesische Kommentare / historische Formulierungen

### Problem
- erschwert Wartung
- erschwert Onboarding
- uneinheitliche Fehlermeldungen und Logs

### Ziel
Eine klare Policy:
- **Code-Kommentare und interne Techniktexte:** Englisch
- **UI-Texte:** i18n
- **Benutzernahe Fehlermeldungen:** i18n oder konsistente API-Fehlerobjekte

---

## 5. Zielbild der Refactoring-Architektur

## 5.1 Backend-Zielstruktur

```text
backend/app/
  api/
    graph.py
    report.py
    runs.py
    simulation/
      __init__.py
      lifecycle.py
      prepare.py
      run.py
      profiles.py
      interviews.py
      branches.py
      artifacts.py
  domain/
    projects/
    graphs/
    simulations/
    reports/
  services/
    graph/
    simulation/
    report/
    llm/
  repositories/
    project_repository.py
    simulation_repository.py
    run_repository.py
  schemas/
    requests.py
    responses.py
  utils/
```

### Architekturprinzipien
- API-Schicht bleibt dünn
- Services enthalten Fachlogik
- Repositories kapseln File-/JSON-Persistenz
- Schemas kapseln Input/Output-Validierung
- Run-/Task-Updates über definierte Orchestrierungsdienste

---

## 5.2 Frontend-Zielstruktur

```text
frontend/src/
  api/
  layouts/
  features/
    graph/
    project/
    simulation/
    report/
    interaction/
  composables/
  stores/
  models/
  views/
  components/ui/
```

### Zielprinzipien
- Views = Routing + Zusammenbau
- Features = fachliche UI-Bausteine
- Composables = Zustand, Polling, API-Logik
- Models = gemeinsame Typen / Mappings
- UI-Komponenten bleiben generisch

---

## 6. Kleinteiliger Refactoring-Plan

# Phase 0 — Leitplanken schaffen (sofort)

## Ziel
Refactoring sicher machen, bevor große Umbauten starten.

### Maßnahmen
1. **Dateigrößen-Freeze definieren**
   - keine neuen Dateien > 500 LOC ohne Begründung
   - Zielwert für Views/Controller: < 300–400 LOC

2. **Technische Qualitäts-Scripts ergänzen**
   - Root-Scripts für Test/Lint/Build
   - Frontend-Lint und optional Typecheck vorbereiten
   - Backend-Lint mit `ruff` einführen

3. **CI-Basisworkflow anlegen**
   - `backend pytest`
   - `frontend build`
   - Python-Lint
   - Frontend-Lint

4. **Definition of Done fürs Refactoring festlegen**
   - keine Funktionsänderung ohne Tests
   - neue Module nur mit klarer Ownership
   - kein weiteres Inline-Polling in Komponenten

### Akzeptanzkriterien
- Es gibt einen standardisierten `quality gate`
- PRs schlagen bei offensichtlichen Regressionen fehl
- Team kann gefahrlos in kleinen Schritten umbauen

---

# Phase 1 — Backend-API entflechten

## Ziel
Routen lesbar machen und API-Schicht auf Orchestrierung reduzieren.

### Maßnahmen

#### 1.1 `simulation.py` aufspalten
**Neue Teilbereiche:**
- Lifecycle (`create`, `get`, `list`)
- Prepare (`prepare`, `prepare/status`)
- Run (`start`, `stop`, `pause`, `resume`)
- Profiles (`list`, `realtime`, `add`, `delete`)
- Branches (`create`, `list`)
- Interviews (`interview_*`)
- Artifacts (`config`, `logs`, `timeline`, `actions`, `comments`, `posts`)

#### 1.2 Gemeinsame Helper extrahieren
- Request-Parsing
- ID-Validation
- Error-to-Response-Mapping
- RunRegistry-Updates
- ArtifactLocator-Aufbereitung

#### 1.3 Response-Formate standardisieren
Einheitliches Fehlerformat:

```json
{
  "success": false,
  "error": {
    "code": "simulation_not_ready",
    "message": "Simulation not ready",
    "details": {}
  }
}
```

### Akzeptanzkriterien
- Keine API-Datei > 600 LOC
- Gemeinsame Error- und Validation-Logik nicht mehr kopiert
- Verhalten der Endpunkte bleibt funktional identisch

---

# Phase 2 — Simulationsdomäne sauber schneiden

## Ziel
Simulation als eigenes fachliches System konsolidieren.

### Maßnahmen

#### 2.1 `SimulationManager` reduzieren
Aktuell enthält er:
- Persistenz
- Vorbereitung
- Branching
- Dateioperationen
- Persona-Overrides

**Aufteilen in:**
- `simulation_service.py`
- `simulation_repository.py`
- `simulation_prepare_service.py`
- `simulation_branch_service.py`
- `persona_override_service.py`

#### 2.2 Statusübergänge formal abbilden
Statt verstreuter `if status != READY`-Logik:
- explizite Transition-Funktionen
- erlaubte Zustandsmatrix

Beispiel:
- `created -> preparing`
- `preparing -> ready`
- `ready -> running`
- `running -> paused`
- `paused -> running`
- `running -> completed|failed|stopped`

#### 2.3 Dateibasierte Persistenz kapseln
Keine JSON-Reads/Writes mehr quer verteilt.

### Akzeptanzkriterien
- Statuswechsel sind zentral testbar
- Dateiformate sind an einer Stelle definiert
- Branching ist separater Service statt Seitenast in Manager-Klasse

---

# Phase 3 — Report-Domäne modularisieren

## Ziel
Report-Engine wartbar machen.

### Maßnahmen

#### 3.1 `report_agent.py` in Submodule zerlegen
- `report_models.py`
- `report_logging.py`
- `report_planning.py`
- `report_sections.py`
- `report_tools.py`
- `report_evidence.py`
- `report_manager.py`

#### 3.2 Tool-Definition und Tool-Ausführung trennen
Aktuell liegen Tool-Metadaten, Tool-Call-Validierung und Tool-Execution zu eng beieinander.

#### 3.3 Prompt-Building kapseln
- Outline-Prompt
- Section-Prompt
- Chat-Prompt
- Evidence-Prompt

#### 3.4 Evidence-Modell explizit machen
Eigene Models für:
- Claim
- EvidenceItem
- ToolEvidence
- SectionEvidence

### Akzeptanzkriterien
- ReportAgent ist nur noch Orchestrator
- Tooling, Logging und Persistence sind austauschbar
- gezielte Tests für Planning/Tool-Parsing/Evidence möglich

---

# Phase 4 — Graph- und Search-Domäne vereinfachen

## Ziel
Graph-Layer robuster und besser erweiterbar machen.

### Maßnahmen

#### 4.1 `Neo4jStorage` weiter schneiden
Mögliche Submodule:
- `graph_write_repository.py`
- `graph_read_repository.py`
- `graph_search_repository.py`
- `graph_mapping.py`

#### 4.2 NER-/Embedding-/Neo4j-Pipeline klar trennen
Aktuell liegt in `add_text()` sehr viel in einem Pfad:
- Ontology lesen
- NER
- Relation-Extraktion
- Embeddings
- Node-Merge
- Label-Set
- Relation-Create

Besser:
- `extract_chunk_semantics()`
- `embed_semantics()`
- `persist_semantics()`

#### 4.3 Graph-View-Model für Frontend standardisieren
Frontend sollte nicht mehrere Legacy-/Alias-Felder kennen müssen.

### Akzeptanzkriterien
- Node/Edge-DTOs sind stabil definiert
- Storage enthält weniger orchestration-heavy Methoden
- Such- und Mapping-Logik sind isoliert testbar

---

# Phase 5 — Frontend-Workbench modernisieren

## Ziel
Große Views und Komponenten in wiederverwendbare Feature-Bausteine zerlegen.

### Maßnahmen

#### 5.1 Gemeinsames Workspace-Layout einführen
Für alle 5 Schritte:
- Header
- Step-Badge
- Status-Chip
- Split View
- Graph-Panel-Einbindung

#### 5.2 `GraphPanel.vue` zerlegen
In:
- `GraphCanvas.vue`
- `GraphHintOverlay.vue`
- `GraphDetailPanel.vue`
- `GraphLegend.vue`
- `GraphControls.vue`
- `useD3Graph.js`

#### 5.3 Polling-Composables einführen
- `useTaskPolling`
- `useRunStatusPolling`
- `useIncrementalLogs`
- `useReportStatus`

#### 5.4 Step-Komponenten weiter zerlegen

**Step2EnvSetup**
- ModelSelector
- PersonaList
- PersonaEditor
- PrepareProgress
- SimulationConfigPreview

**Step4Report**
- ReportStatusPanel
- ReportOutlinePanel
- ReportSectionList
- EvidencePanel
- AgentLogPanel
- ReportExportMenu

**Step5Interaction**
- AgentPicker
- ChatPanel
- SurveyPanel
- SurveyResultsTable

### Akzeptanzkriterien
- Keine Feature-Komponente > 400 LOC
- D3-Logik lebt außerhalb der View-Dateien
- Polling und API-State sind composable-basiert

---

# Phase 6 — Typisierung, Tests, Qualitätskultur

## Ziel
Änderungen dauerhaft absichern.

### Maßnahmen

#### 6.1 Frontend-Tests
- Vitest für Composables und Komponentenlogik
- Kernfälle:
  - Polling stoppt korrekt
  - Reportstatus wird korrekt gemappt
  - Survey aggregiert Antworten korrekt
  - GraphPanel reagiert auf Datenänderung sauber

#### 6.2 Backend-Tests
Pflichtblöcke:
- `ProjectManager`
- `SimulationManager` Statuswechsel
- `RunRegistry`
- `validation.py`
- `auth.py`
- `search_service.py`
- kritische API-Endpoints per Flask test client

#### 6.3 Contract-Tests zwischen Frontend und Backend
Wichtig für DTO-Stabilität.

#### 6.4 Typisierung
- Python: schrittweise Typen ergänzen, mypy/pyright optional
- Frontend: TypeScript für API-Modelle / Composables

### Akzeptanzkriterien
- Backend-Coverage für Kernpfade deutlich erhöht
- Frontend hat mindestens Smoke-Tests
- API-Vertragsbrüche fallen früh auf

---

# Phase 7 — Produktverbesserungen mit hohem Nutzen

## 7.1 Neue Features mit hoher Priorität

### Feature A — Run Dashboard / Operations Center
**Nutzen:** Sichtbarkeit für alle laufenden und vergangenen Jobs.

**Umfang:**
- zentrale Übersicht für Graph-Builds, Prepares, Simulationsruns, Reports
- Status, Fortschritt, Dauer, letzte Fehler, Artefakte
- Resume/Restart direkt aus UI

**Backend:** `runs.py` erweitern  
**Frontend:** neues `RunsDashboardView.vue`

---

### Feature B — Szenariovergleich / Branch Compare
**Nutzen:** Branching wird erst richtig wertvoll, wenn Ergebnisse vergleichbar sind.

**Vergleichsdimensionen:**
- Agentenanzahl
- Plattformkonfiguration
- Rundenanzahl
- Aktivität pro Plattform
- meistgenannte Themen
- Report-Differenzen
- Graph-Differenzen vor/nach Simulation

---

### Feature C — Graph Diff vor/nach Simulation
**Nutzen:** Zeigt, was die Simulation wirklich „gelernt“ oder verändert hat.

**Ansicht:**
- neue Knoten
- neue Kanten
- invalidierte/abgelaufene Kanten
- Cluster-Veränderungen

---

### Feature D — Persona Review & Approval Flow
**Nutzen:** Mehr Kontrolle vor dem Simulationsstart.

**Möglichkeiten:**
- generierte Personas einzeln freigeben
- markieren als „zu generisch“ / „zu halluziniert“
- Persona neu generieren
- Persona diff gegen Originalentity anzeigen

---

### Feature E — Report Confidence / Evidence Score
**Nutzen:** Höhere Glaubwürdigkeit des Reports.

**Je Abschnitt anzeigen:**
- Anzahl Claims
- Anzahl Evidence Items
- Anteil Tool-gestützter Claims
- Confidence-Klassifizierung

---

### Feature F — Interview Presets / Research Templates
**Nutzen:** Step 5 wird von Demo-Feature zu Analysewerkzeug.

**Vorlagen:**
- Zustimmung zu Thema X
- emotionale Reaktion
- Risiken / Gegenargumente
- Segmentvergleich
- pro Plattform Unterschiede

---

### Feature G — Health & Setup Diagnostics im UI
**Nutzen:** Weniger Supportaufwand.

**Prüfungen:**
- Neo4j erreichbar
- Ollama / Cloud-Modell erreichbar
- Modellkonfiguration plausibel
- Token/Auth aktiv?
- Upload-/Disk-/Volume-Pfade ok?

---

## 7.2 Mittlere Priorität

### Feature H — Job Replay / Reproduce Run
- bestimmte Konfiguration erneut starten
- gleicher Graph, anderes Modell
- gleicher Report, anderes Promptprofil

### Feature I — Export Center
- Report Markdown/HTML/PDF
- Personas JSON/CSV
- Timeline CSV
- Actions JSONL
- Graph exportierbar als GraphML / JSON

### Feature J — Prompt Presets je Pipeline-Stufe
- Ontology
- Persona
- SimulationConfig
- Report
- Interview

### Feature K — SSE/WebSocket Live Updates
Polling schrittweise ersetzen.

---

## 8. Konkrete Quick Wins (1–2 Wochen)

Wenn nicht sofort das große Refactoring gestartet werden soll, sind diese Punkte der beste Einstieg:

### Quick Win 1
`simulation.py` entlang der Route-Gruppen splitten, ohne Verhalten zu ändern.

### Quick Win 2
Gemeinsames `WorkspaceLayout.vue` für Schritt 2–5 einführen.

### Quick Win 3
`GraphPanel.vue` in D3-Hook + UI-Komponenten zerlegen.

### Quick Win 4
Backend-Tests für `RunRegistry`, `ProjectManager`, `validation.py` ergänzen.

### Quick Win 5
Frontend Polling in `usePolling.js` zentralisieren.

### Quick Win 6
CI um `pytest` + `npm run build` erweitern.

### Quick Win 7
Standardisierte Error-Response-Struktur einführen.

---

## 9. Empfohlene Priorisierung

## Priorität P0 — sofort
- Test-/CI-Grundlage
- API-Splitting `simulation.py`
- Workspace-Layout vereinheitlichen
- GraphPanel zerlegen

## Priorität P1 — danach
- Report-Agent modularisieren
- SimulationState/RunState konsolidieren
- Polling-Composables
- Frontend-Feature-Struktur

## Priorität P2 — mittelfristig
- TypeScript-Einführung
- SSE/WebSocket
- Contract-Tests
- Persona-Review-Flow
- Branch-Compare

## Priorität P3 — strategisch
- Graph-Diff
- Report-Confidence-Scoring
- Replay/Reproduce
- Export-Center

---

## 10. Konkrete Datei-Empfehlungen

## 10.1 Backend zuerst anfassen
1. `backend/app/api/simulation.py`
2. `backend/app/services/report_agent.py`
3. `backend/app/services/simulation_runner.py`
4. `backend/app/services/simulation_manager.py`
5. `backend/app/storage/neo4j_storage.py`

## 10.2 Frontend zuerst anfassen
1. `frontend/src/components/GraphPanel.vue`
2. `frontend/src/views/MainView.vue`
3. `frontend/src/views/SimulationView.vue`
4. `frontend/src/views/SimulationRunView.vue`
5. `frontend/src/components/Step2EnvSetup.vue`
6. `frontend/src/components/Step4Report.vue`

---

## 11. Technische Leitlinien für das Refactoring

## Backend
- keine Fachlogik mehr direkt in Routen
- JSON-Datei-Zugriffe nur über Repository-Schicht
- Statusübergänge zentral
- DTO-Mapping explizit
- Exception-Klassen statt nur String-Errors

## Frontend
- View != Feature != Infrastruktur
- kein Inline-Polling in großen Komponenten
- Graph-Rendering als eigenständiges Feature
- nur noch eine gemeinsame Workspace-Shell
- API-Responses immer über Mapper normalisieren

## Qualität
- neue Features nur mit Tests
- kein neues Monsterfile
- keine weitere Duplizierung von Header-/Status-/Split-Layouts

---

## 12. Bezug zu aktuellen Best Practices

Die Empfehlungen passen zu aktuellen Best Practices aus der Doku der genutzten Technologien:

- **Flask**: App Factory + saubere Blueprint-/Error-Handler-Struktur
- **Neo4j Python Driver**: klarer Einsatz von `execute_read` / `execute_write` und idempotente Transaktionsfunktionen
- **Vue 3**: bessere Trennung von reaktiver Zustandslogik, Komponenten und wiederverwendbaren Composables

Für dieses Repo heißt das konkret:
- Flask-Schichten konsequenter trennen
- Neo4j-Zugriffe weiter repository-artig strukturieren
- Vue-Logik aus XXL-Komponenten in Composables verschieben

---

## 13. Empfohlener Umsetzungsfahrplan

## Sprint 1
- CI-Grundlage
- `simulation.py` modulweise aufteilen
- erste Backend-Tests

## Sprint 2
- WorkspaceLayout einführen
- `GraphPanel.vue` zerlegen
- Polling-Composables

## Sprint 3
- `report_agent.py` modularisieren
- DTOs / Error-Format standardisieren
- Report-UI vereinfachen

## Sprint 4
- Simulation-State konsolidieren
- Branch-Compare MVP
- Persona-Review Flow MVP

## Sprint 5
- TypeScript für API-Modelle
- Graph-Diff
- Evidence-/Confidence-Scoring

---

## 14. Abschlussbewertung

**Technisch:** Das Produkt ist bereits fortgeschritten, aber an einem Punkt, an dem weiteres Wachstum ohne Refactoring teuer wird.  
**Produktseitig:** Die Pipeline ist stark genug, um daraus ein deutlich professionelleres Analyse- und Simulationswerkzeug zu machen.  
**Empfehlung:** Nicht „alles neu“, sondern **gezieltes, phasenweises Refactoring mit klaren Quality Gates**.

Der wichtigste Grundsatz für die nächsten Schritte lautet:

> **Erst Architektur entlasten, dann neue Features beschleunigt liefern.**

---

## 15. Nächster sinnvoller Schritt

Wenn aus diesem Audit direkt ein umsetzbarer Plan entstehen soll, wäre der nächste Schritt:

1. **Refactoring-Backlog in Tickets schneiden**
2. **Phase 0 + Phase 1 zuerst umsetzen**
3. danach **Branch Compare + Run Dashboard** als stärkste Produktverbesserungen priorisieren

---

## 16. Empfohlene Folge-Dokumente

Als Anschluss an dieses Audit empfehle ich drei weitere Dateien:

1. `docu/refactoring-backlog-priorisiert.md`
   - alle Maßnahmen als Tickets / Arbeitspakete

2. `docu/target-architecture.md`
   - Soll-Architektur mit Modulgrenzen

3. `docu/feature-roadmap.md`
   - Produktverbesserungen nach Business-Nutzen sortiert
