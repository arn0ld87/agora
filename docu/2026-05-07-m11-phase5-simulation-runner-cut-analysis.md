# M11 Phase-5 Schnittanalyse: `simulation_runner.py`

**Datum:** 2026-05-07
**Autor:** Auditor (read-only, kein Code-Edit)
**Zieldatei:** `backend/app/services/simulation_runner.py` (1904 LOC)
**Branch:** `feat/m11-phase5-simrunner-cut-analysis`

---

## (1) Zweck und Scope

`simulation_runner.py` ist der zentrale Orchestrator für alle OASIS-Simulationsläufe in Agora. Er startet OASIS-Subprozesse (`subprocess.Popen`), liest Aktions-Logs der Agenten inkrementell ein, synchronisiert den Laufzustand in ein JSON-Artefakt (`run_state.json`) und veröffentlicht State-Updates auf dem Event-Bus. Zusätzlich enthält er die gesamte Interview-/IPC-Logik (sechs Methoden), Cleanup-Handler für Server-Shutdown sowie statistische Abfragen (Timeline, Agent-Stats). Der Hotspot-Status ergibt sich aus der Kumulation von sechs fachlich unterschiedlichen Concerns in einer 1904-LOC-Klasse ohne Submodul-Grenze. Laut `PLAN.md` (Weakness W5 / Finding F7) und Milestone M11 Slice 14 soll die Datei in mindestens zwei Submodule (`services/sim/process_manager.py`, `services/sim/event_sync.py`) zerlegt werden, wobei `simulation_runner.py` als dünne Façade verbleibt. Das `docu/agora_next_steps_after_p0_2026-05-07.md` war im Worktree zum Zeitpunkt der Analyse nicht vorhanden *(unverifiziert — Datei fehlt im Worktree-Pfad; Kontext wurde aus `PLAN.md` und `docu/ROADMAP.md` rekonstruiert)*.

---

## (2) Verantwortlichkeiten je Sektion

### Setup / Init

| Symbol | Zeilen | Funktion |
|---|---|---|
| `RunnerStatus` (Enum) | 48–58 | Definiert alle zulässigen Laufzustände des Runners. |
| `AgentAction` (dataclass) | 61–85 | Wert-Objekt für eine einzelne Agent-Aktion mit `to_dict()`. |
| `RoundSummary` (dataclass) | 88–111 | Wert-Objekt für eine Rundenübersicht mit `to_dict()`. |
| `SimulationRunState` (dataclass) | 114–207 | Vollständiger Laufzustand einer Simulation mit `add_action()`, `to_dict()`, `to_detail_dict()`. |
| `_store()` (module-level) | 30–37 | Lazy-Resolver für den `SimulationArtifactStore`; hält Flask-Kontext-Freiheit. |
| `_OASIS_DB_DIR_NAME`, `_OASIS_DB_FILE_NAME` | 213–214 | Konstanten für OASIS-DB-Pfad. |
| `_compute_oasis_db_path()` | 217–224 | Berechnet sim-spezifischen DB-Pfad und legt das Verzeichnis an (Sub-Slice 21). |
| `_inject_oasis_db_env()` | 227–233 | Setzt `OASIS_DB_PATH` im Subprozess-Env ohne User-Override zu überschreiben (Sub-Slice 21). |
| `SimulationRunner` (class header + Klassenvariablen) | 236–269 | Konfiguriert `RUN_STATE_DIR`, `SCRIPTS_DIR` und alle In-Memory-Dicts (`_run_states`, `_processes`, `_action_queues`, `_monitor_threads`, `_stdout_files`, `_stderr_files`, `_graph_memory_enabled`). |

### LLM-Call / OASIS-Subprozess

| Symbol | Zeilen | Funktion |
|---|---|---|
| `start_simulation()` | 434–619 | Startet OASIS-Subprozess mit `subprocess.Popen`, injiziert Umgebungsvariablen, öffnet Log-File-Handle und spawnt den Monitor-Thread. |
| `_terminate_process()` | 866–919 | Plattformübergreifende Prozessgruppen-Terminierung (SIGTERM/SIGKILL auf Unix, `taskkill` auf Windows). |

