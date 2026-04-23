# P0-Arbeitsprotokoll

**Start:** 2026-04-22  
**Ziel:** P0 aus `docu/refactoring-backlog-priorisiert.md` kleinteilig umsetzen und jeden Schritt nachvollziehbar dokumentieren.

---

## 1. Scope für diesen P0-Block

Für den ersten P0-Umsetzungsblock werden bewusst nur die **sichersten und am stärksten vorbereitenden Maßnahmen** umgesetzt:

1. CI-Grundpipeline
2. Root-Quality-Scripts
3. Python-Linting mit Ruff
4. Frontend-Linting mit ESLint (minimal, aber lauffähig)
5. erste Backend-Tests für zentrale Hilfskomponenten

**Noch nicht Teil dieses ersten P0-Blocks:**
- Aufspaltung von `backend/app/api/simulation.py`
- Zerlegung von `GraphPanel.vue`
- größere Frontend-Refactorings

Diese folgen erst, wenn die Quality-Basis steht.

---

## 2. Arbeitsprinzipien

- Jede Änderung wird mit betroffenen Dateien dokumentiert.
- Vor Abschlussbehauptungen wird immer verifiziert.
- Bestehende, nicht von mir stammende Änderungen werden nicht stillschweigend vereinnahmt.
- Günstigere Subagents dürfen Doku-/Analysearbeit vorbereiten; kritische Code-Änderungen und Endabnahme bleiben zentral.

---

## 3. Baseline vor Änderungen

### 3.1 Verifikation ausgeführt

#### Backend-Tests
Befehl:
```bash
cd backend && uv run pytest
```

Ergebnis vor P0-Änderungen:
- **35 Tests bestanden**
- Laufzeit ca. **9.74s**

#### Frontend-Build
Befehl:
```bash
cd frontend && npm run build
```

Ergebnis vor P0-Änderungen:
- **Build erfolgreich**
- Vite-Build lief durch
- nur ein vorhandener Chunking-Hinweis zu `pendingUpload.js`, kein Build-Fehler

### 3.2 Arbeitsbaumstatus vor P0
Befehl:
```bash
git status --short
```

Beobachtung vor Start:
- `M README.md`
- `?? docu/`

**Wichtig:** `README.md` wird nicht als Teil meiner P0-Änderungen behandelt.

---

## 4. Entscheidungen für die P0-Umsetzung

### Entscheidung A — minimaler sicherer P0-Schnitt
Statt sofort mehrere große Refactorings zu mischen, wird zuerst die **Qualitäts- und Testbasis** gelegt.

**Grund:**
- reduziert Risiko
- schafft schnell messbaren Fortschritt
- erleichtert spätere größere Refactorings

### Entscheidung B — Frontend-Lint bewusst pragmatisch
Das Frontend-Linting wird zunächst **minimal, aber stabil lauffähig** eingeführt.

**Grund:**
- Ziel von P0 ist zuerst ein Quality-Gate, nicht vollständige Stilbereinigung aller Altdateien
- zu strenge Regeln würden unnötig viele Sofortfixes erzwingen

### Entscheidung C — erste neue Tests fokussieren auf stabile Kernbausteine
Die ersten zusätzlichen Tests werden auf folgende Bereiche konzentriert:
- `RunRegistry`
- `ProjectManager`
- `validation.py`

**Grund:**
- hohe Hebelwirkung
- geringe externe Abhängigkeiten
- gute Absicherung für spätere Refactorings

---

## 5. Kontextrecherche für P0

Für die P0-Konfiguration wurden aktuelle Doku-Hinweise geprüft zu:
- **Ruff** (`pyproject.toml`, GitHub Actions)
- **ESLint v9 Flat Config**
- **pytest-Konfiguration in `pyproject.toml`**

Kernauswahl für die Umsetzung:
- Ruff via `[tool.ruff]` und `[tool.ruff.lint]`
- pytest via `[tool.pytest.ini_options]`
- ESLint via `eslint.config.js` (Flat Config)

---

## 6. Geplanter Patch-Satz

### 6.1 Erwartete neue/angepasste Dateien

#### Root / CI
- `.github/workflows/ci.yml`
- `package.json`

#### Backend
- `backend/pyproject.toml`
- `backend/tests/test_run_registry.py`
- `backend/tests/test_project_manager.py`
- `backend/tests/test_validation.py`

#### Frontend
- `frontend/package.json`
- `frontend/eslint.config.js`
- `frontend/package-lock.json` (falls Dependency-Update nötig)

