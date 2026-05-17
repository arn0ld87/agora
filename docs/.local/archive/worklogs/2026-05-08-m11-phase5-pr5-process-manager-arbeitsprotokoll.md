# M11 Phase 5 PR 5 — `process_manager`-Extraktion aus `SimulationRunner`

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5-pr5-process-manager`
**Basis-Commit:** `ef9f5b6`

---

## Was wurde gemacht?

Subprocess-Lifecycle- und Cleanup-Logik wurde aus `SimulationRunner` in ein neues
Modul `backend/app/services/sim/process_manager.py` extrahiert. `simulation_runner.py`
behält für alle extrahierten Symbole dünne Delegations-Klassenmethoden, damit
bestehende Call-Sites (API-Blueprints, atexit/Signal-Handler, Monkeypatch-Stubs) unverändert
weiterarbeiten.

TDD-Reihenfolge eingehalten: Tests zuerst (RED), dann Implementierung (GREEN).

Das Modul folgt dem Re-Export-/Delegations-Pattern, das PR 2–4 etabliert haben.

---

## Wohin wurden welche Symbole verschoben?

| Vorher (in `SimulationRunner` / module-level) | Nachher (Modul-Funktion in `process_manager`) | Externalisierung |
|---|---|---|
| `_compute_oasis_db_path(sim_dir)` (module-level) | `_compute_oasis_db_path(sim_dir)` | unverändert; re-export in `simulation_runner` für Backward-Compat |
| `_inject_oasis_db_env(env, sim_dir)` (module-level) | `_inject_oasis_db_env(env, sim_dir)` | unverändert; re-export in `simulation_runner` für Backward-Compat |
| `start_simulation(cls, ...)` | `start_simulation(simulation_id, platform, *, run_state_dir, scripts_dir, processes, action_queues, monitor_threads, stdout_files, stderr_files, graph_memory_enabled, get_run_state, save_state, on_monitor_start, write_control_state, get_config, config_exists, setup_graph_memory, max_rounds)` | gesamte Logik inkl. Validierung, State-Init, Subprocess-Launch |
| `_terminate_process(cls, process, simulation_id, timeout)` | `terminate_process(process, simulation_id, timeout=10)` | kein `cls.*`; SIGTERM/SIGKILL-Pfade unverändert |
| `stop_simulation(cls, simulation_id)` | `stop_simulation(simulation_id, *, processes, graph_memory_enabled, get_run_state, save_state, stop_graph_memory_updater)` | `cls.*`-Felder als KW-Parameter |
| `cleanup_all_simulations(cls)` | `cleanup_all_simulations(*, processes, stdout_files, stderr_files, graph_memory_enabled, action_queues, get_run_state, save_state, stop_all_graph_memory, update_store_state, cleanup_done_flag)` | `_cleanup_done`-Flag als `List[bool]`-Referenz übergeben |
| `register_cleanup(cls)` | `register_cleanup(*, cleanup_callable)` | atexit + Signal-Logik + Reloader-Guard erhalten; Cleanup-Action via Callback injiziert |
| `get_running_simulations(cls)` | `get_running_simulations(*, processes)` | kein `cls.*`; simpel |

---

## Backward-Compat

### Re-Exporte in `simulation_runner.py`

```python
from .sim.process_manager import _compute_oasis_db_path as _compute_oasis_db_path  # noqa: PLC0414
from .sim.process_manager import _inject_oasis_db_env as _inject_oasis_db_env  # noqa: PLC0414
from .sim.process_manager import terminate_process as _terminate_process_fn
from .sim.process_manager import start_simulation as _start_simulation_fn
from .sim.process_manager import stop_simulation as _stop_simulation_fn
from .sim.process_manager import cleanup_all_simulations as _cleanup_all_simulations_fn
from .sim.process_manager import register_cleanup as _register_cleanup_fn
from .sim.process_manager import get_running_simulations as _get_running_simulations_fn
```

### Neue Hilfs-Klassenmethoden in `SimulationRunner`

`_setup_graph_memory(cls, sim_id, enable, graph_id, storage)` und
`_mark_store_state_stopped(cls, simulation_id)` wurden als separate Klassenmethoden
extrahiert, damit `cleanup_all_simulations` und `start_simulation` als schlanke
Delegations-Wrapper bleiben können.

### `cls.*`-Felder als KW externalisiert

| `cls.*`-Feld | KW-Parameter | Übergabe in Delegation |
|---|---|---|
| `cls.RUN_STATE_DIR` | `run_state_dir` | direkt |
| `cls.SCRIPTS_DIR` | `scripts_dir` | direkt |
| `cls._processes` | `processes` | by reference (Python-Dict) |
| `cls._action_queues` | `action_queues` | by reference |
| `cls._monitor_threads` | `monitor_threads` | by reference |
| `cls._stdout_files` | `stdout_files` | by reference |
| `cls._stderr_files` | `stderr_files` | by reference |
| `cls._graph_memory_enabled` | `graph_memory_enabled` | by reference |
| `cls._cleanup_done` | `cleanup_done_flag` | `List[bool]` by reference |
| `cls.get_run_state` | `get_run_state` | Callable |
| `cls._save_run_state` | `save_state` | Callable |

---

## Lifecycle-Aspekte

### atexit

`register_cleanup` in `process_manager.py` ruft `atexit.register(cleanup_callable)`.
Der `cleanup_callable` ist `SimulationRunner.cleanup_all_simulations`, das selbst
an `_cleanup_all_simulations_fn` delegiert.

### SIGTERM / SIGINT / SIGHUP

Alle drei Signal-Handler werden in `register_cleanup` registriert. Verhalten:
- SIGTERM → `cleanup_handler(signum, frame)` → `cleanup_callable()` → Original-Handler
- SIGINT → analog
- SIGHUP (Unix only, `hasattr(signal, 'SIGHUP')` Guard) → analog; Default `sys.exit(0)` bei nicht-callable Original-Handler

### Reloader-Child-Guard

```python
is_reloader_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
is_debug_mode = os.environ.get("FLASK_DEBUG") == "1" or os.environ.get("WERKZEUG_RUN_MAIN") is not None
if is_debug_mode and not is_reloader_process:
    _cleanup_registered = True
    return
