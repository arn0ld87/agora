# P0-Simulation-API-Split-Protokoll

**Start:** 2026-04-22  
**Ziel:** `backend/app/api/simulation.py` kontrolliert, inkrementell und testbar aufspalten, ohne Routing oder Produktverhalten zu brechen.

---

## 1. Ausgangslage

Datei:
- `backend/app/api/simulation.py`

Größe laut Analyse:
- **3251 LOC**

Aktuell enthaltene Route-Gruppen:
- Modell-/Status-Hilfen
- Entity-Read-Endpunkte
- Simulation anlegen / laden / listen
- Prepare-Flow
- Branching
- Profile und Config
- Run Control
- Logs / Actions / Timeline / Posts / Comments
- Interviews
- Env-Steuerung

---

## 2. Split-Strategie

Der Split erfolgt **nicht** als Big Bang, sondern in sicheren Stufen.

### Stufe 1 — sichere, schwach gekoppelte Routen herauslösen
Zuerst werden logisch relativ unabhängige Gruppen extrahiert:

1. `available-models`
2. Entity-Read-Endpunkte
3. grundlegende Lifecycle-Routen:
   - `create_simulation`
   - `get_simulation`
   - `list_simulations`

### Stufe 2 — Helper und gemeinsame Utilities konsolidieren
Danach:
- gemeinsame Kontext-/Storage-Helfer
- gemeinsame Response-/Validation-Patterns

### Stufe 3 — größere Fachblöcke aufteilen
Dann schrittweise:
- Prepare
- Run Control
- Profiles / Config / Branches
- Interviews / Artifacts / Env

---

## 3. Architekturregel für den Split

- Das bestehende Blueprint `simulation_bp` bleibt erhalten.
- Neue Module registrieren ihre Routen auf demselben Blueprint.
- `backend/app/api/__init__.py` importiert die neuen Module zusätzlich.
- Das Verhalten der URL-Pfade bleibt unverändert.

---

## 4. Verifikationsregel

Nach jedem Split-Schritt mindestens:

```bash
cd backend && uv run pytest
cd frontend && npm run build
```

Wenn betroffene P0-Dateien verändert wurden zusätzlich:

```bash
npm run check
```

---

## 5. Laufende Dokumentation

### 5.1 Analyse des Routeninventars
Per AST ausgelesene Route-Gruppen (Auszug):
- `/available-models`
- `/entities/<graph_id>`
- `/entities/<graph_id>/<entity_uuid>`
- `/entities/<graph_id>/by-type/<entity_type>`
- `/create`
- `/prepare`
- `/prepare/status`
- `/<simulation_id>`
- `/list`
- `/history`
- `/<simulation_id>/branch`
- `/<simulation_id>/branches`
- `/<simulation_id>/profiles`
- `/<simulation_id>/config`
- `/start`
- `/stop`
- `/<simulation_id>/pause`
- `/<simulation_id>/resume`
- `/<simulation_id>/run-status`
- `/interview`
- `/env-status`
- `/close-env`

### 5.2 Erste konkrete Zielmodule
Für Stufe 1 werden folgende neuen Module vorgesehen:
- `backend/app/api/simulation_common.py`
- `backend/app/api/simulation_entities.py`
- `backend/app/api/simulation_lifecycle.py`

Diese Auswahl ist bewusst konservativ und risikoarm.

### 5.3 Umgesetzter Split-Schritt 1

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

**Inhalt des Split-Schritts**
- gemeinsame Simulation-API-Helfer nach `simulation_common.py` verschoben:
  - Logger
  - RunRegistry-Instanz
  - Interview-Prompt-Normalisierung
  - Run-Artefakt-Helfer
  - Resume-Capability-Helfer
  - Storage-Zugriffshilfe
- Entity-Lese-Endpunkte nach `simulation_entities.py` verschoben:
  - `/entities/<graph_id>`
  - `/entities/<graph_id>/<entity_uuid>`
  - `/entities/<graph_id>/by-type/<entity_type>`
- Lifecycle-/Metadaten-Endpunkte nach `simulation_lifecycle.py` verschoben:
  - `/available-models`
  - `/create`
  - `/<simulation_id>`
  - `/list`
- `backend/app/api/__init__.py` importiert die neuen Module explizit, damit die Routen weiter auf demselben Blueprint registriert werden.
- `backend/app/api/simulation.py` wurde um die verschobenen Routen reduziert und importiert die gemeinsamen Helfer zurück.

### 5.4 Verifikation für Split-Schritt 1