### 6.2 Verifikationsziele nach Umsetzung
- `cd backend && uv run pytest`
- `cd backend && uv run ruff check .`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

---

## 7. Laufende Änderungsdokumentation

### 7.1 Quality-Scripts und CI ergänzt

**Geänderte / neue Dateien**
- `package.json`
- `.github/workflows/ci.yml`

**Änderungen**
- neue Root-Scripts ergänzt:
  - `build:frontend`
  - `lint:frontend`
  - `lint:backend`
  - `test:backend`
  - `check`
- neue CI-Pipeline angelegt mit zwei Jobs:
  - **Backend tests + lint**
  - **Frontend build + lint**

**Wichtige Detailentscheidung**
- `lint:backend` ist im ersten Schritt **bewusst scoped** auf:
  - `app/models/project.py`
  - `app/services/run_registry.py`
  - `app/utils/validation.py`
  - die drei neuen Testdateien

**Begründung**
- Ein unscoped Ruff-Lauf über das gesamte Legacy-Backend zeigte sehr viele bestehende Altlasten.
- Für diesen ersten P0-Block wurde deshalb ein **kontrollierter Rollout** gewählt: neue bzw. direkt abgesicherte Kernbereiche sind lint-clean, die Altlasten bleiben sichtbar, blockieren aber nicht den P0-Start.

---

### 7.2 Python-Linting und pytest-Konfiguration ergänzt

**Geänderte Datei**
- `backend/pyproject.toml`

**Änderungen**
- `ruff` zu Dev-Abhängigkeiten ergänzt
- pytest-Konfiguration in `pyproject.toml` ergänzt
- Ruff-Konfiguration in `pyproject.toml` ergänzt

**Zusatzfix**
- `backend/app/utils/validation.py`
  - ungenutzten Import entfernt, damit der gescopte Ruff-Check sauber läuft
- `backend/app/models/project.py`
  - ungenutzten `asdict`-Import entfernt

---

### 7.3 Frontend-Linting eingeführt

**Geänderte / neue Dateien**
- `frontend/package.json`
- `frontend/eslint.config.js`
- `frontend/package-lock.json`

**Änderungen**
- ESLint-Script ergänzt: `npm run lint`
- Flat Config für ESLint eingeführt
- Vue-/JS-Linting für `.vue` und `.js` aktiviert
- pragmatische Regeln gewählt:
  - Fehler für echte Lint-Blocker
  - Warnungen für bestehende ungenutzte Variablen
  - `vue/multi-word-component-names` vorerst deaktiviert

**Installierte Dev-Dependencies**
- `eslint`
- `@eslint/js`
- `eslint-plugin-vue`
- `vue-eslint-parser`
- `globals`

**Installationsverifikation**
Befehl:
```bash
cd frontend && npm install
```

Beobachtung:
- Installation erfolgreich
- `npm audit` meldete **5 bekannte Vulnerabilities** (1 moderate, 4 high)
- Diese wurden **nicht** im P0-Minimum behoben und bleiben als Folgepunkt offen

---

### 7.4 Erste Backend-Tests ergänzt

**Neue Dateien**
- `backend/tests/test_project_manager.py`
- `backend/tests/test_run_registry.py`
- `backend/tests/test_validation.py`

**Abgesicherte Bereiche**
- `ProjectManager`
  - create / save / load / delete
  - Dateiablage im Projektverzeichnis
  - invalid project id
- `RunRegistry`
  - persistente Manifest-Erzeugung
  - Status-Update / Event-Anhang
  - `get_latest_by_linked_id`
  - `sync_task`
- `validation.py`
  - project / simulation / report / run / graph / task ids

---

### 7.5 Kleine Frontend-Fixes für fehlerfreies Linting

**Geänderte Dateien**
- `frontend/src/components/HistoryDatabase.vue`
- `frontend/src/views/SimulationRunView.vue`
- `frontend/src/views/SimulationView.vue`

**Änderungen**
- leere `catch`-Blöcke in dokumentierte Best-Effort-/Non-Fatal-Blöcke umgewandelt
- Ziel war nicht funktionale Änderung, sondern sauberes ESLint-Verhalten ohne Error-Level-Verstöße

---

## 8. Verifikation nach Umsetzung

### 8.1 Zwischenprüfung: unscope'd Ruff war noch nicht bereit
Befehl:
```bash
cd backend && uv run ruff check .
```

Ergebnis:
- viele bestehende Legacy-Befunde außerhalb des P0-Minimums
- daraufhin bewusste Entscheidung für **scoped rollout** statt Schein-Fix oder Massenänderung

