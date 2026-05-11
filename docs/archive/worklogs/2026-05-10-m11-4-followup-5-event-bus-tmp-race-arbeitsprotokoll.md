# M11.4-Followup-5 — FilePollingEventBus tmp-File-Race Fix

**Datum:** 2026-05-10
**Branch:** `fix/event-bus-tmp-file-race`
**Scope:** `backend/app/services/artifact_store.py`, `backend/tests/test_event_bus.py`

---

## Symptom

CI-Run für `89fbeec` (`Backend tests + lint`-Job in `ci.yml`) zeigte:

```
TimeoutError: Timeout waiting for IPC response
  (command_type=interview, correlation_id=797bf627-…, timeout=10.0s)
ValueError: Invalid IPC command id: '.tmp-json-yw5xy_cp'
FAILED tests/test_event_bus.py::test_request_response_correlation[FilePollingEventBus]
```

### Workaround-Historie (Timeout-Erhöhungen)

| Schritt | Timeout | Commit-Kontext |
|---|---|---|
| Ursprünglicher Test | 2.0 s | Issue #9 Phase A |
| Erster Bump | 5.0 s | CI-Run 25599430790 (FilePollingEventBus) |
| Zweiter Bump | 10.0 s | Folgeproblem CI |
| **Followup-5 Fix** | **5.0 s** | Root Cause behoben, Workaround zurückgedreht |

---

## Root Cause

`write_json_atomic` in `backend/app/utils/json_io.py:15` erzeugt Temp-Dateien via:

```python
fd, tmp_path = tempfile.mkstemp(prefix='.tmp-json-', suffix='.json', dir=directory)
```

Das bedeutet: Während eines atomischen Schreibvorgangs in `ipc_commands/` existiert kurzzeitig eine Datei namens `.tmp-json-XXXXXX.json` in diesem Verzeichnis. `os.replace()` macht den Atomic-Swap danach sofort, aber das Race-Window ist offen.

Der Polling-Loop in `LocalFilesystemArtifactStore.list_artifacts()` (Methode `list_artifacts`, `backend/app/services/artifact_store.py:183-192`) scannte das `ipc_commands/`-Verzeichnis via `os.scandir` und übergab **jeden** Eintrag an `_reverse_lookup()`. Bei einem `.tmp-json-abc.json`-Eintrag lieferte `_reverse_lookup` den logischen Namen `"ipc_command/.tmp-json-abc"` zurück.

Wenn dieser Name dann in `_subscribe_rpc_commands` (event_bus.py:393) oder `SimulationIPCServer.poll_commands()` (simulation_ipc.py:350) als Artifact-Name für `read_json()` verwendet wurde, rief das `_resolve_relative_path("ipc_command/.tmp-json-abc")` auf, das bei Zeile 58-59 prüft:

```python
if not cmd_id or "/" in cmd_id or cmd_id.startswith("."):
    raise ValueError(f"Invalid IPC command id: {cmd_id!r}")
```

Der `ValueError` wurde im `poll_commands`-Code via `except (KeyError, ValueError)` abgefangen (simulation_ipc.py:384), aber im `_subscribe_rpc_commands`-Polling-Loop propagierte er nach oben und brach den gesamten Poll-Tick ab. Das echte IPC-Command wurde in dieser Runde nicht gesehen. Bei mehreren hintereinanderfolgenden atomic-writes summierte sich das zu einem Test-Timeout.

**Vergleichscode:** `backend/app/services/run_registry.py:281` hat das identische Problem korrekt gelöst:
```python
# Skip tempfiles from atomic writes (.tmp-json-*.json).
if filename.startswith("."):
    continue
```

---

## Fix

**Datei:** `backend/app/services/artifact_store.py`

In `LocalFilesystemArtifactStore.list_artifacts()`, beim Scan der IPC-Unterverzeichnisse (`ipc_commands/`, `ipc_responses/`) wird jetzt vor der `_reverse_lookup()`-Übergabe gefiltert:

```python
# Vorher (Zeilen 186-192):
with os.scandir(sub_path) as entries:
    for entry in entries:
        if entry.is_file():
            name = _reverse_lookup(f"{sub}/{entry.name}")
            if name is not None:
                results.append(name)

# Nachher:
with os.scandir(sub_path) as entries:
    for entry in entries:
        if not entry.is_file():
            continue
        # Skip tempfiles from atomic writes (.tmp-json-*.json).
        # Analogous guard to run_registry.py:281. Without this,
        # the Polling-Loop picks up the dot-prefixed tmp name,
        # passes it to _resolve_relative_path, and receives a
        # ValueError (cmd_id.startswith(".")), aborting the whole
        # poll round — the real IPC command is never seen until
        # the next tick, causing cumulative TimeoutErrors under
        # rapid atomic-write traffic (M11.4-Followup-5).
        if entry.name.startswith(".") or not entry.name.endswith(".json"):
            continue
        name = _reverse_lookup(f"{sub}/{entry.name}")
        if name is not None:
            results.append(name)
```

Approach A (Listen-Generator filtern) gewählt, da Approach B (defensive `_reverse_lookup`) die API ändern und alle Aufrufer anpassen würde.

---

## Test-Änderungen

**Datei:** `backend/tests/test_event_bus.py`

1. `test_request_response_correlation`: Timeout zurückgedreht von 10.0 s auf 5.0 s, Kommentar aktualisiert mit Erklärung, dass ein erneutes Rot kein Timeout-Problem ist.

2. Neuer Regressionstest `test_tmp_files_do_not_disrupt_file_polling`: Legt gezielt 5 `.tmp-json-*.json`-Dateien im `ipc_commands/`-Verzeichnis an via `tempfile.mkstemp()`, sendet dann ein echtes IPC-Command und asserted, dass `request_response()` erfolgreich durchläuft.

---

## Verifikation

### 10x sequentieller Race-Test

```
Run 1:  1 passed in 20.84s  (pytest cold-start)
Run 2:  1 passed in 1.67s
Run 3:  1 passed in 1.58s
Run 4:  1 passed in 1.13s
Run 5:  1 passed in 1.05s
Run 6:  1 passed in 1.20s
Run 7:  1 passed in 1.50s
Run 8:  1 passed in 1.49s
Run 9:  1 passed in 1.06s
Run 10: 1 passed in 1.25s
```

10/10 grün. Kein einziger Timeout.

### Full test suite

```
1692 passed, 9 skipped, 7 deselected, 3 warnings in 123.39s
```

Skips: Redis nicht verfügbar + docker-compose (erwartet).

### Lint + Types

```
ruff check app/ tests/  → All checks passed!
mypy app               → Success: no issues found in 132 source files
```

### Schema-Drift

```
git diff --exit-code schemas/ → No schema drift
```

---

## Betroffene Dateien

| Datei | Änderung |
|---|---|
| `backend/app/services/artifact_store.py` | Filter für dot-prefixed Einträge in `list_artifacts()` IPC-Subdir-Scan |
| `backend/tests/test_event_bus.py` | Timeout 10.0 → 5.0 s, neuer Regressionstest |
| `docs/2026-05-10-m11-4-followup-5-*` | Dieses Protokoll |
| `CHANGELOG.md` | Fixed-Bullet |
