# Sub-Slice 35 — Resume/Stop-Test-Coverage (Closes #64)

**Datum:** 2026-05-03
**Layer:** 7 (Run-Registry / API)
**Vorgänger:** Sub-Slice 33 (Implementierung Resume/Stop-Endpoints + HistoryDatabase-Buttons)

## Was

Reine Test-Erweiterung — kein Produktcode-Edit.

### Backend

Neue Datei: `backend/tests/api/test_runs_resume_stop.py` (130 LOC)

6 Tests, alle Negativpfade:

1. `test_resume_unknown_run_returns_404` — gültiges run_id-Format, kein Eintrag → 404
2. `test_resume_unsupported_run_type_returns_409` — run_type=custom_xyz → 409 mit "Unsupported run type"
3. `test_stop_unknown_run_returns_404` — ungültiges Format → 400; gültiges Format, kein Eintrag → 404
4. `test_stop_non_simulation_run_returns_409` — run_type=graph_build → 409 mit "Stop is only supported for simulation_run"
5. `test_stop_simulation_run_without_simulation_id_returns_409` — simulation_run ohne linked_ids.simulation_id → 409 mit "missing simulation_id linkage"
6. `test_resume_response_uses_json_success_envelope` — 409-Pfad liefert `{success:false, error:...}` (handle_api_errors-Decorator)

Fixture-Pattern: identisch zu `test_runs_api_filter_aggregate.py` (Flask-App + Blueprint + tmp_path-RunRegistry).
Keine echten Dispatcher-Calls (SimulationRunner, ProjectManager etc.) — nur Dispatch-Guard-Pfade getestet.

### Frontend

Neue Datei: `frontend/src/components/__tests__/HistoryDatabase.spec.ts` (235 LOC)

4 Tests:

1. Resume-Button ausgeblendet bei `resume_capability.available=false`
2. Resume-Button sichtbar mit korrektem Label bei `available=true`
3. `handleResume` ruft `resumeRun(run_id)` nach confirm=true, löst danach `loadRuns` aus
4. `handleStop`: `window.confirm=false` → `stopRun` nicht aufgerufen; `confirm=true` → aufgerufen

Mock-Strategie: `vi.mock('../../api/runs', ...)` für alle API-Calls; `vi.spyOn(window, 'confirm')` für Confirm-Dialog.

## Warum

Issue #64 war nach Sub-Slice 33 noch offen, weil die Implementierung ohne Test-Coverage geliefert wurde. Dieser Sub-Slice schließt die Lücke.

## Verifikation

```
backend: 6 passed (test_runs_resume_stop.py), 95 passed (tests/api/ gesamt)
frontend: 141 passed (17 test files), npm run check grün
```

## Out of Scope

Echte Happy-Path-Tests für Resume (graph_build, simulation_run, report_generate starten tatsächlich neu) erfordern umfangreiche Fixtures für ProjectManager/SimulationRunner — separater Sub-Slice wenn gewünscht.