### 8.2 Frontend-Lint
Befehl:
```bash
cd frontend && npm run lint
```

Ergebnis:
- **0 Fehler**
- **23 Warnungen** zu bestehendem ungenutztem Code / Parametern
- Lint-Befehl lief erfolgreich durch

### 8.3 Finaler Root-Check
Befehl:
```bash
npm run check
```

Ergebnis:
- `lint:backend` → **bestanden**
- `test:backend` → **49 Tests bestanden**
- `lint:frontend` → **0 Fehler, 23 Warnungen**
- `build:frontend` → **bestanden**

**Fazit aus Verifikation**
- Der erste P0-Block ist **funktionsfähig umgesetzt und verifiziert**.
- Backend-Linting ist absichtlich **zunächst gescoped**.
- Frontend-Linting ist **eingeführt und lauffähig**, aber mit dokumentierten Warnungen.

---

## 9. Folgeblock: erster kontrollierter Split von `simulation.py`

### 9.1 Ziel
Nach der Quality-Basis wurde der nächste P0-Schritt gestartet: die kontrollierte Aufspaltung von `backend/app/api/simulation.py`.

### 9.2 Umgesetzter Teilschritt
Es wurden zunächst die **am schwächsten gekoppelten Routen** herausgelöst:

**Neue Dateien**
- `backend/app/api/simulation_common.py`
- `backend/app/api/simulation_entities.py`
- `backend/app/api/simulation_lifecycle.py`
- `backend/tests/test_simulation_api_routes.py`

**Geänderte Dateien**
- `backend/app/api/__init__.py`
- `backend/app/api/simulation.py`
- `package.json`
- `.github/workflows/ci.yml`

**Herausgelöste Endpunkte**
- `/available-models`
- `/entities/<graph_id>`
- `/entities/<graph_id>/<entity_uuid>`
- `/entities/<graph_id>/by-type/<entity_type>`
- `/create`
- `/<simulation_id>`
- `/list`