### Persona- / Quoten-Logik

Nicht direkt vorhanden — Quoten-Logik liegt in `prepare_service.py`. `simulation_runner.py` konsumiert Quoten ausschließlich über die fertige `simulation_config.json` (Z. 476) und übersetzt `time_config`-Felder in `total_rounds`. Kein eigener Concern.

### Persistierung / Storage

| Symbol | Zeilen | Funktion |
|---|---|---|
| `get_run_state()` | 318–327 | Liest Laufzustand aus In-Memory-Cache oder delegiert an `_load_run_state()`. |
| `_load_run_state()` | 330–384 | Deserialisiert `run_state.json` vom Artifact-Store in ein `SimulationRunState`-Objekt. |
| `_save_run_state()` | 387–431 | Serialisiert Zustand, schreibt JSON via Artifact-Store, publiziert auf Event-Bus, synct mit `RunRegistry`. |
| `_read_actions_from_file()` | 973–1039 | Liest und filtert eine einzelne `actions.jsonl`-Datei; gibt `AgentAction`-Objekte zurück. |
| `get_all_actions()` | 1042–1100 | Aggregiert Aktionen aus Twitter- und Reddit-Log-Dateien mit optionalem Legacy-Fallback. |
| `get_actions()` | 1103–1134 | Wraps `get_all_actions()` mit Paginierung. |
| `get_console_log()` | 271–315 | Liest `simulation.log` inkrementell für Client-Polling. |
| `cleanup_simulation_logs()` | 1251–1327 | Löscht Log-Dateien und In-Memory-State für Force-Restart. |

### Stream / SSE

Der Runner publiziert auf dem Event-Bus in `_save_run_state()` (Z. 398–411) via `bus.publish(CHANNEL_STATE, SimulationEvent(...))`. Es gibt keinen dedizierten SSE-Endpunkt in dieser Datei — das liegt in `app/api/simulation_run.py`. Die Bus-Integration ist tief in `_save_run_state()` eingebettet und nicht separiert.

### Cleanup / Teardown

| Symbol | Zeilen | Funktion |
|---|---|---|
| `stop_simulation()` | 922–970 | Stoppt einen laufenden Subprozess über `_terminate_process()` und schreibt finalen Zustand. |
| `cleanup_all_simulations()` | 1333–1428 | Terminiert alle laufenden Prozesse beim Server-Shutdown, schreibt Zustände, schließt File-Handles. |
| `register_cleanup()` | 1431–1501 | Registriert `atexit`-Handler und Signal-Handler (SIGTERM/SIGINT/SIGHUP) mit Reloader-Child-Guard. |
| `cleanup_handler()` (nested) | 1462–1483 | Signal-Handler, der Cleanup auslöst und originale Handler weiterleitet. |
| `get_running_simulations()` | 1504–1512 | Gibt Liste der IDs aller laufenden Subprozesse zurück. |

### Interview / IPC

| Symbol | Zeilen | Funktion |
|---|---|---|
| `check_env_alive()` | 1517–1532 | Prüft via `SimulationIPCClient`, ob das OASIS-Environment noch läuft. |
| `get_env_status_detail()` | 1535–1561 | Liest detaillierten Environment-Status aus `env_status.json`. |
| `interview_agent()` | 1564–1625 | Sendet einzelnes Interview-Kommando via IPC und gibt Ergebnis zurück. |
| `interview_agents_batch()` | 1628–1684 | Sendet Batch-Interview-Kommando via IPC. |
| `interview_all_agents()` | 1687–1745 | Liest alle Agent-IDs aus `simulation_config.json` und delegiert an `interview_agents_batch()`. |
| `close_simulation_env()` | 1748–1793 | Sendet Close-Environment-Kommando via IPC. |

### Helper / Pure

