# Slice A2 — Branching-Service extrahieren (Closes #44)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #44 (EPIC-06-ST-04) — Branching-Service extrahieren

## Inventur

`SimulationManager` enthielt drei Methoden zur Branch-Verwaltung in einem 789-LOC-Monolithen:
- `list_branches()` (12 LOC) — Branches mit gemeinsamem Root finden
- `create_branch()` (~140 LOC) — Branch anlegen, Profile/Configs kopieren, Persona-Overrides anwenden, RunRegistry-Eintrag schreiben
- `_apply_persona_overrides()` (~48 LOC) — Reddit-JSON und Twitter-CSV editieren

Akzeptanzkriterium aus #44: *„Branch-Logik in eigener Service-Datei, Persona-Override-Logik separat testbar."* Die Logik war in `simulation_manager.py:544-747` **zusammenhängend**, aber in der falschen Datei.

Externe Aufrufstellen:
- `backend/app/api/simulation_profiles.py:50,72` (`manager.create_branch`, `manager.list_branches`)
- `backend/tests/test_simulation_api_routes.py`, `backend/tests/api/test_simulation_endpoints.py` (API-Routes)
- `backend/tests/services/test_simulation_manager_transitions.py:122` (String-Identifier `"simulation_manager.create_branch"` — refactor-sicher)

## Schnitt

**Funktionsmodul** statt Service-Klasse, um zirkuläre Importe und einen separaten Konstruktor mit explizit übergebenen Manager-Dependencies zu vermeiden. Manager-API bleibt stabil — Caller in `simulation_profiles.py` und Tests müssen nicht angefasst werden.

```python
# backend/app/services/branching_service.py
def list_branches(manager: SimulationManager, simulation_id: str) -> List[SimulationState]: ...
def create_branch(manager, simulation_id, branch_name, *, copy_profiles=True, ...) -> SimulationState: ...
def _apply_persona_overrides(manager, simulation_id, sim_dir, removals, additions) -> None: ...
```

`SimulationStatus` wird in `create_branch()` per **lazy import** geladen — `simulation_manager` importiert `branching_service` (für die Delegation), umgekehrte Top-Level-Imports würden zirkulär. Type-Hints nutzen `from __future__ import annotations` plus `TYPE_CHECKING`-Block, damit IDE-Tooling die Typen weiterhin auflösen kann.

## Änderungen

**Neu:** `backend/app/services/branching_service.py` (230 LOC)

**Geändert:** `backend/app/services/simulation_manager.py`
- Drei Methoden zu 1-Zeilen-Delegationen reduziert
- `_apply_persona_overrides()` komplett entfernt (jetzt im Service, nur intern aufgerufen)
- Imports aufgeräumt: `shutil`, `Config`, `ArtifactLocator`, `RunRegistry` nicht mehr benötigt
- **Datei:** 789 → 622 LOC (−21 %)

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean (3 unused-Import-Warnings durch Cleanup behoben)
- Backend Tests: **517 passed**, 2 skipped (Redis-Integration ohne lokalen Redis)
- Frontend Lint: 0 errors, 1 vorhandene Warning in `Step4Report.vue` (nicht in diesem Slice)
- Frontend Tests: **40 passed** (4+1 Test-Files, neue `markdown.spec.js` von Issue #103)
- Frontend Build: vite, 738 modules, ok

Branching-spezifische Tests, die das Refactor abdecken:
- `test_simulation_api_routes.py::test_create_branch_*` (4 Tests)
- `test_simulation_endpoints.py::test_create_branch_*` (3 Tests)
- `test_simulation_manager_transitions.py::test_*_create_branch` (string-basiert, refactor-sicher)

## Konsequenz für v0.9.0

Issue #44 abgeschlossen. Verbleibender v0.9.0-Backlog: **10 echte Issues** (EPIC-06 ×2, EPIC-07 ×5, EPIC-08 ×3 — wobei EPIC-07 nach Issue #103 inhaltlich bereits stark vorangetrieben wurde, eigene Inventur folgt vor Pfad C).

## Folge-Slice

Slice A3 (Issue #45) — Report-Models aus `report_agent.py` in `models/report.py` extrahieren. **Vorher** Inventur, weil Issue #103 (S3b–S6) `report_agent.py` umfangreich umgebaut hat — Report-Models könnten retrospektiv schon in einer separaten Datei liegen.