### 9.3 Verifikation dieses Split-Schritts
#### Zusatztest
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_api_routes.py
```

Ergebnis:
- **4 Tests bestanden**

#### Voller Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **53 bestanden**
- Frontend Lint → **0 Fehler, 23 Warnungen**
- Frontend Build → **bestanden**

### 9.4 Bewertung
- Der Split ist **funktional gelungen**.
- Das bestehende Routing blieb stabil.
- Das Blueprint-Modell wurde nicht gebrochen.
- `simulation.py` ist noch nicht fertig zerlegt, aber der riskante erste Schnitt ist jetzt sauber etabliert.

### 9.5 Zweiter Split-Schritt
Danach wurde zusätzlich der **Prepare-Block** herausgelöst:

**Neue Datei**
- `backend/app/api/simulation_prepare.py`

**Herausgelöste Logik**
- `_check_simulation_prepared`
- `/prepare`
- `/prepare/status`

**Zusätzliche Verifikation**
- `backend/tests/test_simulation_api_routes.py` wurde auf **6 API-Smoke-Tests** erweitert
- `npm run check` lief danach erneut erfolgreich durch
- Gesamtstand danach:
  - **55 Backend-Tests bestanden**
  - Frontend-Lint weiter **0 Fehler, 23 Warnungen**
  - Frontend-Build **bestanden**

### 9.6 Dritter Split-Schritt
Danach wurden **Profile / Config / Branches** herausgelöst.

**Neue Datei**
- `backend/app/api/simulation_profiles.py`

**Herausgelöste Logik**
- `/<simulation_id>/branch`
- `/<simulation_id>/branches`
- `/<simulation_id>/profiles` (GET/POST/DELETE)
- `/<simulation_id>/profiles/realtime`
- `/<simulation_id>/config`
- `/<simulation_id>/config/realtime`
- `/<simulation_id>/config/download`
- `/script/<script_name>/download`

**Zusätzliche Verifikation**
- `backend/tests/test_simulation_api_routes.py` wurde auf **8 API-Smoke-Tests** erweitert
- `npm run check` lief erneut erfolgreich durch
- Gesamtstand danach:
  - **57 Backend-Tests bestanden**
  - Frontend-Lint weiter **0 Fehler, 23 Warnungen**
  - Frontend-Build **bestanden**

### 9.7 Vierter Split-Schritt
Danach wurden **Run-Control / Run-Status / Env-Control** herausgelöst.

**Neue Datei**
- `backend/app/api/simulation_run.py`

**Herausgelöste Logik**
- `/start`
- `/stop`
- `/<simulation_id>/pause`
- `/<simulation_id>/resume`
- `/<simulation_id>/console-log`
- `/<simulation_id>/run-status`
- `/<simulation_id>/run-status/detail`
- `/<simulation_id>/actions`
- `/<simulation_id>/timeline`
- `/<simulation_id>/agent-stats`
- `/env-status`
- `/close-env`

**Zusätzliche Verifikation**
- `backend/tests/test_simulation_api_routes.py` wurde auf **11 API-Smoke-Tests** erweitert
- `npm run check` lief erneut erfolgreich durch
- Gesamtstand danach:
  - **60 Backend-Tests bestanden**
  - Frontend-Lint weiter **0 Fehler, 23 Warnungen**
  - Frontend-Build **bestanden**

### 9.8 Fünfter Split-Schritt
Danach wurden die **restlichen History-/Interview-/Standalone-Routen** herausgelöst.

**Neue Dateien**
- `backend/app/api/simulation_interviews.py`
- `backend/app/api/simulation_history.py`

**Herausgelöste Logik**
- `/history`
- `/generate-profiles`
- `/<simulation_id>/posts`
- `/<simulation_id>/comments`
- `/interview`
- `/interview/batch`
- `/interview/all`
- `/interview/history`

**Wichtige Folgeentscheidung**
- `backend/app/api/simulation.py` wurde danach auf einen **Kompatibilitäts-Shim** reduziert.
- Die tatsächliche Routenregistrierung erfolgt nun vollständig in den gesplitteten Modulen.

**Zusätzliche Verifikation**
- `backend/tests/test_simulation_api_routes.py` wurde auf **14 API-Smoke-Tests** erweitert
- `npm run check` lief erneut erfolgreich durch
- Gesamtstand danach:
  - **63 Backend-Tests bestanden**
  - Frontend-Lint weiter **0 Fehler, 23 Warnungen**
  - Frontend-Build **bestanden**

### 9.9 Erster GraphPanel-Modularisierungsschritt
Nach dem Abschluss des Backend-Splits wurde der nächste P0-Hotspot im Frontend begonnen: `frontend/src/components/GraphPanel.vue`.

**Neue Dateien**
- `frontend/src/components/graph/GraphDetailPanel.vue`
- `frontend/src/components/graph/GraphLegend.vue`
- `frontend/src/components/graph/graphPanelUtils.js`
- zusätzliches Detailprotokoll: `docu/p0-graph-panel-modularisierung-protokoll.md`

**Geänderte Datei**
- `frontend/src/components/GraphPanel.vue`

**Herausgelöste Logik**
- komplette Node-/Edge-Detailansicht
- Self-Loop-Detaildarstellung
- Entity-Type-Legende
- Hilfsfunktionen für Entity-Type-Berechnung und Datumsformatierung

**Wichtige Designentscheidung**
- Der D3-Renderer selbst wurde in diesem Schritt **noch nicht** zerlegt.
- Zuerst wurde nur die statische bzw. UI-lastige Logik aus dem Monolithen herausgezogen, um Risiko zu minimieren.

**Messbarer Effekt**
- `GraphPanel.vue` wurde von **1433 auf 905 Zeilen** reduziert
- Frontend-ESLint-Warnungen sanken von **23 auf 21**

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 21 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **63 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.10 Zweiter GraphPanel-Modularisierungsschritt
Danach wurde die **D3-Datenaufbereitung / Graph-Normalisierung** aus `GraphPanel.vue` herausgezogen.

**Neue Datei**
- `frontend/src/components/graph/graphPanelData.js`

**Geänderte Datei**
- `frontend/src/components/GraphPanel.vue`

**Herausgelöste Logik**
- Node-Normalisierung
- Farbmapping für Entity Types
- Filterung renderbarer Kanten
- Self-Loop-Gruppierung
- Mehrfachkanten-Zählung pro Node-Paar
- Krümmungsberechnung
- Zusammenbau des Render-Modells `{ nodes, edges, getColor }`

**Wichtige Designentscheidung**
- Force-Simulation, SVG-Renderer, Zoom und Drag-Handling blieben noch in `GraphPanel.vue`.
- So wurde die funktionale Datenlogik getrennt, ohne den sensibleren D3-Lebenszyklus unnötig anzufassen.

**Messbarer Effekt**
- `GraphPanel.vue` wurde weiter von **905 auf 785 Zeilen** reduziert
- Frontend-ESLint-Warnungen blieben stabil bei **21**

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 21 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **63 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.11 Versions- und README-Synchronisierung
Zwischen den Refactoring-Schritten wurde zusätzlich eine **sichtbare Versionsanhebung plus README-Überarbeitung** eingezogen, damit der öffentliche Projektzustand zum tatsächlichen Stand passt.

**Version angehoben auf**
- `0.4.0`

**Geänderte Dateien**
- `package.json`
- `package-lock.json`
- `frontend/package.json`
- `frontend/package-lock.json`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/app/api/status.py`
- `backend/tests/test_status.py`
- `frontend/src/i18n/locales/de.json`
- `frontend/src/i18n/locales/en.json`
- `README.md`
- `CHANGELOG.md`
- `docs/ROADMAP.md`

