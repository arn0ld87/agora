# M11 Phase 5 PR 1 — Arbeitsprotokoll: `run_state_store`-Extraktion

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5-pr1-run-state-store`
**Worker:** Agora-Backend-Refactor-Worker (Claude Sonnet 4.6)

---

## Was wurde extrahiert

Aus `backend/app/services/simulation_runner.py` (vorher 1904 LOC) wurden folgende Symbole herausgeschnitten:

### Klassen (Wert-Objekte)

| Symbol | Art | Beschreibung |
|---|---|---|
| `RunnerStatus` | `str, Enum` | Alle zulässigen Laufzustände (IDLE, STARTING, RUNNING, PAUSED, STOPPING, STOPPED, COMPLETED, FAILED, READY) |
| `AgentAction` | `@dataclass` | Wert-Objekt für eine einzelne Agent-Aktion mit `to_dict()` |
| `RoundSummary` | `@dataclass` | Wert-Objekt für eine Rundenübersicht mit `to_dict()` |
| `SimulationRunState` | `@dataclass` | Vollständiger Laufzustand einer Simulation mit `add_action()`, `to_dict()`, `to_detail_dict()` |

### Module-Level-Funktionen (I/O-Helper)

| Neue Funktion | Vorher | Beschreibung |
|---|---|---|
| `load_run_state(run_id, base_dir)` | `SimulationRunner._load_run_state()` | Deserialisiert `run_state.json` |
| `save_run_state(state, base_dir, *, event_bus_publish, run_registry_sync)` | `SimulationRunner._save_run_state()` | Serialisiert + persistiert; Side-Effects als Callbacks |
| `read_console_log(run_id, base_dir, *, max_lines)` | `SimulationRunner.get_console_log()` (inliner) | Liest `simulation.log`; gibt `list[str]` zurück |
| `cleanup_run_logs(run_id, base_dir)` | `SimulationRunner.cleanup_simulation_logs()` | Löscht Log- und State-Dateien |

---

## Wohin

Neues Sub-Package: `backend/app/services/sim/`

- `backend/app/services/sim/__init__.py` — Modul-Marker
- `backend/app/services/sim/run_state_store.py` — alle 4 Klassen + 4 Module-Funktionen

---

## Wie wurde Backward-Compat gewährleistet

`simulation_runner.py` re-exportiert alle 4 Klassen via explizite Alias-Imports (PEP 484 Konvention, satisfies mypy `no-implicit-reexport`):

```python
from .sim.run_state_store import AgentAction as AgentAction
from .sim.run_state_store import RoundSummary as RoundSummary
from .sim.run_state_store import RunnerStatus as RunnerStatus
from .sim.run_state_store import SimulationRunState as SimulationRunState
```

Die Methoden `SimulationRunner.get_run_state`, `SimulationRunner._load_run_state`, `SimulationRunner._save_run_state`, `SimulationRunner.get_console_log` und `SimulationRunner.cleanup_simulation_logs` bleiben als Methoden erhalten und delegieren intern:

- `_load_run_state` → `load_run_state(simulation_id, cls.RUN_STATE_DIR)`
- `_save_run_state` → `_save_run_state_fn(state, cls.RUN_STATE_DIR, event_bus_publish=_publish, run_registry_sync=_registry_sync)` mit zwei lokal definierten Closures, die `event_bus` und `RunRegistry` in `simulation_runner.py` halten
- `get_console_log` → `read_console_log(simulation_id, cls.RUN_STATE_DIR)` + Response-Aufbau
- `cleanup_simulation_logs` → `cleanup_run_logs(simulation_id, cls.RUN_STATE_DIR)` + In-Memory-Cache-Eviction

`app/services/__init__.py` bleibt unverändert — importiert weiterhin alle 4 Symbole aus `simulation_runner`.

---

## Design-Entscheidungen

- **Keine direkten Imports auf `event_bus` oder `RunRegistry` in `run_state_store.py`:** Side-Effects werden als optionale `Callable`-Parameter übergeben. Das hält das neue Modul testbar ohne Event-Bus-Setup.
- **`resolve_default_store()` wird lazy per Function-Call importiert** (gleiche Konvention wie das bestehende `_store()` Helper in `simulation_runner.py`).
- **`read_console_log` gibt `list[str]` zurück** (pure I/O), während `SimulationRunner.get_console_log` weiterhin das Response-Dict mit Paginierungs-Feldern aufbaut. Kein Verhaltens-Diff für API-Aufrufer.

---

## Tests, die grün sind

### Targeted Tests (höchster Re-Export-Druck laut Schnittanalyse)

| Test-Datei | Ergebnis | Count |
|---|---|---|
| `tests/test_simulation_runner_oasis_db_path.py` | GRÜN | 4 passed |
| `tests/test_simulation_metrics_export.py` | GRÜN | 7 passed |
| `tests/test_report_manager.py` | GRÜN | 12 passed |
| `tests/services/test_compare_service.py` | GRÜN | 7 passed |

### Volltest

```
1555 passed, 9 skipped, 7 deselected in 65.44s
```

(9 skipped: 2× Redis nicht erreichbar, 7× docker-compose-Snapshot ohne `.env`)

### Static Analysis

- `ruff check app/ tests/` — **All checks passed**
- `mypy app` — **Success: no issues found in 121 source files**

### Schema-Dump

```
uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

Kein Schema-Drift. Alle 11 Schemas unverändert.

---

## LOC-Reduktion `simulation_runner.py`

| Zustand | LOC |
|---|---|
| Vorher | 1904 |
| Nachher | 1647 |
| Reduktion | −257 LOC (−13,5 %) |

Ziel war ≥150 LOC, idealerweise ~250 — Ergebnis: 257 LOC raus, Ziel übertroffen.

---

## Geänderte Dateien (git diff --stat)

```
 CHANGELOG.md                                        |   3 +
 backend/app/services/sim/__init__.py                |   1 +
 backend/app/services/sim/run_state_store.py         | ~310 +
 backend/app/services/simulation_runner.py           | 1647 (war 1904, -257)
 docu/2026-05-08-m11-phase5-pr1-run-state-store-arbeitsprotokoll.md | neu
```

5 Dateien: 3 neu + simulation_runner.py geändert + CHANGELOG.md geändert.
