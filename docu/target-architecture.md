# Agora / MiroFish-Offline — Zielarchitektur

**Stand:** 2026-04-22  
**Ableitung aus:**
- `docu/2026-04-22-refactoring-produkt-audit.md`
- `docu/refactoring-backlog-priorisiert.md`

---

## 1. Zweck dieses Dokuments

Dieses Dokument beschreibt die **Soll-Architektur** für Agora / MiroFish-Offline nach dem geplanten Refactoring. Es übersetzt Audit-Befunde und priorisiertes Backlog in ein konsistentes Zielbild, das als Referenz für technische Entscheidungen, Modulgrenzen und Migration dient.

Die Zielarchitektur soll vor allem drei Dinge leisten:

1. **Wachstum ermöglichen**, ohne weitere Monolithen zu erzeugen.
2. **Fachliche Zuständigkeiten klar schneiden**, damit Backend, Frontend und Pipeline-Schritte unabhängig weiterentwickelt werden können.
3. **Refactoring in Phasen erlauben**, ohne das bestehende Produkt in einem Big-Bang-Umbau zu destabilisieren.

---

## 2. Ziele

### 2.1 Produktziele
- Die bestehende End-to-End-Pipeline bleibt erhalten: **Upload → Graph → Setup → Simulation → Report → Interaktion**.
- Branching, Report-Evidence, Interviews und Graph-Exploration bleiben Kernfunktionen.
- Künftige Produktfeatures wie **Run Dashboard**, **Branch Compare**, **Persona Review**, **Graph Diff** und **Confidence Scoring** sollen ohne Architekturbruch ergänzt werden können.

### 2.2 Architekturziele
- Keine fachlich zentralen Monsterdateien mehr in API, Services und UI.
- Pro Domäne eine klare **Single Source of Truth** für Zustände und Artefakte.
- Dünne API-Schicht, klar geschnittene Fachservices, kapsulierte Persistenz.
- Wiederverwendbare Frontend-Shells, Feature-Module und Composables statt XXL-Views.
- Einheitliche Datenverträge zwischen Backend und Frontend.
- Bessere Testbarkeit, Beobachtbarkeit und Fehlerdiagnose.

### 2.3 Qualitätsziele
- Neue Module bleiben klein, fokussiert und testbar.
- Polling, Fehlerbehandlung, DTO-Mapping und Statuslogik werden zentralisiert.
- CI, Linting, Tests und Vertragsstabilität werden zur Entwicklungsgrundlage.

---

## 3. Architekturprinzipien

### 3.1 Fachliche Trennung vor technischer Bequemlichkeit
Module werden nach Domänen und Verantwortlichkeiten geschnitten, nicht nach historisch gewachsenen Dateien.

### 3.2 Dünne Schnittstellen, starke Services
- **API/Views** orchestrieren nur.
- **Services/Composables** enthalten Logik.
- **Repositories/Adapter** kapseln IO, JSON, Neo4j und externe Systeme.

### 3.3 Single Source of Truth je Domäne
Jede fachliche Domäne hat genau eine führende Persistenz für Status und Artefakte. In-Memory-Objekte sind nur Runtime-Caches.

### 3.4 Standardisierte Verträge
Alle wichtigen Requests, Responses, Fehlerobjekte und Statusmodelle werden als stabile Verträge definiert und versionierbar gemacht.

### 3.5 Inkrementelle Migration statt Big Bang
Die Zielarchitektur muss schrittweise erreichbar sein. Bestehende Endpunkte und UI-Flows bleiben während der Migration möglichst kompatibel.

### 3.6 Observability als Architekturbestandteil
Logs, Run-Manifeste, Statusobjekte und Health-Signale sind keine Nebenprodukte, sondern Teil des Systems.

### 3.7 Security by Default
Validierung, Authentifizierung, Dateipfad-Sicherheit, sichere Defaults und saubere Fehlergrenzen sind in allen Schichten verpflichtend.

---

## 4. Zielbild

### 4.1 Fachliches Zielbild
Das System besteht aus fünf eng gekoppelten, aber technisch sauber getrennten Domänen:

1. **Project & Graph Domain**  
   Upload, Parsing, Ontology, Chunking, NER/RE, Embeddings, Neo4j-Persistenz, Graph-Suche.

2. **Simulation Domain**  
   Persona-Generierung, Konfigurations-Freeze, Vorbereitung, Branching, Run-Steuerung, Artefaktzugriff.

3. **Run & Async Domain**  
   Task-/Run-Lebenszyklus, Registry, Fortschritt, Logs, Cleanup, Orchestrierung langlaufender Prozesse.

4. **Report Domain**  
   Report-Planung, Tool-Aufrufe, Evidence-Sammlung, Abschnittsgenerierung, Export.

5. **Interaction Domain**  
   Interviews, explorative Abfragen, Survey-/Agenten-Interaktion und spätere Analyse-Features.

### 4.2 Technisches Zielbild
- Backend wird in **API**, **Domain/Services**, **Repositories**, **Schemas/DTOs** und **Infrastructure/Utils** getrennt.
- Frontend wird in **Layouts**, **Features**, **Composables**, **Stores**, **Models** und **API-Adapter** geteilt.
- Async-Abläufe erhalten ein konsistentes Statusmodell, einheitliche Polling-Schnittstellen und vorbereitete SSE/WebSocket-Erweiterbarkeit.
- Persistente JSON-Artefakte bleiben erlaubt, werden aber über definierte Repositories und Mappers verwaltet.

---

## 5. Zielstruktur Backend

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
      models.py
      service.py
      repository.py
      mapper.py
    graphs/
      models.py
      build_service.py
      query_service.py
      ingestion_service.py
      repository.py
      mapper.py
    simulations/
      models.py
      service.py
      prepare_service.py
      branch_service.py
      state_machine.py
      repository.py
      mapper.py
    reports/
      models.py
      planner.py
      section_generator.py
      prompt_builder.py
      tool_schema.py
      tool_executor.py
      evidence.py
      manager.py
      agent.py
    runs/
      models.py
      registry.py
      task_service.py
      cleanup_service.py
      mapper.py
  repositories/
    project_repository.py
    simulation_repository.py
    run_repository.py
  schemas/
    requests.py
    responses.py
    errors.py
  services/
    llm/
      client.py
      json_mode.py
      prompt_utils.py
    storage/
      neo4j_read_repository.py
      neo4j_write_repository.py
      neo4j_search_repository.py
  utils/
    auth.py
    file_parser.py
    logging.py
    retry.py