**README-Überarbeitung**
- Versionsstatus auf `v0.4.0 alpha` aktualisiert
- Engineering-Status (Qualitäts-Gates, API-Split, GraphPanel-Modularisierung) sichtbar gemacht
- Architekturabschnitt auf die gesplitteten Simulation-API-Module aktualisiert
- Entwicklungsbefehle um `npm run check` ergänzt
- Refactoring-Dokumentation unter `docu/` im README verlinkt
- englische README-Hälfte ebenfalls auf denselben Stand gebracht

**Verifikation**
- `npm run check` lief nach der Versionsanhebung erneut erfolgreich durch
- dabei weiter bestätigt:
  - **63 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.12 Dritter GraphPanel-Modularisierungsschritt
Danach wurde die **Link-Geometrie** aus `GraphPanel.vue` herausgezogen.

**Neue Datei**
- `frontend/src/components/graph/graphPanelGeometry.js`

**Geänderte Datei**
- `frontend/src/components/GraphPanel.vue`

**Herausgelöste Logik**
- SVG-Path-Berechnung für Links
- Midpoint-Berechnung für Label-Positionen
- Self-Loop-Geometrie
- gemeinsame Kontrollpunkt-Berechnung für gekrümmte Kanten

**Wichtige Designentscheidung**
- Die Geometrie wurde vor dem Renderer extrahiert, weil sie rein funktional ist.
- D3-Simulation, Zoom, Drag und DOM-Manipulation blieben weiter im Parent.

**Messbarer Effekt**
- `GraphPanel.vue` wurde weiter von **785 auf 714 Zeilen** reduziert
- Frontend-ESLint-Warnungen blieben stabil bei **21**

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 21 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **63 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.13 Embedding-Konfiguration gehärtet
Nach der Architekturkritik wurde die Kopplung von `EMBEDDING_MODEL` und `VECTOR_DIM` fail-fast abgesichert.

**Neue Datei**
- `backend/tests/test_embedding_service.py`
- zusätzliches Detailprotokoll: `docu/p0-embedding-config-hardening-protokoll.md`

**Geänderte Dateien**
- `backend/app/config.py`
- `backend/app/storage/embedding_service.py`
- `backend/app/__init__.py`
- `.env.example`
- `package.json`
- `.github/workflows/ci.yml`

**Umgesetzte Logik**
- bekannte Modell→Dim-Mappings eingeführt
- `VECTOR_DIM` wird nun standardmäßig aus `EMBEDDING_MODEL` abgeleitet, wenn nichts explizit gesetzt ist
- Startup-Probe gegen das echte Embedding-Backend eingeführt
- Mismatch zwischen Modell, Probe-Vektor und `VECTOR_DIM` führt nun zu einem **harten Fehler beim Start**
- `.env.example` auf den realen v0.4.0-Stand gebracht

**Zusätzliche Verifikation**
- `cd backend && uv run pytest tests/test_embedding_service.py tests/test_status.py` → **11/11 bestanden**
- `cd backend && uv run ruff check app/__init__.py app/config.py app/storage/embedding_service.py tests/test_embedding_service.py` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **67 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.14 Polling-Composable eingeführt
Anschließend wurde der nächste von außen identifizierte P0-Hebel umgesetzt: Polling-Grundlogik wurde zentralisiert.

**Neue Datei**
- `frontend/src/composables/usePolling.js`
- zusätzliches Detailprotokoll: `docu/p0-polling-composable-protokoll.md`