```

Verhalten identisch mit dem Original in `simulation_runner.py`. Registrierung
erfolgt nur im Werkzeug-Child-Prozess, nicht im Parent-Reloader.

### `_cleanup_done` Flag

Ursprünglich ein klassenattribut `_cleanup_done: bool = False`. Nach PR 5 als
`_cleanup_done: List[bool] = [False]` auf `SimulationRunner` — die Referenz auf
die Liste wird als `cleanup_done_flag` an `cleanup_all_simulations` übergeben.
Dies ermöglicht Mutation ohne `nonlocal` und ohne `global`.

---

## Tests

### Baseline

- 1572 passed, 9 skipped (nach PR 4)

### Neue Tests

Datei: `backend/tests/services/sim/test_process_manager.py` (252 LOC)

| Test | Beschreibung |
|---|---|
| `TestComputeOasisDbPath::test_returns_sim_specific_path` | Pfad enthält `oasis_db/social_media.db` |
| `TestComputeOasisDbPath::test_creates_directory` | Verzeichnis wird angelegt |
| `TestComputeOasisDbPath::test_is_idempotent` | Mehrfachaufruf liefert gleichen Pfad |
| `TestInjectOasisDbEnv::test_no_override_when_already_set` | Gesetztes OASIS_DB_PATH wird nicht überschrieben |
| `TestInjectOasisDbEnv::test_sets_when_unset` | Nicht gesetzt → sim-spezifischen Pfad setzen |
| `TestTerminateProcess::test_unix_sigterm_path` | Unix: os.killpg(pgid, SIGTERM) wird aufgerufen |
| `TestTerminateProcess::test_unix_sigkill_on_timeout` | TimeoutExpired → SIGKILL-Eskalation |
| `TestGetRunningSimulations::test_filters_dead_processes` | poll()==None → running; poll()==0 → not running |
| `TestGetRunningSimulations::test_empty_processes` | Leeres Dict → [] |
| `TestGetRunningSimulations::test_all_running` | Alle laufend → alle in Rückgabe |
| `TestRegisterCleanup::test_registers_atexit_handler` | atexit.register wird aufgerufen |
| `TestRegisterCleanup::test_reloader_child_guard_skips_in_debug_mode` | FLASK_DEBUG=1 ohne WERKZEUG_RUN_MAIN → keine Registrierung |

### Nach PR 5

- 1584 passed, 9 skipped (+12 neue Tests)

---

## LOC-Diff-Tabelle

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `backend/app/services/simulation_runner.py` | 986 | 508 | −478 |
| `backend/app/services/sim/process_manager.py` | (neu) | 582 | +582 |
| `backend/tests/services/sim/test_process_manager.py` | (neu) | 252 | +252 |

---

## Phase 5 ABGESCHLOSSEN — Zusammenfassung der 5 PRs

| PR | Modul | LOC raus aus simulation_runner.py |
|---|---|---|
| PR 1 | `run_state_store` | −178 |
| PR 2 | `action_log_reader` | −198 |
| PR 3 | `monitor_thread` | −170 |
| PR 4 | `interview_client` | −292 |
| PR 5 | `process_manager` | −478 |
| **Summe** | | **−1316** |

`simulation_runner.py`: 1904 LOC (Ausgangsbasis) → 508 LOC (nach PR 5) = **Reduktion 73 %**

---

## Verifikations-Ergebnisse

- `pytest -x -q`: 1584 passed, 9 skipped
- `pytest tests/contracts/ -x -v`: 71 passed
- `pytest tests/services/sim/ -v`: 29 passed (12 neue + 17 bestehende)
- `pytest tests/test_simulation_runner_oasis_db_path.py -v`: 4 passed (via Re-Export)
- `ruff check app/ tests/`: All checks passed
- `mypy app`: Success: no issues found in 125 source files (+1 neues Modul vs Baseline 124)
- `git diff --exit-code schemas/`: kein Drift

---

## Risiken / offene Punkte

- **gevent ↔ OASIS-Subprozess:** `subprocess.Popen` läuft bei aktivem `gevent.monkey.patch_all()` durch den Patch. Bei jedem Slice der OASIS anfasst: per `scripts/verify-deploy.sh` smoken. Der `process_manager`-Code selbst ist gevent-agnostisch; Risiko liegt im Deployment, nicht im Refactor.
- **M11 Phase 5 ist abgeschlossen.** Die `sim/`-Submodule decken jetzt alle fünf Verantwortlichkeiten von `simulation_runner.py` ab. Zukünftige Features können direkt auf den Submodulen aufbauen, ohne das `SimulationRunner`-Monolith zu erweitern.
