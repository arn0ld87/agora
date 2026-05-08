# Arbeitsprotokoll: M11 Phase 5 PR 3 — `monitor_thread` Extraktion

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5-pr3-monitor-thread`
**Basis:** `2142e0a` (origin/main nach PR2 `action_log_reader`)

---

## Was wurde gemacht?

Extraktion von drei Methoden aus `SimulationRunner` in ein neues Submodul
`backend/app/services/sim/monitor.py`:

- `_monitor_simulation` (Daemon-Thread-Target, ~110 LOC)
- `get_timeline` (~60 LOC)
- `get_agent_stats` (~40 LOC)

In `simulation_runner.py` bleiben drei dünne Delegations-Klassenmethoden
für Backward-Compat. Pattern ist identisch zu PR 2 (`action_log_reader`).

---

## Wohin wurden welche Symbole verschoben?

| Vorher (SimulationRunner-Methode) | Nachher (Modul-Funktion) | Signaturänderung |
|---|---|---|
| `_monitor_simulation(cls, simulation_id)` | `monitor_simulation(simulation_id, *, run_state_dir, processes, graph_memory_enabled, action_queues, stdout_files, stderr_files, get_run_state, save_state)` | Alle `cls.*`-Dicts als Keyword-Parameter; `get_run_state` + `save_state` als Callables |
| `get_timeline(cls, simulation_id, start_round, end_round)` | `get_timeline(simulation_id, base_dir, start_round, end_round)` | `cls.RUN_STATE_DIR` durch expliziten `base_dir`-Parameter ersetzt |
| `get_agent_stats(cls, simulation_id)` | `get_agent_stats(simulation_id, base_dir)` | `cls.RUN_STATE_DIR` durch expliziten `base_dir`-Parameter ersetzt |

---

## Backward-Compat

Alle drei Methoden bleiben als delegierende Klassenmethoden auf `SimulationRunner`
erhalten:

- `_monitor_simulation`: Delegiert an `monitor_simulation_fn` mit allen `cls.*`-Dicts
  als Keyword-Args (Referenz-Übergabe, keine Kopie — Mutations bleiben synchron).
  `Thread(target=cls._monitor_simulation, args=(simulation_id,))` in `start_simulation`
  läuft unverändert.
- `get_timeline`: Delegiert an `_get_timeline_fn` mit `base_dir=cls.RUN_STATE_DIR`.
- `get_agent_stats`: Delegiert an `_get_agent_stats_fn` mit `cls.RUN_STATE_DIR`.

`monkeypatch.setattr(SimulationRunner, ...)` in Tests greift weiterhin auf die
Klassenmethoden.

---

## Technische Entscheidungen

1. **Callable-Parameter statt direkter Import:** `monitor_simulation` erhält
   `get_run_state` und `save_state` als Callables (wie beim PR-2-Lazy-Import-Pattern
   für `GraphMemoryManager`). Das verhindert einen zirkulären Import
   `monitor.py → simulation_runner.py`.

2. **Mutable Dicts by reference:** Die fünf Class-Level-Dicts (`_processes`,
   `_graph_memory_enabled`, `_action_queues`, `_stdout_files`, `_stderr_files`)
   werden by reference übergeben. Mutations in `monitor_simulation` (z. B.
   `processes.pop(...)`) sind sofort in `SimulationRunner` sichtbar — kein
   Verhaltens-Diff.

3. **GraphMemoryManager lazy import:** Identisch zu PR 2 — lazy import innerhalb
   des `finally`-Blocks mit `# noqa: PLC0415`.

4. **LOC monitor.py > 280:** Die extrahierte Logik (`_monitor_simulation` allein
   ~110 LOC inkl. `try/except/finally`) überschreitet die Zielspanne minimal
   (302 LOC statt max. 280). Der Wert war eine Schätzung; der Code ist korrekt
   und vollständig extrahiert.

---

## Tests

| Test-Art | Ergebnis |
|---|---|
| Baseline (vor PR 3) | 1555 passed, 9 skipped |
| Nach PR 3 | 1562 passed, 9 skipped (+7 neue Tests) |
| `tests/contracts/` | 71 passed |
| `ruff check app/ tests/` | All checks passed |
| `mypy app` | Success: no issues found in 123 source files |
| `git diff --exit-code schemas/` | Kein Drift |

Neue Tests in `backend/tests/services/sim/test_monitor.py`:

- `TestGetTimeline::test_round_grouping` — Actions nach Round gruppiert, Zähler korrekt
- `TestGetTimeline::test_start_round_filter` — `start_round` schließt frühere Rounds aus
- `TestGetTimeline::test_end_round_filter` — `end_round` schließt spätere Rounds aus
- `TestGetTimeline::test_empty_actions` — Leere Liste → leere Timeline
- `TestGetAgentStats::test_aggregation` — Pro-Agent-Stats korrekt berechnet
- `TestGetAgentStats::test_sorted_by_total_desc` — Sortierung nach `total_actions` absteigend
- `TestGetAgentStats::test_empty_actions` — Leere Liste → leere Stats-Liste

`monitor_simulation` ist Thread-basiert und hat keinen Unit-Test (kein Smoke-Test
ohne Thread-Spawn möglich ohne deutlich erhöhten Testaufwand; nicht in Scope).

---

## LOC-Diff

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `simulation_runner.py` | 1448 | 1278 | −170 |
| `sim/monitor.py` | — | 302 | +302 |
| `tests/services/sim/test_monitor.py` | — | 131 | +131 |
| `tests/services/sim/__init__.py` | — | 0 (leer) | +0 |
| `CHANGELOG.md` | — | +1 Eintrag | — |
| Dieses Protokoll | — | neu | — |

Netto-Bilanz über beide Dateien: −170 + 302 = +132 LOC gesamt im Produktivcode.
`simulation_runner.py` liegt bei 1278 (< 1300 Ziel, < 1320 Akzeptanzkriterium).

---

## Risiken / Offene Punkte

- **Unit-Test für `monitor_simulation`:** Thread-Logik ist durch die Delegation
  implizit durch die bestehenden Integrationstests abgedeckt (z. B.
  `test_simulation_manager_transitions.py`). Direkter Unit-Test wäre aufwendig
  (Mock für `subprocess.Popen.poll()`-Loop nötig) und ist als Folge-Slice
  dokumentierbar.
- `simulation_runner.py` hat noch ~1278 LOC. Weitere Kandidaten für Phase 5 PR 4:
  `_terminate_process` + `stop_simulation` (Process-Lifecycle) und
  `start_simulation` (Setup-Logik).