**Geänderte Dateien**
- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step3Simulation.vue`
- `frontend/src/components/Step4Report.vue`

**Umgesetzte Logik**
- wiederverwendbares Polling-Composable mit Start/Stop/Tick/Cleanup
- Overlap-Schutz für laufende Async-Polls
- Migration der wichtigsten Langläufer:
  - Prepare-Status / Realtime-Profile / Realtime-Config
  - Run-Status / Run-Detail / Console-Log
  - Report-Status / Agent-Log / Console-Log

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 21 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **67 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.15 Root-Cleanup
Zusätzlich wurde das Wurzelverzeichnis von alten Hilfsdateien und Notiz-Artefakten entlastet.

**Neue Datei**
- `docu/p0-root-cleanup-protokoll.md`

**Verschobene Dateien**
- `plan.md` → `docu/history/previous-agent-plan.md`
- `SECURITY_REPORT.md` → `docu/history/security-review-report.md`
- `fix_logs.py` → `scripts/logs/fix_logs.py`
- `format_logs.py` → `scripts/logs/format_logs.py`

**Begleitende Anpassung**
- Log-Skripte wurden von `docs/logs/...` auf `docu/logs/...` umgestellt

**Verifikation**
- Pfad- und Dateiumzug geprüft
- Log-Skripte zeigen nun auf die neue Dokumentationsablage

### 9.16 Report-Status-Regression behoben
Nach dem Polling-/Refactoring-Stand trat eine Regression auf: `POST /api/report/generate/status` konnte mit HTTP 500 abbrechen, wenn Polling genau in dem Moment auf `progress.json` oder `meta.json` zugriff, in dem diese Dateien gerade neu geschrieben wurden.

**Root Cause**
- Report-Status-Endpunkte lasen JSON-Artefakte direkt
- Report-Dateien wurden nicht atomar geschrieben
- bei einer Polling-Anfrage im falschen Moment konnte `json.load(...)` auf einer leeren/trunkierten Datei landen
- Ergebnis: `JSONDecodeError` und 500er im Backend-Log

**Geänderte Dateien**
- `backend/app/services/report_agent.py`
- `backend/tests/test_report_manager.py`
- `package.json`
- `.github/workflows/ci.yml`

**Umgesetzter Fix**
- atomische JSON-Schreibfunktion für Report-Artefakte eingeführt
- defensive JSON-Lesehilfe eingeführt
- `get_progress()`, `get_report()` und `get_evidence_map()` tolerieren jetzt kurzzeitig unlesbare/trunkierte Dateien sauber
- zusätzlicher Testschutz für ungültige/temporär leere Report-JSON-Dateien
- Scoped-Ruff-Rollout auf `report_agent.py` und neuen Report-Manager-Test erweitert

**Zusätzliche Verifikation**
- `cd backend && uv run pytest tests/test_report_manager.py tests/test_embedding_service.py tests/test_status.py` → **14/14 bestanden**
- `cd backend && uv run ruff check app/__init__.py app/config.py app/storage/embedding_service.py app/services/report_agent.py tests/test_embedding_service.py tests/test_report_manager.py` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **70 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.17 Weitere JSON-/Polling-Härtung im Simulation-Stack
Danach wurden analoge Race-Condition-Risiken im Simulation-Stack nachgezogen.

**Neue Dateien**
- `backend/app/utils/json_io.py`
- zusätzliches Detailprotokoll: `docu/p0-simulation-json-hardening-protokoll.md`

**Geänderte Dateien**
- `backend/app/services/simulation_runner.py`
- `backend/app/services/simulation_manager.py`
- `backend/app/api/simulation_prepare.py`
- `backend/app/api/simulation_profiles.py`
- `backend/app/api/simulation_history.py`
- `package.json`
- `.github/workflows/ci.yml`

**Umgesetzte Logik**
- gemeinsamer atomic-write/defensive-read Helfer für JSON-Dateien
- `run_state.json` robuster gegen gleichzeitiges Schreiben/Lesen
- `state.json`, `simulation_config.json`, `reddit_profiles.json` und report meta lookups defensiver
- realtime prepare/profile/config polling reagiert toleranter auf temporär unlesbare Dateien
- Scoped-Ruff-Rollout auf weitere stabilisierte Backend-Dateien erweitert

**Zusätzliche Verifikation**
- `cd backend && uv run ruff check app/api/simulation_prepare.py app/api/simulation_profiles.py app/api/simulation_history.py app/services/simulation_manager.py app/services/simulation_runner.py app/utils/json_io.py` → **bestanden**
- `cd backend && uv run pytest tests/test_simulation_runtime.py tests/test_simulation_api_routes.py tests/test_report_manager.py tests/test_embedding_service.py` → **24/24 bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **70 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 21 Warnungen**
  - Frontend-Build **bestanden**

### 9.18 Frontend-Lint-Warnungen Block A abgebaut
Als erster Follow-up-Block nach dem v0.4.1-Plan wurden die verbleibenden Low-Risk-Lint-Warnungen im Frontend bereinigt.

**Geänderte Dateien**
- `frontend/src/components/HistoryDatabase.vue`
- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step3Simulation.vue`
- `frontend/src/components/Step4Report.vue`
- `frontend/src/components/Step5Interaction.vue`
- `frontend/src/views/SimulationRunView.vue`
- `frontend/src/views/Process.vue`

