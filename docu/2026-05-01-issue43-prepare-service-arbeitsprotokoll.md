# Slice B2 — Prepare-Service extrahieren (Closes #43)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #43 (EPIC-06-ST-03) — Prepare-Service extrahieren

## Inventur

`SimulationManager.prepare_simulation()` war 244 LOC monolithisch und mit dem Manager als Methode verzahnt, obwohl das Issue (Aufwand: L) eine Service-Trennung mit drei klaren Phasen forderte:

- **Phase 1 (Z. 332-377):** Entity-Read und -Filter via `EntityReader.filter_defined_entities`, optional `max_agents`-Cap, Update von `state.entities_count` + `entity_types`.
- **Phase 2 (Z. 379-463):** OASIS-Profile-Generierung mit `OasisProfileGenerator`, parallel, Realtime-Save, Reddit-JSON + Twitter-CSV.
- **Phase 3 (Z. 465-522):** LLM-Config-Generierung via `SimulationConfigGenerator`, atomare Persistenz im `ArtifactStore`.

Plus FSM-Übergänge PREPARING/READY/FAILED am Anfang/Ende und im Error-Pfad.

## Schnittentscheidung

**Funktionsmodul** `backend/app/services/prepare_service.py` mit drei Phasen-Helpern und einem Top-Level-Orchestrator. Symmetrisch zum bereits etablierten `branching_service`-Pattern (Slice A2). Manager wird zur 1-Methoden-Delegation.

```python
prepare_service.prepare_simulation(
    manager,                # SimulationManager-Instanz für _set_status, _store, _get_simulation_dir
    simulation_id, simulation_requirement, document_text,
    *, defined_entity_types=…, use_llm_for_profiles=…,
    progress_callback=…, parallel_profile_count=…,
    storage=…, llm_model=…, language=…, max_agents=…,
) -> SimulationState
```

Phasen-Funktionen (modul-private, `_`-Prefix):

- `_phase_read_entities(state, storage, defined_entity_types, max_agents, progress_callback) -> FilteredEntities`
- `_phase_generate_profiles(state, storage, filtered, sim_dir, *, llm_model, language, use_llm_for_profiles, parallel_profile_count, progress_callback) -> List[Profile]`
- `_phase_generate_config(manager, state, simulation_id, simulation_requirement, document_text, filtered, *, llm_model, language, progress_callback) -> None`

Manager-Referenz wird nur in Phase 3 gebraucht (für `manager._store.write_json`) und im Orchestrator (für `_set_status` und `_get_simulation_dir`). Phase 1 + 2 sind manager-frei → besser für Unit-Tests.

`SimulationStatus` wird im Orchestrator lazy importiert (Zirkularitäts-Schutz wie bei `branching_service`).

## Änderungen

### `backend/app/services/prepare_service.py` (+376 LOC, neu)
Drei Phasen-Funktionen + Orchestrator + Modul-Docstring.

### `backend/app/services/simulation_manager.py` (+15 / −233 LOC)
- `prepare_simulation()` zur 14-Zeilen-Delegation reduziert
- `import json` entfernt (wurde nur in Phase 3 für `json.loads(sim_params.to_json())` benutzt — jetzt im prepare_service)
- `from .entity_reader import EntityReader` entfernt
- `from .oasis_profile_generator import OasisProfileGenerator` entfernt
- `from .simulation_config_generator import SimulationConfigGenerator` entfernt
- `from . import branching_service, prepare_service` (Sammel-Import)
- **Datei: 622 → 403 LOC (−35 %)**

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean
- Backend Tests: **520 passed**, 2 skipped (Redis)
- Frontend Lint: 0 errors
- Frontend Tests: **40 passed**
- Frontend Build: vite, ok

Behavior-Coverage durch bestehende Tests:
- `test_simulation_runtime.py` — End-to-End Prepare-Flow mit echtem Storage-Mock
- `test_simulation_api_routes.py` — API-Aufrufe `/prepare` mit Validation
- `test_simulation_metrics_export.py` — Status-Übergänge nach Prepare
- Behavior-Tests in `tests/services/test_simulation_manager_transitions.py`

## Akzeptanzkriterien #43

- [x] `SimulationManager` wird orchestratorischer und kleiner — von 622 auf 403 LOC (−35 %), nur noch dünne Delegations für `prepare_simulation`/`list_branches`/`create_branch`

## Konsequenz für v0.9.0

Issue #43 abgeschlossen — **EPIC-06 vollständig durch (4/4 Issues)**.

Verbleibender v0.9.0-Backlog: **5 echte Issues** (EPIC-07 ×2: #47/#48; EPIC-08 ×3: #50/#51/#52).

## LOC-Bilanz `simulation_manager.py` über v0.9.0

| Stand | LOC | Δ |
|---|---|---|
| Pre-A (v0.8.0) | 789 | — |
| Nach A2 (#44 Branching) | 622 | −167 (−21 %) |
| Nach B2 (#43 Prepare) | 403 | −219 (−35 %) |
| **Gesamt v0.9.0** | | **−386 (−49 %)** |

Manager ist jetzt ein dünner Orchestrator: State-Persist + Status-Guards + drei delegierende Methoden.

## Folge-Slice

Open. PLAN.md-Reihenfolge nach B2 wäre Pfad C (#47 Tools, #48 Prompts) oder direkt EPIC-08 (#52 DTOs am leichtesten, #50 Storage-Split größter Brocken).
