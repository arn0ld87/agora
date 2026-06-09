# fix/build-graph-complexity — Arbeitsprotokoll

**Branch:** `fix/build-graph-complexity`
**Basis:** `0df2fa2` (origin/main, 2026-05-11)
**Ziel:** `build_graph` in `app/api/graph.py` von cc=22 (Class D) unter das Gate-Limit (cc < 21, Class C) drücken, ohne neuen Allow-List-Eintrag.

## Ausgangslage

```
app/api/graph.py
    F 335:0 build_graph - D (22)
```

`bash scripts/check_complexity.sh` schlug fehl mit:

```
::error:: Neue High-Complexity-Funktionen (Cyclomatic Class D+) gefunden:
  D  app/api/graph.py::build_graph
```

## Refactor-Strategie

Extraktion von sechs privaten Helpern direkt in `app/api/graph.py` (keine neue Datei, kein Import-Impact). Die `build_task`-Closure wurde nicht angefasst (greift auf viele Closure-Locals zu, Extraktion würde mehr Komplexität erzeugen als sie beseitigt).

## Neue Helper + jeweilige cc

| Funktion | cc | Klasse |
|---|---|---|
| `_validate_build_request(data)` | 4 | A |
| `_resolve_llm_overrides(data, project)` | 2 | A |
| `_check_project_state_for_build(project, force)` | 6 | B |
| `_load_build_inputs(project_id, project, data)` | 6 | B |
| `_create_build_run_record(project_id, project, graph_name, task_manager)` | 1 | A |
| `_make_ner_override(llm_runtime, llm_model_override)` | 2 | A |

Alle Helper sind Class A oder B — kein neuer Allow-List-Eintrag nötig.

## Endwert für `build_graph`

```
F 509:0 build_graph - B (7)
```

Reduktion: D (22) → B (7), Δ = -15.

## Test-Counts

- Vorher: 1945 passed (Baseline)
- Nachher: 1945 passed, 9 skipped, 7 deselected

Keine Tests geändert. Die Monkeypatches in `tests/api/test_graph_endpoints.py` greifen weiterhin auf `app.api.graph.ProjectManager` — bleibt korrekt, da alle Helper in derselben Datei leben.

## check_complexity.sh-Output

```
OK: Keine neuen D/E/F-Klassen-Funktionen ausserhalb der Allow-List.
```

## mypy-Hinweis

5 Pre-existing-Fehler in `app/api/llm_routing.py` (Out of Scope, unverändert seit Commit `0df2fa2`). Kein neuer Fehler durch diesen Refactor eingeführt.

## Betroffene Dateien

- `backend/app/api/graph.py` (+~130 LOC durch Helper-Definitionen, -100 LOC aus `build_graph`-Body; netto ~+30 LOC)
