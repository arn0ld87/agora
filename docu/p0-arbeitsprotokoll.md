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

---

## 10. Offene Punkte nach diesem Stand

1. Backend-Ruff schrittweise auf weitere Module ausweiten
2. Frontend-Warnungen gezielt abbauen
3. weitere Aufspaltung von `simulation.py`:
   - `prepare`
   - run control
   - profiles/config
   - interviews/artifacts/env
4. `GraphPanel.vue`-Zerlegung nachziehen
5. eventuelle `npm audit`-Nacharbeit separat priorisieren
