# M11 Phase 5 PR 4 — `interview_client`-Extraktion aus `SimulationRunner`

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5-pr4-interview-client`
**Basis-Commit:** `b177cd9`

---

## Was wurde gemacht?

Acht Interview-/IPC-Methoden wurden aus `SimulationRunner` in ein neues Modul
`backend/app/services/sim/interview_client.py` extrahiert. `simulation_runner.py`
behält für alle acht Methoden dünne Delegations-Klassenmethoden, damit
bestehende Call-Sites (API-Blueprints, Monkeypatch-Stubs in Tests) unverändert
weiterarbeiten.

Das Modul folgt dem Re-Export-/Delegations-Pattern, das PR 2 (`action_log_reader`)
und PR 3 (`monitor`) etabliert haben:
- Top-Level-Import-Aliase in `simulation_runner.py` (`_check_env_alive_fn`, …)
- Delegations-Klassenmethoden rufen den Alias auf und reichen `cls.RUN_STATE_DIR` als KW-Argument `run_state_dir` durch
- Kein Import von `simulation_runner` aus dem Sub-Modul (verhindert Circular-Import)

---

## Wohin wurden welche Symbole verschoben?

| Vorher (Klassenmethode auf `SimulationRunner`) | Nachher (Modul-Funktion in `interview_client`) | Externalisierung |
|---|---|---|
| `check_env_alive(cls, simulation_id)` | `check_env_alive(simulation_id, *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir` |
| `get_env_status_detail(cls, simulation_id)` | `get_env_status_detail(simulation_id)` | nutzt nur `resolve_default_store()`, kein `cls.*` |
| `interview_agent(cls, simulation_id, agent_id, prompt, platform, timeout)` | `interview_agent(..., *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir` |
| `interview_agents_batch(cls, simulation_id, interviews, platform, timeout)` | `interview_agents_batch(..., *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir` |
| `interview_all_agents(cls, simulation_id, prompt, platform, timeout)` | `interview_all_agents(..., *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir`; ruft jetzt `interview_agents_batch` direkt im Modul |
| `close_simulation_env(cls, simulation_id, timeout)` | `close_simulation_env(simulation_id, timeout, *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir` |
| `_get_interview_history_from_db(cls, db_path, platform_name, agent_id, limit)` | `_get_interview_history_from_db(db_path, platform_name, agent_id, limit)` | kein `cls.*`; `sqlite3`-Import auf Modul-Level |
| `get_interview_history(cls, simulation_id, platform, agent_id, limit)` | `get_interview_history(simulation_id, platform, agent_id, limit, *, run_state_dir)` | `cls.RUN_STATE_DIR` als `run_state_dir` |

---

## Backward-Compat

### Delegations-Klassenmethoden

Alle acht Methoden bleiben auf `SimulationRunner` mit identischer Signatur (inklusive
Default-Werten). Die Top-Level-Imports in `simulation_runner.py`:

```python
from .sim.interview_client import check_env_alive as _check_env_alive_fn
from .sim.interview_client import get_env_status_detail as _get_env_status_detail_fn
# … (8 Aliase gesamt)
```

### Entfernte Imports in `simulation_runner.py`

- `from .simulation_ipc import SimulationIPCClient` — war nach PR 4 ungenutzt (nur in `interview_client.py` benötigt)
- `import json` — war nach PR 4 ungenutzt (nur in Kommentar referenziert)

### `cls.*`-Felder als KW externalisiert

| `cls.*`-Feld | KW-Parameter | Übergabe in Delegation |
|---|---|---|
| `cls.RUN_STATE_DIR` | `run_state_dir` | `run_state_dir=cls.RUN_STATE_DIR` |

`_store()` / `resolve_default_store()` wird in `interview_client.py` direkt
aufgerufen (nicht über `cls.*`), da es schon in `simulation_runner.py` als
modul-level Helper implementiert war.

---

## Tests

### Baseline
- 1562 passed, 9 skipped (vor PR 4)

### Neue Tests
Datei: `backend/tests/services/sim/test_interview_client.py`

| Test | Beschreibung |
|---|---|
| `TestCheckEnvAlive::test_returns_false_when_sim_dir_missing` | Fehlender sim_dir → False |
| `TestCheckEnvAlive::test_returns_false_when_ipc_check_raises_connection_error` | IPC ConnectionError propagiert korrekt |
| `TestCheckEnvAlive::test_returns_false_when_ipc_returns_false` | IPC-Client gibt False zurück |
| `TestCheckEnvAlive::test_returns_true_when_ipc_reports_alive` | IPC-Client gibt True zurück |
| `TestGetEnvStatusDetail::test_returns_default_when_store_empty` | Kein Artifact → stopped-Default |
| `TestGetEnvStatusDetail::test_returns_parsed_status_from_store` | Artifact wird korrekt weitergeleitet |
| `TestGetInterviewHistoryFromDb::test_returns_empty_list_when_db_missing` | Fehlende DB → [] |
| `TestGetInterviewHistoryFromDb::test_reads_all_interview_rows` | Alle interview-Zeilen werden gelesen |
| `TestGetInterviewHistoryFromDb::test_filters_by_agent_id` | agent_id-Filter funktioniert |
| `TestGetInterviewHistoryFromDb::test_aggregation_via_get_interview_history` | Aggregation über beide Plattform-DBs |

### Nach PR 4
- 1572 passed, 9 skipped (+10 neue Tests)

---

## LOC-Diff-Tabelle

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `backend/app/services/simulation_runner.py` | 1278 | 986 | −292 |
| `backend/app/services/sim/interview_client.py` | (neu) | 350 | +350 |
| `backend/tests/services/sim/test_interview_client.py` | (neu) | 179 | +179 |

---

## Verifikations-Ergebnisse

- `pytest -x -q`: 1572 passed, 9 skipped
- `pytest tests/contracts/ -x -v`: 71 passed
- `pytest tests/services/sim/ -v`: 17 passed (10 neue + 7 bestehende)
- `ruff check app/ tests/`: All checks passed
- `mypy app`: Success: no issues found in 124 source files
- `git diff --exit-code schemas/`: kein Drift

---

## Risiken / offene Punkte

- **PR 5 (Restmenge):** `simulation_runner.py` hat nach PR 4 noch 986 LOC.
  Die Cut-Analyse schlägt `prepare_simulation` / `start_simulation` als nächsten
  Kandidaten vor. Der OASIS-Subprozess-Pfad ist der Hot-Spot für
  `gevent`-Monkey-Patch-Interaktionen — dort ist besondere Vorsicht geboten.
- **Monkeypatch-Stubs:** Tests patchen weiterhin `SimulationRunner.<method>`,
  nicht `interview_client.<function>`. Das ist korrekt, weil die API-Blueprints
  `SimulationRunner.*` aufrufen. Wenn zukünftig Tests direkt
  `interview_client`-Funktionen testen, müssen sie auf
  `app.services.sim.interview_client.*` patchen.
