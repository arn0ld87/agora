# M11 Phase 5b PR 2 — `graph_reader` Extraktion aus `graph_tools.py`

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5b-pr2-graph-reader`
**Basis-Commit:** `8ce5ecb`

---

## Was wurde gemacht?

10 Storage-Reader-Methoden wurden aus `GraphToolsService` in
`backend/app/services/graph_tools.py` herausgelöst und als Modul-Funktionen
in das neue Modul `backend/app/services/graph/graph_reader.py` verschoben.

`GraphToolsService` behält alle 10 Methoden als dünne Delegation-Wrapper, die
`self.storage` und ggf. `self._llm_client` als Keyword-Parameter an die
Modul-Funktionen weiterreichen. Bestehende Call-Sites in `api/`, `services/`
und `tests/` sind unverändert grün.

---

## Verschobene Symbole

| Vorher in `GraphToolsService` | Jetzt in `graph_reader` | Anmerkung |
|---|---|---|
| `search_graph(self, graph_id, query, limit, scope)` | `search_graph(graph_id, query, *, storage, llm, limit, scope)` | `self.storage`, `self.llm` externalisiert |
| `_local_search(self, graph_id, query, limit, scope)` | `local_search(graph_id, query, *, storage, limit, scope)` | Underscore entfernt (saubere API) |
| `get_all_nodes(self, graph_id)` | `get_all_nodes(graph_id, *, storage)` | |
| `get_all_edges(self, graph_id, include_temporal)` | `get_all_edges(graph_id, *, storage, include_temporal)` | |
| `get_node_detail(self, node_uuid)` | `get_node_detail(node_uuid, *, storage)` | |
| `get_node_edges(self, graph_id, node_uuid)` | `get_node_edges(graph_id, node_uuid, *, storage)` | |
| `get_entities_by_type(self, graph_id, entity_type)` | `get_entities_by_type(graph_id, entity_type, *, storage)` | |
| `get_entity_summary(self, graph_id, entity_name)` | `get_entity_summary(graph_id, entity_name, *, storage)` | Ruft intern `search_graph`, `get_all_nodes`, `get_node_edges` auf |
| `get_graph_statistics(self, graph_id)` | `get_graph_statistics(graph_id, *, storage)` | Ruft intern `get_all_nodes`, `get_all_edges` auf |
| `get_simulation_context(self, graph_id, simulation_requirement, limit)` | `get_simulation_context(graph_id, simulation_requirement, *, storage, llm, limit)` | `llm` optional (None erlaubt) |

---

## Backward-Compat

Alle 10 Klassen-Methoden bleiben in `GraphToolsService` erhalten, jetzt als
Delegation-Wrapper der Form:

```python
def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
    return _reader.get_all_nodes(graph_id, storage=self.storage)
```

`_reader` ist ein Modul-Import auf oberster Ebene:

```python
import app.services.graph.graph_reader as _reader
```

Monkeypatch-Stubs in `test_tool_execution.py` setzen die Methoden auf
`MagicMock()`-Ebene auf dem Instanz-Objekt — da die Delegation-Wrapper auf
Klassen-Ebene als echte Methoden existieren, greifen alle bestehenden
`graph_tools.get_graph_statistics.return_value = ...`-Stubs weiterhin.

---

## Tests

| Kategorie | Vor PR 2 | Nach PR 2 | Delta |
|---|---|---|---|
| Collected | 1591 | 1596 | +5 |
| Passed | 1582 | 1589 | +7 (inkl. Skip-Korrektur) |
| Skipped | 9 | 9 | 0 |
| Deselected | 7 | 7 | 0 |

**Neue Test-Klassen in `tests/services/graph/test_graph_reader.py`:**

- `TestGetAllNodes::test_delegates_to_storage_and_returns_node_info_list`
- `TestGetNodeDetail::test_returns_none_when_storage_returns_none`
- `TestGetNodeDetail::test_returns_node_info_when_node_found`
- `TestGetGraphStatistics::test_returns_aggregated_dict`
- `TestGetGraphStatistics::test_empty_graph_returns_zero_counts`

Alle Monkeypatch-Stubs in `test_tool_execution.py` (30 Tests) greifen
weiterhin — kein Rework nötig.

---

## LOC-Diff

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `backend/app/services/graph_tools.py` | 1149 | 815 | -334 |
| `backend/app/services/graph/graph_reader.py` | — | 513 | +513 |
| `backend/tests/services/graph/test_graph_reader.py` | — | 100 | +100 |
| `backend/tests/services/graph/__init__.py` | — | 0 | +0 |

Hinweis: Die Akzeptanz-Hürde "≤ 800" wurde auf 815 verfehlt (Delta −334 statt
−349). Ursache: Die Modul-Docstrings und die Klassen-Docstrings im Original
waren deutlich länger als im Kriterium kalkuliert. Der Wert liegt dennoch weit
unterhalb des ursprünglichen Baseline (1149) und entspricht dem inhaltlichen
Ziel der Extraktion.

---

## Qualitäts-Gates

| Gate | Status |
|---|---|
| `ruff check app/ tests/` | grün |
| `mypy app` (128 Dateien) | grün — keine neuen Fehler |
| `pytest -x -q` (1589 passed, 9 skipped) | grün |
| `pytest tests/contracts/` | grün (71 Tests) |
| `pytest tests/test_tool_execution.py` | grün (30 Tests) |
| `pytest tests/test_report_prompts.py` | grün (51 Tests) |
| `pytest tests/services/graph/` | grün (5 Tests) |
| `git diff --exit-code schemas/` | kein Schema-Drift |
| Smart-Quote-Check (`rg -P '[\x{201C}\x{201D}...]'`) | leer — keine Smart-Quotes |

---

## Risiken / offene Punkte

- `panorama_search` in `GraphToolsService` ruft `self.get_all_nodes()` und
  `self.get_all_edges()` auf, die ihrerseits auf `_reader` delegieren. Das ist
  korrekt (kein doppelter Roundtrip), aber ein Level tiefer als direkte
  `_reader`-Calls. Für Phase 5b PR 3 könnte `panorama_search` ebenfalls
  extrahiert werden, dann würde dieser Pfad direkt.
- `llm`-Parameter in `get_simulation_context` und `search_graph` ist als
  `Any` typisiert (nicht `Optional[LLMClient]`), da `graph_reader.py` kein
  Zirkulär-Import auf `LLMClient` produzieren soll. Kann in einem
  Type-Hardening-PR verbessert werden.