| Symbol | Zeilen | Funktion |
|---|---|---|
| `_monitor_simulation()` | 622–726 | Monitor-Thread: liest Action-Logs iterativ, aktualisiert Zustand, delegiert an `_read_action_log()`. |
| `_read_action_log()` | 729–836 | Liest JSONL-Einträge ab einer Datei-Position, verarbeitet Event-Typen (`simulation_end`, `round_end`) und Agent-Aktionen. |
| `_check_all_platforms_completed()` | 839–863 | Prüft ob alle aktiven Plattformen abgeschlossen sind (via Dateiexistenz). |
| `get_timeline()` | 1137–1205 | Aggregiert Aktionen zu einer Runden-Zeitleiste. |
| `get_agent_stats()` | 1208–1248 | Berechnet Pro-Agent-Statistiken über alle Aktionen. |
| `_get_interview_history_from_db()` | 1796–1851 | Liest Interview-Historie direkt aus SQLite (`trace`-Tabelle) einer Plattform-DB. |
| `get_interview_history()` | 1854–1904 | Aggregiert Interview-Historien aus Twitter- und Reddit-SQLite-DBs. |

---

## (3) Externe Call-Sites

### api/ (Boundary)

| Datei | Genutzte Symbole |
|---|---|
| `app/api/simulation_run.py` | `SimulationRunner.start_simulation`, `stop_simulation`, `get_run_state`, `cleanup_simulation_logs`, `get_console_log`, `get_all_actions`, `get_actions`, `get_timeline`, `get_agent_stats`, `check_env_alive`, `get_env_status_detail`, `close_simulation_env` |
| `app/api/simulation_interviews.py` | `SimulationRunner.check_env_alive`, `interview_agent`, `interview_agents_batch`, `interview_all_agents`, `get_interview_history` |
| `app/api/simulation_metrics.py` | `SimulationRunner.get_all_actions` |
| `app/api/simulation_history.py` | `SimulationRunner.get_run_state` |
| `app/api/simulation_common.py` | `SimulationRunner.get_run_state`, `RunnerStatus` |
| `app/api/runs.py` | `SimulationRunner.stop_simulation`, `start_simulation`, `get_run_state`, `RunnerStatus` |

### services/ (intern)

| Datei | Genutzte Symbole |
|---|---|
| `app/services/__init__.py` | Re-Export: `SimulationRunner` |
| `app/services/compare_service.py` | `SimulationRunner.get_all_actions` (lazy import in Methode Z. 162) |
| `app/services/graph_tools.py` | `SimulationRunner.interview_agents_batch` (lazy import in Methode Z. 1094) |
| `app/services/report_agent/agent.py` | `SimulationRunner.get_all_actions` (lazy import in Methode Z. 187) |
| `app/services/artifact_store.py` | Nur Kommentar-Referenz (Z. 250), kein Import |
| `app/services/prepare_service.py` | Nur Kommentar-Referenz (Z. 464), kein Import |

### scripts/ (CLI / OASIS)

| Datei | Genutzte Symbole |
|---|---|
| `scripts/diagnose_metric_snapshot.py` | `SimulationRunner.get_all_actions` (direkter Import, Z. 41) |
| `scripts/run_twitter_simulation.py` | `TwitterSimulationRunner` (eigene Klasse, kein Import von `simulation_runner.py`) |
| `scripts/run_reddit_simulation.py` | `RedditSimulationRunner` (eigene Klasse, kein Import von `simulation_runner.py`) |

### tests/ (Coverage)

| Datei | Genutzte Symbole |
|---|---|
| `tests/test_simulation_runner_oasis_db_path.py` | `_compute_oasis_db_path`, `_inject_oasis_db_env` |
| `tests/test_simulation_metrics_export.py` | `AgentAction`, `SimulationRunner.get_all_actions` (via Monkeypatch) |
| `tests/test_report_manager.py` | `AgentAction`, `SimulationRunner.get_all_actions` (via Monkeypatch) |
| `tests/api/test_simulation_endpoints.py` | `SimulationRunner.check_env_alive` (via Monkeypatch) |
| `tests/services/test_compare_service.py` | `SimulationRunner.get_all_actions` (via Monkeypatch, 4 Testfälle) |