**Umgesetzte Logik**
- ungenutzte Catch-Parameter durch parameterlose `catch { ... }`-Blöcke ersetzt
- ungenutzten `watch`-Import in `Step3Simulation.vue` entfernt
- ungenutztes `emit`-Binding in `Step5Interaction.vue` entfernt
- ungenutzten Map-Index in `Step5Interaction.vue` entfernt
- ungenutztes `link`-Binding in `Process.vue` entfernt

**Messbarer Effekt**
- Frontend-Lint wurde von **0 Fehlern, 21 Warnungen** auf **0 Fehler, 0 Warnungen** reduziert

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

### 9.19 Workspace-Layout-Grundlage gelegt
Danach wurde der erste sichere Schritt für die gemeinsame Frontend-Workspace-Shell umgesetzt.

**Neue Dateien**
- `frontend/src/layouts/WorkspaceLayout.vue`
- `frontend/src/layouts/WorkspaceHeader.vue`
- `frontend/src/layouts/WorkspaceSplit.vue`
- zusätzliches Detailprotokoll: `docu/p0-workspace-layout-protokoll.md`

**Geänderte Datei**
- `frontend/src/views/MainView.vue`

**Umgesetzte Logik**
- gemeinsame Layout-Primitives für Header und Split-Workspace eingeführt
- `MainView.vue` auf die neuen Layout-Bausteine umgestellt
- Routing und fachliche State-Logik unverändert gelassen

**Wichtige Designentscheidung**
- Es wurde bewusst nur **ein** View migriert.
- So bleibt der erste Shell-Schnitt risikoarm und schafft dennoch die Basis für weitere Migrationen (`Process.vue`, `SimulationRunView.vue`, ...).

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

### 9.20 Zweiter Workspace-Layout-Schritt
Danach wurde die neue Workspace-Shell direkt auf einen zweiten zentralen Arbeitsview ausgeweitet.

**Geänderte Datei**
- `frontend/src/views/SimulationRunView.vue`
- Detailprotokoll aktualisiert: `docu/p0-workspace-layout-protokoll.md`

**Umgesetzte Logik**
- `SimulationRunView.vue` nutzt jetzt ebenfalls `WorkspaceLayout`, `WorkspaceHeader` und `WorkspaceSplit`
- Brand / View-Switcher / Status + Quick-Pause bleiben funktional unverändert
- linker Graph-/rechter Workbench-Bereich bleibt in derselben fachlichen Struktur erhalten

**Wichtige Designentscheidung**
- Wieder nur der Shell-Rahmen wurde ersetzt, nicht die innere Simulationslogik.
- So wird die gemeinsame Workspace-Sprache gestärkt, ohne Laufstatus-/Pause-/Routing-Logik zu gefährden.

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**
- `npm run check` → erneut vollständig erfolgreich
- Gesamtstand danach:
  - **70 Backend-Tests bestanden**
  - Frontend-Lint **0 Fehler, 0 Warnungen**
  - Frontend-Build **bestanden**

### 9.21 Gemeinsamen Workspace-Mode-Switcher extrahiert
Als nächster kleiner Shell-Cleanup wurde der View-Mode-Umschalter der Workspace-Screens zentralisiert.

**Neue Datei**
- `frontend/src/layouts/WorkspaceModeSwitch.vue`

**Geänderte Dateien**
- `frontend/src/views/MainView.vue`
- `frontend/src/views/SimulationRunView.vue`
- Detailprotokoll aktualisiert: `docu/p0-workspace-layout-protokoll.md`

**Umgesetzte Logik**
- gemeinsamer `WorkspaceModeSwitch` für `graph` / `split` / `workbench`
- Header-Duplikat in beiden migrierten Workspace-Views entfernt
- View-Mode-Verhalten blieb unverändert

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

### 9.22 Weitere Workspace-Views umgestellt
Danach wurde die gemeinsame Workspace-Shell auf weitere Kernscreens ausgeweitet.

