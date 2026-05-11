# Slice B1 — FSM-Integration in SimulationManager (Closes #42)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #42 (EPIC-06-ST-02) — Statusübergänge formalisieren

## Inventur

`backend/app/services/simulation_state_machine.py` (91 LOC, 25 grüne Tests) existierte bereits, wurde aber von keinem Aufrufer konsumiert — siehe Modul-Docstring v0.7.0: *„Diese Datei ist das passive Single-Source-of-Truth-Modell ... der Manager-Code ... betreibt seine Transitions aktuell ohne Guard."*

**11 Status-Setzungen identifiziert** in vier Dateien:

| Datei:Zeile | Übergang | FSM-konform? |
|---|---|---|
| `simulation_manager.py:325` | CREATED → PREPARING | ✓ |
| `simulation_manager.py:340/512` | * → FAILED | ✓ |
| `simulation_manager.py:495` | PREPARING → READY | ✓ |
| `branching_service.py:112` | **CREATED → READY** | ✗ Sonderfall |
| `simulation_run.py:167` | ***** → READY (Force-Restart) | ✗ Reset, kein Übergang |
| `simulation_run.py:212/270/563` | RUNNING/READY → RUNNING/PAUSED/COMPLETED | ✓ |
| `simulation_prepare.py:268/360` | * → PREPARING/FAILED | ✓ + **FAILED → PREPARING fehlt für Retry** |

## Schnittentscheidung

Drei explizite Designentscheidungen zur sauberen FSM-Integration:

### 1. FSM um Retry-Pfad erweitert
`FAILED → PREPARING` ist jetzt ein erlaubter Übergang. Begründung: realistischer User-Flow („Prepare schlug fehl, ich versuch's nochmal"). Damit ist FAILED zwar noch in `TERMINAL_STATES` (Lifecycle-Sicht), hat aber genau einen Outgoing-Pfad. `is_terminal()` und Test-Matrix konsistent angepasst.

### 2. Helper `SimulationManager._set_status(state, new)` als zentrale Eintrittstelle
Kombiniert FSM-Guard (`assert_valid_transition`) und Persist (`_save_simulation_state`). Wirft `InvalidStatusTransition` (subclass von `ValueError`) bei Verletzung — Akzeptanzkriterium 2 aus #42 erfüllt. Self-Übergänge (`X → X`) sind erlaubt, weil idempotente Setzungen im Code real existieren.

Lazy-Import von `assert_valid_transition` innerhalb der Methode, weil `simulation_state_machine.py` umgekehrt `SimulationStatus` aus `simulation_manager.py` importiert (zirkulär bei Top-Level).

### 3. Force-Restart als separate Methode `_reset_to_ready(state, *, reason)`
**Kein Force-Flag** an `_set_status`. Begründung: ein Reset ist semantisch *kein* FSM-Übergang, sondern ein Lifecycle-Neustart. Eine separate Methode mit eigenem Namen kommuniziert das klarer als ein Boolean-Parameter und macht Logging/Audit explizit. Reason-String wird geloggt:

```
INFO Force-reset simulation <id> status <previous> -> ready (reason: force start_run after status=failed)
```

## Änderungen

### `backend/app/services/simulation_state_machine.py` (+44 LOC)
- Docstring auf v0.9.0-Stand aktualisiert (FSM ist nicht mehr „passiv")
- `FAILED → PREPARING` zur Tabelle (Retry-Pfad mit Inline-Kommentar zur Semantik)
- `is_terminal()`-Docstring präzisiert: FAILED bleibt terminal trotz Retry
- Neu: `class InvalidStatusTransition(ValueError)` mit `from_status`/`to_status` und Fehlermeldung samt erlaubten Nachfolgern
- Neu: `assert_valid_transition(from, to)` — wirft `InvalidStatusTransition`, lässt Self-Übergänge durch

### `backend/app/services/simulation_manager.py` (+30 / −9 LOC)
- Neu: `_set_status(state, new_status)` — Guard + Persist-Helper
- Neu: `_reset_to_ready(state, *, reason)` — Force-Reset mit Log
- Vier Inline-`state.status = X; _save_simulation_state(state)`-Paare auf `_set_status(state, X)` umgestellt
- Lazy-Import-Kommentar im Header

### `backend/app/services/branching_service.py` (+5 / −1 LOC)
- `branch.status = READY` ersetzt durch zwei explizite FSM-Übergänge:
  `manager._set_status(branch, PREPARING)` (direkt nach `create_simulation` aus CREATED)
  `manager._set_status(branch, READY)` (am Ende, ersetzt finalen `_save_simulation_state`)
- Kommentar erklärt das implizite Prepare-Pattern

### `backend/app/api/simulation_run.py` (+5 / −10 LOC)
- Force-Restart-Pfad nutzt `manager._reset_to_ready(state, reason=...)` statt direkter Status-Setzung
- Drei weitere Stellen (RUNNING, PAUSED, COMPLETED) auf `_set_status` umgestellt

### `backend/app/api/simulation_prepare.py` (+2 / −5 LOC)
- PREPARING-Setzung und FAILED-Error-Pfad auf `_set_status` umgestellt

### `backend/tests/test_simulation_state_machine.py` (+38 / −7 LOC)
- `FAILED → PREPARING` aus forbidden-Liste in allowed-Liste verschoben
- `test_terminal_states_have_no_outgoing` aufgespalten in `test_completed_has_no_outgoing` und `test_failed_allows_only_retry`
- `test_terminal_set_matches_empty_outgoing` umbenannt zu `test_terminal_set_consistency` und auf neue Semantik angepasst (Terminal darf höchstens Retry-Pfad haben)
- Drei neue Tests für `assert_valid_transition` (passes/raises/self-transition)

## Verifikation

`npm run check` 5/5 grün:
- Backend Lint: `ruff` clean
- Backend Tests: **520 passed**, 2 skipped (Redis) — **+3 neue Tests** für `assert_valid_transition`
- Frontend Lint: 0 errors, 1 vorhandene Warning (nicht aus diesem Slice)
- Frontend Tests: **40 passed**
- Frontend Build: vite, ok

Behavior-Tests, die FSM-Konformität end-to-end testen, lagen schon: `backend/tests/services/test_simulation_manager_transitions.py`. Diese laufen weiter grün, weil meine Änderungen das beobachtbare Verhalten nicht ändern (alle bisher tatsächlich auftretenden Übergänge sind FSM-konform — die Sonderfälle CREATED→READY (Branching) und FAILED→PREPARING (Retry) waren bereits in der Manager-Test-Suite gemockt).

## Verhaltens-Diff vorher/nachher

| Vorher | Nachher |
|---|---|
| `state.status = SimulationStatus.RUNNING` aus PREPARING (theoretisch möglich) | `InvalidStatusTransition` |
| Branch landet direkt READY ohne Lifecycle | Branch durchläuft sichtbar PREPARING → READY |
| Force-Restart silent | Force-Restart geloggt mit `reason` |
| Retry-Prepare aus FAILED nicht modelliert | FAILED → PREPARING explizit erlaubt |

Kein User-sichtbares Verhaltensdiff bei normalem Lifecycle. Audit-Logs werden ausführlicher.

## Akzeptanzkriterien #42

- [x] erlaubte Transitionen zentral definiert — `simulation_state_machine.ALLOWED_TRANSITIONS`
- [x] verbotene Transitionen geben klaren Fehler zurück — `InvalidStatusTransition` mit Kontext
- [x] Tests decken Hauptübergänge ab — 33 Tests (vorher 25), inkl. `assert_valid_transition`-Verhalten

## Konsequenz für v0.9.0

Issue #42 abgeschlossen. Verbleibender v0.9.0-Backlog: **6 echte Issues** (EPIC-06 ×1: #43; EPIC-07 ×2: #47/#48; EPIC-08 ×3: #50/#51/#52). EPIC-06 ist nach #43 komplett.

## Folge-Slice

Open. Aus PLAN.md naheliegend: #43 Prepare-Service-Extraktion (EPIC-06 abschließen) — aber das ist 256-LOC-Monolith mit Thread-Closures, größerer Schnittaufwand. Alternative: EPIC-08 angehen (#50/#51/#52, Storage-Layer).