---

## (4) Test-Coverage

| Test-Datei | Abgedeckte Symbole | Stil |
|---|---|---|
| `test_simulation_runner_oasis_db_path.py` | `_compute_oasis_db_path`, `_inject_oasis_db_env` | unit |
| `test_simulation_metrics_export.py` | `AgentAction` (Konstruktor), `get_all_actions` (Monkeypatch-Stub) | unit |
| `test_report_manager.py` | `AgentAction` (Konstruktor), `get_all_actions` (Monkeypatch-Stub) | unit |
| `test_simulation_endpoints.py` | `check_env_alive` (Monkeypatch-Stub für 1 Testfall) | unit / API |
| `test_compare_service.py` | `get_all_actions` (Monkeypatch-Stub, 4 Testfälle) | unit |

**Sektionen ohne dedizierte Tests (Coverage-Gap):**

- `start_simulation()` — kein Test, der den `Popen`-Aufruf verifiziert oder die State-Transition `STARTING → RUNNING` prüft.
- `_monitor_simulation()` / `_read_action_log()` — kein Test für JSONL-Parsing, Event-Typ-Handling (`simulation_end`, `round_end`), Graph-Memory-Integration.
- `stop_simulation()` / `_terminate_process()` — kein Test für Prozess-Termination (SIGTERM/SIGKILL-Pfade, Windows-Fallback).
- `cleanup_all_simulations()` / `register_cleanup()` — kein Test für Shutdown-Handler.
- `get_timeline()` / `get_agent_stats()` — keine dedizierten Tests (werden implizit durch API-Tests berührt, aber nicht direkt).
- Interview-Sektion (`interview_agent`, `interview_agents_batch`, `interview_all_agents`, `get_interview_history`, `_get_interview_history_from_db`) — nur `check_env_alive` hat einen Stub-Test; Kern-Interview-Methoden sind ungetestet.
- `_save_run_state()` — kein Test für Event-Bus-Publish oder RunRegistry-Sync.
- `_load_run_state()` — kein direkter Test (nur indirekt via `get_run_state`-Pfad in Integrationstests).

---

## (5) Extraktionskandidaten

### Kandidat 1: `process_manager`

**Was raus:** `start_simulation()` (Z. 434–619), `_terminate_process()` (Z. 866–919), `stop_simulation()` (Z. 922–970), `cleanup_all_simulations()` (Z. 1333–1428), `register_cleanup()` (Z. 1431–1501), `get_running_simulations()` (Z. 1504–1512), `cleanup_handler()` (nested, Z. 1462–1483), `_compute_oasis_db_path()` (Z. 217–224), `_inject_oasis_db_env()` (Z. 227–233)

**Wohin:** `backend/app/services/sim/process_manager.py`

**Pure?** Nein. Starke Side-Effects: `subprocess.Popen`, `os.makedirs`, `signal.signal`, `atexit.register`, Schreiben von File-Handles. Außerdem Zugriff auf Klassenattribute (`_processes`, `_stdout_files`, `_stderr_files`, `_graph_memory_enabled`), die migriert werden müssen.

**Risiko:** H — `start_simulation()` ist die am häufigsten aufgerufene Methode (6 API-Call-Sites), enthält den vollständigen `Popen`-Lifecycle und hat keinen dedizierten Test. Fehler im Refactor sind nur durch manuelles Smoke-Testen des OASIS-Subprozesses erkennbar.

**Test-Strategie:** Die 4 bestehenden `_compute_oasis_db_path`/`_inject_oasis_db_env`-Tests in `test_simulation_runner_oasis_db_path.py` können 1:1 auf den neuen Pfad verschoben werden. Für `start_simulation()` müssen vor dem Refactor Mocks für `subprocess.Popen` und den Artifact-Store angelegt werden, die State-Transition `STARTING → RUNNING` verifizieren.

---

### Kandidat 2: `action_log_reader`

