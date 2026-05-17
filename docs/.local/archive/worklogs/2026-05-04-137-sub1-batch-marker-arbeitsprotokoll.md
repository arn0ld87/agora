# Arbeitsprotokoll: Sub-Slice 137 SUB1 — Graph-Build Batch-Marker Backend

**Datum:** 2026-05-04
**Branch:** `feat/task-137-graph-build-batch-marker`
**Issue:** #137 (Layer 8, Size S)

## Diagnose

Vor diesem Slice gab `Task.progress_detail` während eines Graph-Builds keinen Marker,
wann ein Chunk-Batch committet wurde. Der `add_progress_callback` in `graph.py` setzte
`progress_detail` nicht; die 4-Arg-Callback-Signatur existierte noch nicht in
`add_text_batches`.

Konkrete Ausgangslage:

- `backend/app/services/graph_builder.py:186-254` — `add_text_batches()` rief
  `progress_callback(msg, ratio)` mit 2 Argumenten auf. Type-Hint war `Optional[Callable]`.
- `backend/app/api/graph.py:439-445` — `add_progress_callback(msg, progress_ratio)`
  setzte nur `message` und `progress`, kein `progress_detail`.
- `backend/app/models/task.py:120` — `update_task()` akzeptiert `progress_detail: Optional[Dict]`
  bereits; wird bei `None` nicht überschrieben.

## Implementierte Änderungen

### `backend/app/services/graph_builder.py`

**Zeile 191** — Type-Hint auf `Optional[Callable[[str, float, int, int], None]]` gesetzt.

**Zeilen 199-203** — Docstring-Block ergänzt, der die vier Positional-Args der Callback-Signatur
beschreibt: `msg`, `progress_ratio`, `completed`, `total`.

**Zeilen 249-253** — Callback-Aufruf um zwei neue Argumente erweitert:
```python
progress_callback(
    f"Processed {completed}/{total_chunks} chunks...",
    completed / total_chunks,
    completed,      # NEU
    total_chunks,   # NEU
)
```

**Zeile 135** — Lambda in `build_and_store_graph()` (interne Nutzung ohne `progress_detail`)
auf 4-Arg-Signatur angepasst: `lambda msg, prog, _completed, _total: ...`

### `backend/app/api/graph.py`

**Zeile 8** — `import time` ergänzt (war bereits vorhanden, kein Duplikat).

**Zeile 440** — `add_progress_callback`-Signatur von `(msg, progress_ratio)` auf
`(msg, progress_ratio, completed, total)` erweitert.

**Zeilen 446-451** — `progress_detail`-Dict im `update_task`-Aufruf ergänzt:
```python
progress_detail={
    "batch_count": completed,
    "total_batches": total,
    "batch_at": time.time(),
},
```

Alle anderen `update_task`-Aufrufe in `graph.py` (Zeilen ~391, ~401, ~414, ~432, ~453,
~467, ~474) bleiben ohne `progress_detail` — sie überschreiben den Batch-Marker nicht
(dank `if progress_detail is not None`-Guard in `task.py:148`).

### `backend/tests/api/test_graph_endpoints.py`

Zwei neue Tests am Ende der Datei (Zeilen 201-333):

**`test_add_text_batches_callback_receives_four_args`** (Unit, schnell):
- Initialisiert `GraphBuilderService` mit Mock-Storage (`add_text.side_effect` gibt
  3 Fake-UUIDs zurück).
- Ruft `add_text_batches` mit 3 Chunks auf, erfasst alle Callback-Calls.
- Verifiziert: 3 Calls, `total` konstant 3, `completed`-Werte 1/2/3 (monoton),
  `ratio` genau `completed/total`.

**`test_add_progress_callback_sets_progress_detail_on_task_manager`** (API-Level):
- Patcht `TaskManager.update_task` als Spy, der `progress_detail`-Aufrufe aufzeichnet.
- Simuliert zwei Chunk-Completions via `fake_add_text_batches`.
- Startet Build-Endpoint mit `POST /api/graph/build`, wartet bis zu 2.5 s auf
  Background-Thread.
- Verifiziert: mindestens 1 `update_task`-Call mit `progress_detail`, Felder
  `batch_count`, `total_batches`, `batch_at` vorhanden, `total_batches == 2`,
  `batch_at` ist `float`, `batch_count` monoton steigend.

## Test-Entscheidung

API-Level-Test statt reinem Unit-Test gewählt, weil der kritische Vertragspunkt das
Zusammenspiel `add_progress_callback` → `task_manager.update_task` ist. Unit-Test
allein hätte die Kopplung nicht geprüft. Spy-Pattern ohne vollständigen Integration-Stack
hält die Test-Laufzeit unter 3 s.

## Verifikations-Output

```
ruff: All checks passed (graph_builder.py, graph.py)
mypy: Success: no issues found in 2 source files
pytest tests/api/ tests/services/ -x -q -k graph: 24 passed, 240 deselected in 6.46s
pytest -x -q (Volltest): 1414 passed, 9 skipped, 4 deselected in 30.33s
```

## Offene Punkte / SUB2

**SUB2 (Frontend)** folgt im selben Branch `feat/task-137-graph-build-batch-marker`:
- `getTaskStatus`-Polling in der Frontend-Komponente liest `progress_detail.batch_count`
  und `progress_detail.batch_at`.
- Wenn sich `batch_at` ändert (neuer Batch), freezt die UI ~800 ms, damit der User
  dem Graph-Aufbau visuell folgen kann.
- Zuständiger Subagent: `agora-frontend-worker`.