```

### 5.1 Backend-Schichten

#### API-Schicht
Verantwortlich für:
- Request-Annahme
- Validierung gegen Schemas
- Auth-Prüfung
- Aufruf eines fachlichen Services
- Response-Mapping

Nicht verantwortlich für:
- komplexe Statuslogik
- Dateisystemzugriffe
- Neo4j-Details
- Prompt-Building
- RunRegistry-Nebenlogik

#### Domain-/Service-Schicht
Verantwortlich für:
- Fachregeln
- Statusübergänge
- Orchestrierung von Repositories und Infrastruktur
- Domänenspezifische Fehler

#### Repository-/Adapter-Schicht
Verantwortlich für:
- JSON-Dateien
- Artefaktpfade
- Neo4j-Lese-/Schreiboperationen
- externe APIs/Clients

#### Schema-/Mapper-Schicht
Verantwortlich für:
- Request-/Response-Validierung
- stabile DTOs
- Übersetzung von Persistenzmodellen zu API-Modellen

---

## 6. Backend-Module im Zielzustand

### 6.1 Projects / Graphs

#### Verantwortung
- Projektanlage und Projektmetadaten
- Upload-Verwaltung
- Dateiparsing
- Chunking und semantische Extraktion
- Graph-Build und Graph-Queries

#### Zielmodule
- `projects/service.py`: Projekt-Lifecycle
- `projects/repository.py`: `project.json`, Upload-Referenzen, sichere Pfade
- `graphs/build_service.py`: Build-Orchestrierung
- `graphs/ingestion_service.py`: Semantik-Extraktion, Embeddings, Persistenz-Pipeline
- `graphs/query_service.py`: Suche, Nachbarschaften, Detailansichten, spätere Diff-Funktionen
- `services/storage/neo4j_*`: getrennte Read/Write/Search-Zugriffe

#### Wichtige Regeln
- `add_text()` wird in klar benannte Schritte zerlegt: Extraktion, Embedding, Persistenz.
- Frontend bekommt stabile Node-/Edge-DTOs statt historisch gewachsener Aliasfelder.

### 6.2 Simulationsdomäne

#### Verantwortung
- Simulation anlegen, laden, listen
- Persona- und Config-Generierung
- Vorbereitungsstatus
- Branching und Overrides
- Start/Pause/Resume/Stop
- Zugriff auf Artefakte, Logs und Laufzustand

#### Zielmodule
- `simulations/service.py`: zentrale fachliche Orchestrierung
- `simulations/repository.py`: `state.json`, Artefaktpfade, Simulation-Metadaten
- `simulations/state_machine.py`: erlaubte Statusübergänge
- `simulations/prepare_service.py`: Entity-Read, Persona-Generierung, Config-Freeze
- `simulations/branch_service.py`: Branching, Kopien, Override-Handling
- `api/simulation/*.py`: nach Route-Gruppen geschnittene Endpunkte

#### Wichtige Regeln
- Keine verstreuten JSON-Zugriffe mehr.
- Branching ist eigenes Fachmodul, nicht Sonderfall im Manager.
- Simulationsstatus ist zentral formalisiert.

### 6.3 Runs / Async

#### Verantwortung
- Verwaltung langlaufender Jobs
- Fortschritt, Startzeit, Endzeit, Fehler, Linked IDs
- Cleanup und Wiederaufnahme
- laufzeitnahe Statusaggregation

#### Zielmodule
- `runs/registry.py`: persistente Run-Registry
- `runs/task_service.py`: generische Aufgabensteuerung
- `runs/cleanup_service.py`: Prozessbereinigung / Orphan-Cleanup
- `runs/models.py`: RunStatus, Progress, ErrorInfo, LinkedResource

#### Wichtige Regeln
- Run-Registry ist führend für Run-Zustände.
- In-Memory-Strukturen dürfen nur Beschleuniger sein.
- Alle langlaufenden Prozesse erzeugen einheitliche Run-Manifeste.

### 6.4 Reports

#### Verantwortung
- Report-Planung
- Tool-Definition und Tool-Ausführung
- Prompt-Building
- Section-Generierung
- Evidence-Modell
- Export und Status

#### Zielmodule
- `reports/models.py`: Report, Section, Outline, Evidence-Typen
- `reports/planner.py`: Struktur- und Outline-Planung
- `reports/prompt_builder.py`: getrennte Prompt-Bausteine
- `reports/tool_schema.py`: deklarative Tool-Beschreibung
- `reports/tool_executor.py`: Tool-Laufzeitlogik
- `reports/evidence.py`: Claim-, Evidence- und Confidence-nahe Modelle
- `reports/agent.py`: schlanker Orchestrator
- `reports/manager.py`: Persistenz und Statusmanagement

#### Wichtige Regeln
- Tool-Schema, Tool-Validierung und Tool-Execution werden nicht mehr vermischt.
- ReportAgent koordiniert, implementiert aber nicht alle Details selbst.

---

## 7. Zielstruktur Frontend

```text
frontend/src/
  api/
    client.js
    graph.js
    simulation.js
    report.js
    runs.js
    mappers/
  layouts/
    WorkspaceLayout.vue
    WorkspaceHeader.vue
    WorkspaceSplit.vue
  features/
    graph/
      components/
      composables/
      models/
    project/
      components/
      composables/
      models/
    simulation/
      components/
      composables/
      models/
    report/
      components/
      composables/
      models/
    interaction/
      components/
      composables/
      models/
    runs/
      components/
      composables/
      models/
  composables/
    usePolling.js
    useTaskPolling.js
    useRunPolling.js
    useIncrementalLogPolling.js
  stores/
    projectStore.js
    workspaceStore.js
    runStore.js
  models/
    api/
    ui/
  views/
    MainView.vue
    SimulationView.vue
    SimulationRunView.vue
    ReportView.vue
    InteractionView.vue
    RunsDashboardView.vue
  components/ui/
    AppButton.vue
    StatusChip.vue
    EmptyState.vue
    ErrorPanel.vue
```

### 7.1 Frontend-Schichten

#### Views
- Routing, Page-Komposition, Laden der passenden Feature-Shells
- keine tiefe Fachlogik
- keine ad-hoc Polling-Implementierungen

#### Layouts
- gemeinsame Workspace-Struktur für die Pipeline-Schritte
- Header, Split-Ansicht, Statusslot, Actionslot

#### Features
- fachlich geschnittene UI-Module für Graph, Simulation, Report, Interaktion, Runs
- jeweils eigene Komponenten, Composables und ViewModels

#### Composables
- Wiederverwendung für Polling, Async-Handling, API-State, D3-Integration, Status-Mapping

#### Stores
- nur globaler, langlebiger UI- oder Session-Zustand
- kein unkontrollierter Wildwuchs von versteckter Fachlogik

---

## 8. Frontend-Module im Zielzustand

### 8.1 Graph-Feature

#### Zielkomponenten
- `GraphCanvas.vue`
- `GraphLegend.vue`
- `GraphDetailPanel.vue`
- `GraphToolbar.vue`
- `GraphHintOverlay.vue`

#### Ziel-Composables
- `useGraphData.js`
- `useGraphPolling.js`
- `useD3Graph.js`

#### Zielprinzip
D3-Rendering, Datennachladen und UI-Controls werden getrennt, damit `GraphPanel.vue` nur noch komponiert.

### 8.2 Simulation-Feature

#### Zielkomponenten
- `SimulationStatusPanel.vue`
- `PrepareProgress.vue`
- `ModelSelector.vue`
- `PersonaList.vue`
- `PersonaEditor.vue`
- `SimulationConfigPreview.vue`
- `RunControls.vue`
- `RunConsole.vue`

#### Ziel-Composables
- `useSimulationState.js`
- `usePrepareSimulation.js`
- `useSimulationRun.js`
- `useSimulationArtifacts.js`

### 8.3 Report-Feature

#### Zielkomponenten
- `ReportStatusPanel.vue`
- `ReportOutlinePanel.vue`
- `ReportSectionList.vue`
- `EvidencePanel.vue`
- `AgentLogPanel.vue`
- `ReportExportMenu.vue`

#### Ziel-Composables
- `useReportState.js`
- `useReportGeneration.js`
- `useReportLogs.js`
- `useEvidenceViewModel.js`

### 8.4 Interaction-Feature

#### Zielkomponenten
- `AgentPicker.vue`
- `ChatPanel.vue`
- `SurveyPanel.vue`
- `SurveyResultsTable.vue`

#### Ziel-Composables
- `useAgentInterview.js`
- `useSurveySession.js`

### 8.5 Runs-Feature

#### Zielkomponenten
- `RunsTable.vue`
- `RunStatusDrawer.vue`
- `RunActionBar.vue`

#### Ziel-Composables
- `useRunsDashboard.js`
- `useRunDetails.js`

---

## 9. Async- und State-Architektur

### 9.1 Grundprinzip
Langlaufende Prozesse sind in Agora normal, nicht Ausnahme. Die Architektur behandelt sie deshalb als eigenen Systemaspekt.

### 9.2 Single Source of Truth pro Statusart
- **Projektzustand** → `project.json`
- **Simulationszustand** → `state.json`
- **Run-Zustand** → `run_registry/<run-id>.json` bzw. persistente RunRegistry
- **Laufzeit-Cache** → nur in Memory, nie führend

### 9.3 Zielmodell für Status
Jede asynchrone Domäne verwendet ein kompatibles Zustandsmodell mit:
- `status`
- `phase`
- `progress` (0–100 oder explizit unbekannt)
- `started_at`
- `updated_at`
- `finished_at`
- `linked_resource`
- `error`
- `artifacts`

### 9.4 Simulationszustandsautomat
Mindestens folgende Übergänge werden zentral erlaubt:

```text
created -> preparing -> ready -> running -> completed
                           |         |-> paused -> running
                           |         |-> stopped
                           |         |-> failed
                           -> failed
```

Der Zustandsautomat lebt nicht in API-Routen, sondern in `simulations/state_machine.py`.

### 9.5 Async-Orchestrierung
- API startet Jobs nicht „frei“, sondern über Run-/Task-Services.
- Jeder Job erhält eine Run-ID und eine referenzierte Fachressource.
- Logs, Status und Artefakte sind immer über dieselbe Run-Sicht auffindbar.

### 9.6 Frontend-Async-Modell
- Polling wird über generische Composables vereinheitlicht.
- Komponenten kennen nur noch deklarative Inputs wie `load`, `interval`, `shouldContinue`, `onError`.
- Cleanup bei Unmount oder Route-Wechsel ist zentral.

### 9.7 Evolutionspfad
Kurzfristig bleibt **Polling** Standard. Mittelfristig wird die Architektur für **SSE oder WebSockets** vorbereitet, ohne Feature-Komponenten erneut zu zerlegen.

---

## 10. Datenverträge

### 10.1 Zielsetzung
Frontend und Backend sollen über stabile, dokumentierte und testbare Verträge sprechen. Historisch gewachsene Antwortformate werden auf wenige konsistente Muster reduziert.

### 10.2 Response-Grundmuster

#### Erfolg
```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

#### Fehler
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

### 10.3 Kern-DTOs
Es werden mindestens folgende Kernverträge stabilisiert:
- `ProjectDTO`
- `GraphNodeDTO`
- `GraphEdgeDTO`
- `SimulationDTO`
- `SimulationPrepareStatusDTO`
- `RunStatusDTO`
- `ReportStatusDTO`
- `ReportSectionDTO`
- `EvidenceItemDTO`
- `InterviewResponseDTO`

### 10.4 Mapping-Regeln
- Persistenzmodelle dürfen von API-DTOs abweichen.
- Frontend arbeitet mit API-DTOs oder abgeleiteten ViewModels, nie direkt mit Rohdaten aus mehreren Legacy-Formen.
- Feldaliasse und Rückwärtskompatibilität werden in Mappern gekapselt, nicht in Views.

### 10.5 Vertragsversionierung
Für kritische Endpunkte wird ein leichtgewichtiger Versionierungsansatz empfohlen:
- additive Felder bevorzugen
- Breaking Changes nur geplant und dokumentiert
- Contract-Tests für Kernpfade

---

## 11. Observability

### 11.1 Ziele
- Fehler schneller finden
- Langläufer transparent machen
- Reproduzierbarkeit von Runs verbessern
- spätere Betriebsansichten wie Run Dashboard ermöglichen

### 11.2 Logs
Logs werden strukturell nach Domäne getrennt:
- Graph-Build-Logs
- Prepare-Logs
- Simulation-Logs
- Report-Agent-Logs
- API-/System-Logs

Wichtige Eigenschaften:
- Run-ID und verlinkte Ressource im Log-Kontext
- konsistente Zeitstempel
- klare Trennung von Benutzerfehlern, Infrastrukturfehlern und Fachfehlern

### 11.3 Run-Manifeste
Jeder Langläufer erzeugt ein maschinenlesbares Manifest mit:
- Job-Typ
- Status
- Fortschritt
- Start/Ende
- Artefaktpfaden
- Fehlermetadaten
- optionalen Countern und Performance-Hinweisen

### 11.4 Health & Diagnostics
Mindestens folgende Health-Signale sollen standardisiert abfragbar sein:
- Backend erreichbar
- Neo4j erreichbar
- LLM-Endpunkt erreichbar
- Upload-/Artefaktpfade verfügbar
- Konfiguration plausibel

### 11.5 Metriken
Mindestens auf Anwendungsebene sinnvoll:
- Dauer von Graph-Build, Prepare, Simulation, Report
- Fehlerraten pro Domäne
- Anzahl aktiver Runs
- Retry-/Abbruchraten
- Polling-Last bzw. Update-Häufigkeit

---

## 12. Sicherheit

### 12.1 Grundprinzipien
- Eingaben werden auf jeder Schicht validiert.
- Auth bleibt aktivierbar und konsistent über alle Kernrouten.
- Dateisystemzugriffe laufen nur über sichere Repository-Funktionen.
- Interne Fehlerdetails werden nicht ungefiltert an Clients geleakt.

### 12.2 API-Sicherheit
- Token-basierte Auth für schreibende oder sensible Endpunkte
- konsistentes Fehlerobjekt statt unstrukturierter Tracebacks
- zentrale Request-Validierung und ID-Prüfung

### 12.3 Dateisystem- und Artefaktsicherheit
- Pfadauflösung nur über Whitelisting und sichere Join-Strategien
- keine frei kombinierbaren Client-Pfade
- Uploads und Simulation-Artefakte bleiben strikt innerhalb definierter Roots
- **`SimulationArtifactStore`-Port** (`backend/app/services/artifact_store.py`, Issue #13) ist die einzige zugelassene Schreib-/Lese-Schnittstelle für JSON-Artefakte unter `uploads/simulations/<sim_id>/`. Domäne und API benutzen logische Artefakt-Namen; der `LocalFilesystemArtifactStore` wrappt `utils/json_io` (atomic write + fsync). Tests injizieren den `InMemoryArtifactStore`. Cloud-Adapter (S3/Azure) folgen hinter dem gleichen Interface.

### 12.4 Daten- und Modell-Sicherheit
- Sanitizing von Graph-Labels und extern abgeleiteten Bezeichnern
- defensive Verarbeitung von LLM-Ausgaben
- klare Grenzen zwischen Rohantworten, Parsern und persistierten Strukturen

### 12.5 Geheimnisse und Konfiguration
- Secrets ausschließlich aus `.env` bzw. Laufzeitumgebung
- keine Token oder Zugangsdaten in Artefakten, Logs oder Exports
- Health-/Debug-Endpunkte geben keine sensiblen Konfigurationen preis

---

## 13. Migrationspfad

Die Zielarchitektur wird **inkrementell** erreicht. Die Reihenfolge folgt Audit und priorisiertem Backlog.

### Phase 0 — Qualitätsfundament
**Ziel:** Refactoring absichern.

- CI mit Backend-Tests und Frontend-Build
- Python-Linting und Frontend-Linting
- standardisierte Quality-Skripte
- erste Tests für RunRegistry, ProjectManager und Validierung

**Ergebnis:** Änderungen werden früh geprüft; Refactoring erfolgt nicht mehr im Blindflug.

### Phase 1 — Simulation API entflechten
**Ziel:** größtes API-Monolithrisiko reduzieren.

- `backend/app/api/simulation.py` nach Lifecycle, Prepare, Run, Profiles, Interviews, Branches, Artifacts splitten
- gemeinsame Helper für Validierung, Fehler-Mapping und Run-Updates extrahieren

**Ergebnis:** dünnere Endpunkte, klarere Zuständigkeiten, kleinere Änderungsflächen.

### Phase 2 — Frontend-Workspace konsolidieren
**Ziel:** Layout-Duplikate und UI-Streuverantwortung reduzieren.

- `WorkspaceLayout.vue`, `WorkspaceHeader.vue`, `WorkspaceSplit.vue` einführen
- Pipeline-Views auf gemeinsame Shell migrieren
- Status- und Header-Konfiguration deklarativ machen

**Ergebnis:** konsistente UX, weniger duplizierte View-Struktur.

### Phase 3 — Polling und Async-State zentralisieren
**Ziel:** einheitliche Langläuferbehandlung im Frontend.

- `usePolling`, `useTaskPolling`, `useRunPolling`, `useIncrementalLogPolling` einführen
- Inline-Polling aus Views und Step-Komponenten entfernen

**Ergebnis:** berechenbares UI-Verhalten, sauberes Cleanup, weniger Boilerplate.

### Phase 4 — Simulationsdomäne schneiden
**Ziel:** saubere Fachlogik und Statusverwaltung.

- `SimulationRepository`, `PrepareService`, `BranchService`, `StateMachine` einführen
- JSON-Zugriffe kapseln
- Statusübergänge zentralisieren

**Ergebnis:** robuste Simulationslogik und stabile Single Source of Truth.

### Phase 5 — Report-Engine modularisieren
**Ziel:** größten Service-Hotspot strukturieren.

- Modelle, Logging, Prompt-Building, Tool-Schema, Tool-Execution, Evidence und Manager trennen
- `ReportAgent` auf Orchestrierung reduzieren

**Ergebnis:** bessere Testbarkeit und Erweiterbarkeit für Report-Features.

### Phase 6 — Graph-/Storage-Schicht schärfen
**Ziel:** Neo4j- und Ingestion-Komplexität kontrollieren.

- Read/Write/Search-Repositories trennen
- Ingestion-Pipeline modularisieren
- Graph-DTOs standardisieren

**Ergebnis:** klarere Graph-Schnittstellen und bessere Grundlage für Graph Diff und Compare.

### Phase 7 — Vertrags- und Typisierungsschicht
**Ziel:** Stabilität über die Schichten hinweg.

- standardisierte Response-/Fehler-Schemas
- Frontend-Mapper und ViewModels
- schrittweise TypeScript-Einführung für API-Modelle und Composables
- Contract-Tests zwischen Backend und Frontend

**Ergebnis:** weniger Integrationsfehler und besser abgesicherte Evolution.

### Phase 8 — Produktausbau auf stabiler Basis
**Ziel:** neue Features auf tragfähiger Architektur aufsetzen.

- Run Dashboard
- Branch Compare
- Persona Review & Approval
- Graph Diff
- Confidence-/Evidence-Scoring
- SSE/WebSocket-Live-Updates

---

## 14. Architekturentscheidungen für die Umsetzung

### 14.1 Bewusst beibehalten
- Flask Application Factory
- DI über `app.extensions`
- OpenAI-kompatibler LLM-Client
- dateibasierte Artefakte für lokale/offline-nahe Nutzbarkeit
- OASIS-Simulation im separaten Subprozess

### 14.2 Bewusst ändern
- monolithische API-Dateien und Service-Dateien
- mehrfach redundante Zustandsquellen
- unkoordinierte Polling-Logik
- direkte JSON-/Pfadlogik in Fachcode und Routen
- UI-Monolithen mit gemischter Verantwortung

---

## 15. Definition of Done für die Zielarchitektur

Ein Refactoring-Schritt gilt architektonisch nur dann als abgeschlossen, wenn:

- Modulgrenzen klarer sind als vorher
- keine neue Datei unnötig monolithisch geworden ist
- fachliche Zuständigkeiten explizit benannt sind
- relevante Tests ergänzt oder angepasst wurden
- Datenverträge dokumentiert bzw. stabilisiert wurden
- Async- und Cleanup-Verhalten berücksichtigt wurde
- Observability- und Fehlerpfade nicht verschlechtert wurden

---

## 16. Zusammenfassung

Die Zielarchitektur für Agora ist **keine komplette Neuerfindung**, sondern eine kontrollierte Weiterentwicklung des bestehenden Produkts:

- Die fachliche Pipeline bleibt erhalten.
- Die Architektur wird entlang der Domänen **Graph**, **Simulation**, **Runs**, **Report** und **Interaktion** sauberer geschnitten.
- Backend und Frontend erhalten klare Modulgrenzen.
- Async-State, Datenverträge, Observability und Sicherheit werden zu erstklassigen Architekturthemen.
- Der Migrationspfad ist explizit so gewählt, dass zuerst Risiko und Komplexität sinken und danach neue Produktfeatures schneller entstehen.

Der Leitgedanke lautet:

> **Erst Architektur entlasten, dann Produktgeschwindigkeit erhöhen.**