**Was raus:** `_read_action_log()` (Z. 729–836), `_read_actions_from_file()` (Z. 973–1039), `get_all_actions()` (Z. 1042–1100), `get_actions()` (Z. 1103–1134), `_check_all_platforms_completed()` (Z. 839–863)

**Wohin:** `backend/app/services/sim/action_log_reader.py`

**Pure?** Teilweise. `_read_actions_from_file()` und `get_all_actions()` lesen nur von Disk und sind weitgehend pure (Dateipfad-Abhängigkeit, kein globaler State). `_read_action_log()` ist impure: mutiert das übergebene `SimulationRunState`-Objekt und greift auf `_graph_memory_enabled` zu.

**Risiko:** M — `get_all_actions()` ist der am häufigsten als Monkeypatch-Stub genutzte Einstiegspunkt (5 Test-Stellen). Eine Umbenennung oder Signaturänderung bricht alle Stubs. Der Legacy-Fallback auf `actions.jsonl` (Z. 1087–1095) muss erhalten bleiben.

**Test-Strategie:** Die bestehenden Monkeypatch-Stubs in `test_simulation_metrics_export.py`, `test_report_manager.py`, `test_compare_service.py` bleiben durch Re-Export aus `simulation_runner.py` grün. Neue Unit-Tests für `_read_actions_from_file()` mit Fixture-JSONL-Dateien decken den JSONL-Parsing-Pfad ab.

---

### Kandidat 3: `run_state_store`

**Was raus:** `get_run_state()` (Z. 318–327), `_load_run_state()` (Z. 330–384), `_save_run_state()` (Z. 387–431), `get_console_log()` (Z. 271–315), `cleanup_simulation_logs()` (Z. 1251–1327), `SimulationRunState` (Z. 114–207), `AgentAction` (Z. 61–85), `RoundSummary` (Z. 88–111), `RunnerStatus` (Z. 48–58)

**Wohin:** `backend/app/services/sim/run_state_store.py`

**Pure?** Nein. `_save_run_state()` publiziert auf dem Event-Bus und schreibt in die `RunRegistry` — beide sind Side-Effects. Die Dataclasses selbst sind pure Wert-Objekte.

**Risiko:** M — `SimulationRunState`, `AgentAction` und `RunnerStatus` werden in 6 API-Dateien und 3 Test-Dateien direkt importiert. Ein Pfadwechsel erfordert Update aller Import-Statements oder konsequentes Re-Export aus `simulation_runner.py`. Die Event-Bus-Logik in `_save_run_state()` ist ein versteckter Coupling-Punkt zu `event_bus.py`.

**Test-Strategie:** Bestehende Tests importieren `AgentAction` und `RunnerStatus` — Re-Export aus `simulation_runner.py` hält sie grün. Neue Tests für `_save_run_state()` sollten Event-Bus-Publish und RunRegistry-Sync mit Mocks verifizieren, um den bisher ungetesteten Coupling zu dokumentieren.

---

### Kandidat 4: `interview_client`

**Was raus:** `check_env_alive()` (Z. 1517–1532), `get_env_status_detail()` (Z. 1535–1561), `interview_agent()` (Z. 1564–1625), `interview_agents_batch()` (Z. 1628–1684), `interview_all_agents()` (Z. 1687–1745), `close_simulation_env()` (Z. 1748–1793), `_get_interview_history_from_db()` (Z. 1796–1851), `get_interview_history()` (Z. 1854–1904)

**Wohin:** `backend/app/services/sim/interview_client.py`

**Pure?** Nein. `interview_agent()` und Batch-Varianten delegieren vollständig an `SimulationIPCClient` (IPC-Call). `_get_interview_history_from_db()` öffnet eine SQLite-Verbindung (`sqlite3.connect`). Alle Methoden haben I/O-Side-Effects.

**Risiko:** L — Die Interview-Methoden sind fachlich isoliert und haben nur zwei Import-Stellen in `api/` (`simulation_interviews.py`, `simulation_run.py`). Die einzige Test-Abdeckung ist ein einzelner `check_env_alive`-Stub. Der Schnitt verändert kein bestehendes Verhalten; das Risiko liegt im fehlenden Test-Netz, nicht in der Coupling-Dichte.