#### Targeted API-Smoke-Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_api_routes.py
```

Ergebnis:
- **4/4 Tests bestanden**
- verifiziert wurden:
  - Route `/available-models` registriert
  - Entity-Validierung bleibt aktiv
  - `/create` verlangt weiterhin `project_id`
  - `/list` bleibt registriert

#### Scoped Ruff-Check nach Split
Befehl:
```bash
cd backend && uv run ruff check app/models/project.py app/services/run_registry.py app/utils/validation.py app/api/simulation_common.py app/api/simulation_entities.py app/api/simulation_lifecycle.py tests/test_project_manager.py tests/test_run_registry.py tests/test_validation.py tests/test_simulation_api_routes.py
```

Ergebnis:
- **alle Checks bestanden**

### 5.5 Zweiter umgesetzter Split-Schritt

**Neue Datei**
- `backend/app/api/simulation_prepare.py`

**Geänderte Dateien**
- `backend/app/api/__init__.py`
- `backend/app/api/simulation.py`
- `backend/tests/test_simulation_api_routes.py`
- `package.json`
- `.github/workflows/ci.yml`

**Herausgelöste Logik**
- `_check_simulation_prepared`
- `/prepare`
- `/prepare/status`

**Wichtige Detailentscheidung**
- `_check_simulation_prepared` wurde in das neue Prepare-Modul verschoben und in `simulation.py` zurückimportiert, weil andere verbleibende Endpunkte diese Prüfung weiterhin verwenden.
- Dadurch bleibt das Verhalten stabil, ohne den nächsten Split künstlich zu blockieren.

### 5.6 Verifikation für Split-Schritt 2

#### Targeted API-Smoke-Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_api_routes.py
```

Ergebnis:
- **6/6 Tests bestanden**
- zusätzlich verifiziert:
  - `/prepare` verlangt weiterhin `simulation_id`
  - `/prepare/status` verlangt weiterhin `task_id` oder `simulation_id`

#### Voller Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **55 bestanden**
- Frontend Lint → **0 Fehler, 23 Warnungen**
- Frontend Build → **bestanden**

### 5.7 Dritter umgesetzter Split-Schritt

**Neue Datei**
- `backend/app/api/simulation_profiles.py`

**Geänderte Dateien**
- `backend/app/api/__init__.py`
- `backend/app/api/simulation.py`
- `backend/tests/test_simulation_api_routes.py`
- `package.json`
- `.github/workflows/ci.yml`

**Herausgelöste Logik**
- Branch-Endpunkte
- Profile-Endpunkte
- Config-Endpunkte
- Script-Download-Endpunkt
- zugehörige Hilfsfunktionen für Profile-Dateien

### 5.8 Verifikation für Split-Schritt 3

#### Targeted API-Smoke-Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_api_routes.py
```

Ergebnis:
- **8/8 Tests bestanden**
- zusätzlich verifiziert:
  - Branch-Erstellung verlangt `branch_name`
  - Config-Route behält ihren ID-Guard

#### Voller Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **57 bestanden**
- Frontend Lint → **0 Fehler, 23 Warnungen**
- Frontend Build → **bestanden**

### 5.9 Vierter umgesetzter Split-Schritt

**Neue Datei**
- `backend/app/api/simulation_run.py`

**Geänderte Dateien**
- `backend/app/api/__init__.py`
- `backend/app/api/simulation.py`
- `backend/tests/test_simulation_api_routes.py`
- `package.json`
- `.github/workflows/ci.yml`

**Herausgelöste Logik**
- Start/Stop/Pause/Resume
- Console-Log / Run-Status / Run-Detail
- Actions / Timeline / Agent-Stats
- Env-Status / Close-Env
- gemeinsamer `_simulation_dir`-Helper

### 5.10 Verifikation für Split-Schritt 4

#### Targeted API-Smoke-Tests
Befehl:
```bash
cd backend && uv run pytest tests/test_simulation_api_routes.py
```

Ergebnis:
- **11/11 Tests bestanden**
- zusätzlich verifiziert:
  - `/start` verlangt `simulation_id`
  - `/<simulation_id>/pause` behält ID-Validation
  - `/env-status` verlangt `simulation_id`

#### Voller Gesamtcheck
Befehl:
```bash
npm run check
```

Ergebnis:
- Backend Ruff (scoped) → **bestanden**
- Backend Tests → **60 bestanden**
- Frontend Lint → **0 Fehler, 23 Warnungen**
- Frontend Build → **bestanden**

### 5.11 Nächste sichere Split-Kandidaten
Nach vier erfolgreichen Splits sind die nächsten sinnvollen Kandidaten:
1. Interview-/Artifact-Endpunkte
2. verbleibende Database-Query-Endpunkte (`posts`, `comments`)
3. verbleibende History-/Standalone-Helfer