**Geänderte Dateien**
- `frontend/src/views/SimulationView.vue`
- `frontend/src/views/ReportView.vue`
- `frontend/src/views/InteractionView.vue`
- Detailprotokoll aktualisiert: `docu/p0-workspace-layout-protokoll.md`

**Umgesetzte Logik**
- alle drei Views nutzen jetzt `WorkspaceLayout`, `WorkspaceHeader`, `WorkspaceSplit` und `WorkspaceModeSwitch`
- bestehende Brand-/Status-/Split-Logik blieb erhalten
- `SimulationView.vue` behält sein Branch-Panel in derselben fachlichen Position

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

### 9.23 Gemeinsamen Workspace-Step-Status extrahiert
Danach wurde die nächste offensichtliche Header-Duplizierung in den Workspace-Views beseitigt.

**Neue Datei**
- `frontend/src/layouts/WorkspaceStepStatus.vue`

**Geänderte Dateien**
- `frontend/src/views/MainView.vue`
- `frontend/src/views/SimulationView.vue`
- `frontend/src/views/SimulationRunView.vue`
- `frontend/src/views/ReportView.vue`
- `frontend/src/views/InteractionView.vue`
- Detailprotokoll aktualisiert: `docu/p0-workspace-layout-protokoll.md`

**Umgesetzte Logik**
- gemeinsamer Baustein für Schrittzähler + Statusanzeige
- Header-Duplikat in allen Workspace-Kernviews reduziert
- viewspezifische Zusatzcontrols (Pause / Branch) blieben lokal in den jeweiligen Screens

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

### 9.24 Backend-Ruff-Rollout Phase 2
Danach wurde der gescopte Backend-Lint auf einen weiteren low-risk Modulblock ausgedehnt.

**Neue Datei**
- `docu/p0-backend-ruff-rollout-protokoll.md`

**Geänderte Dateien**
- `backend/app/api/runs.py`
- `backend/app/services/graph_memory_updater.py`
- `backend/app/utils/gpu_probe.py`
- `backend/app/storage/search_service.py`
- `backend/tests/test_status.py`
- `backend/tests/test_logging.py`
- `backend/tests/test_neo4j_resilience.py`
- `package.json`
- `.github/workflows/ci.yml`

**Umgesetzte Logik**
- ungenutzte Imports und Variablen bereinigt
- triviale Ruff-Befunde in Tests beseitigt
- die gesäuberten Dateien in den regulären Ruff-Scope aufgenommen

**Zusätzliche Verifikation**
- `cd backend && uv run ruff check app/api/runs.py app/services/graph_memory_updater.py app/utils/gpu_probe.py app/storage/search_service.py tests/test_status.py tests/test_logging.py tests/test_neo4j_resilience.py` → **bestanden**
- `cd backend && uv run pytest tests/test_status.py tests/test_logging.py tests/test_neo4j_resilience.py` → **23/23 bestanden**

### 9.25 Gemeinsamen Workspace-Brand-Link extrahiert
Danach wurde die letzte naheliegende Header-Duplikation in den Workspace-Views beseitigt.

**Neue Datei**
- `frontend/src/layouts/WorkspaceBrandLink.vue`

**Geänderte Dateien**
- `frontend/src/views/MainView.vue`
- `frontend/src/views/SimulationView.vue`
- `frontend/src/views/SimulationRunView.vue`
- `frontend/src/views/ReportView.vue`
- `frontend/src/views/InteractionView.vue`
- Detailprotokoll aktualisiert: `docu/p0-workspace-layout-protokoll.md`

**Umgesetzte Logik**
- einheitlicher Brand-Link über alle Workspace-Screens
- redundante Brand-Styles in den Views entfernt
- Workspace-Shell weiter in kleine Layout-Primitives aufgeteilt

**Zusätzliche Verifikation**
- `cd frontend && npm run lint` → **0 Fehler, 0 Warnungen**
- `cd frontend && npm run build` → **bestanden**

---

## 10. Offene Punkte nach diesem Stand

1. weitere Backend-Ruff-Cluster schrittweise aufnehmen
2. `Process.vue` als Alt-View gegen den neuen Shell-Stand bewerten oder zurückbauen
3. größere Frontend-Strukturthemen jenseits der Workspace-Shell angehen
3. `GraphPanel.vue` weiter zerlegen:
   - Link-Path-/Midpoint-Geometrie
   - Force-Simulation / Renderer
   - Toolbar-/Toggle-/Hint-Bereiche
4. gemeinsames Frontend-Workspace-Layout einführen
5. eventuelle `npm audit`-Nacharbeit separat priorisieren