**Test-Strategie:** Bestehender `check_env_alive`-Stub-Test in `test_simulation_endpoints.py` bleibt über Re-Export grün. Vor dem Refactor sollten Mocks für `SimulationIPCClient` und `sqlite3.connect` angelegt werden, um den IPC-Roundtrip und SQLite-Lesepfad abzusichern.

---

### Kandidat 5: `monitor_thread`

**Was raus:** `_monitor_simulation()` (Z. 622–726), `get_timeline()` (Z. 1137–1205), `get_agent_stats()` (Z. 1208–1248)

**Wohin:** `backend/app/services/sim/monitor.py`

**Pure?** Nein. `_monitor_simulation()` ist ein Daemon-Thread mit Schleifen-Wartezeit (`time.sleep(2)`), mutiert `SimulationRunState` und ruft `_save_run_state()` auf. `get_timeline()` und `get_agent_stats()` sind reine Read-Methoden über `get_actions()` und damit näher an pure.

**Risiko:** M — `_monitor_simulation()` wird nur intern als Thread-Target genutzt (Z. 602) und hat keine direkten externen Call-Sites. `get_timeline()` und `get_agent_stats()` sind je einmal in `simulation_run.py` aufgerufen. Die Kopplung zu `GraphMemoryManager` im `finally`-Block (Z. 700–708) muss beim Refactor mitbetrachtet werden. Keine eigenen Tests vorhanden — hohes Regressions-Risiko ohne vorherige Test-Absicherung.

**Test-Strategie:** Vor dem Refactor sind Unit-Tests für `_read_action_log()` (schon in Kandidat 2 enthalten) notwendig, da `_monitor_simulation()` darauf aufbaut. `get_timeline()` und `get_agent_stats()` sind mit Fixture-`AgentAction`-Listen direkt testbar.

---

## (6) Empfohlene PR-Reihenfolge

1. **PR 1 — Kandidat 3: `run_state_store`** (= PR 1 der vier Phase-5-PRs gemäß PLAN.md F7 / M11 Slice 14)
   Begründung: Die Dataclasses (`SimulationRunState`, `AgentAction`, `RoundSummary`, `RunnerStatus`) und die Store-Methoden sind das stabile Fundament, auf dem alle anderen Kandidaten aufbauen. Ein Re-Export-Pattern wie bei `neo4j_storage.py` hält alle bestehenden Imports grün. Keine laufenden Prozesse betroffen; Risiko ist beherrschbar.

2. **PR 2 — Kandidat 2: `action_log_reader`**
   Begründung: `get_all_actions()` ist die am häufigsten gemockte Methode; nach PR 1 sind die Dataclasses bereits im neuen Pfad stabil. Die Monkeypatch-Stubs in 5 Test-Dateien sind der einzige Brittle-Point und werden durch Re-Export abgefangen.

3. **PR 3 — Kandidat 5: `monitor_thread`**
   Begründung: `_monitor_simulation()` baut auf `_read_action_log()` (nach PR 2 im neuen Modul) auf. Nach PR 1+2 sind die Abhängigkeiten klar getrennt. Kein externer Call-Site; Risiko ausschließlich intern.

4. **PR 4 — Kandidat 4: `interview_client`**
   Begründung: Fachlich vollständig isolierter Block ohne Abhängigkeit zu den anderen Kandidaten. Niedrigstes Risiko wegen geringer Call-Site-Dichte. Kann parallel zu PR 3 vorbereitet, aber sequenziell danach gemergt werden.

5. **PR 5 — Kandidat 1: `process_manager`** (last)
   Begründung: Höchstes Risiko (H) wegen fehlendem Test-Netz für `start_simulation()` und direkter `Popen`-/Signal-Lifecycle-Komplexität. Erst nach PR 1–4 sollte dieser Schnitt erfolgen, wenn die umgebenden Module stabil und getestet sind und der Monitor-Thread bereits extrahiert wurde.

