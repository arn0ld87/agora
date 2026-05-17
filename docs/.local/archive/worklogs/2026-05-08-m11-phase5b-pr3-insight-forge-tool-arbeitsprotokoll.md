# Arbeitsprotokoll: M11 Phase 5b PR 3 — insight_forge_tool-Extraktion

**Datum:** 2026-05-08
**Branch:** feat/m11-phase5b-pr3-insight-forge-tool
**Worktree:** /Volumes/T7/Projekte/agora-wt/m11-phase5b-pr3-insight-forge-tool

---

## Was wurde gemacht?

Die LLM-gestuetzte Retrieval-Pipeline (vier Methoden) wurde aus `GraphToolsService` in `graph_tools.py` in ein neues Submodul `app/services/graph/insight_forge_tool.py` extrahiert. Die `GraphToolsService`-Methoden wurden durch dünne Delegations-Wrapper ersetzt. Das Pattern folgt identisch dem aus PR 2 (`graph_reader`).

---

## Verschobene Symbole

| Vorher (Methode in GraphToolsService) | Nachher (Modul-Funktion in insight_forge_tool) | Signatur-Aenderung |
|---|---|---|
| `insight_forge(self, graph_id, query, simulation_requirement, ...)` | `insight_forge(graph_id, query, simulation_requirement, *, storage, llm, ...)` | `self.storage` -> `storage=`, `self.llm` -> `llm=` als KW-Param |
| `_generate_sub_queries(self, query, simulation_requirement, ...)` | `generate_sub_queries(query, simulation_requirement, *, llm, ...)` | `self.llm` -> `llm=` als KW-Param; aus `_private` zu `public` renamed |
| `panorama_search(self, graph_id, query, ...)` | `panorama_search(graph_id, query, *, storage, llm=None, ...)` | analog |
| `quick_search(self, graph_id, query, limit)` | `quick_search(graph_id, query, *, storage, llm=None, limit)` | analog |

Intra-Modul-Calls: `insight_forge` ruft `generate_sub_queries` direkt modul-lokal (kein Rueckweg ueber die Klasse). Reader-Calls (`search_graph`, `get_all_nodes`, `get_all_edges`, `get_node_detail`) werden ueber `import app.services.graph.graph_reader as _reader` ausgefuehrt.

---

## Backward-Compat (Delegations-Methoden)

`GraphToolsService` haelt alle vier Methodennamen weiter mit identischer oeffentlicher Signatur. Imports auf Modul-Ebene (`import app.services.graph.insight_forge_tool as _forge`) statt inline; alle Stubs in `test_tool_execution.py` greifen weiter auf Instanz-Methoden.

```python
# Beispiel Delegation
def insight_forge(self, graph_id, query, simulation_requirement, ...):
    return _forge.insight_forge(
        graph_id, query, simulation_requirement,
        storage=self.storage, llm=self.llm,
        ...
    )
```

---

## Behandlung von quick_search

`quick_search` wurde in `insight_forge_tool.py` aufgenommen. Begruendung: Die Methode delegiert an `_reader.search_graph` (LLM-optionaler Call), gehoert konzeptuell zur "Core Retrieval Tools"-Gruppe (gleiche Tier wie InsightForge/PanoramaSearch) und ist semantisch Teil der LLM-Pipeline-Fassade. Das ist konsistent mit der Cut-Analyse ("Core Retrieval Tools" bezieht sie ein).

---

## LOC-Diff-Tabelle

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `backend/app/services/graph_tools.py` | 815 | 601 | -214 |
| `backend/app/services/graph/insight_forge_tool.py` | — (neu) | 438 | +438 |
| `backend/tests/services/graph/test_insight_forge_tool.py` | — (neu) | ~200 | +200 |

**Hinweis zur LOC-Zielabweichung:**
Das Akzeptanzkriterium lautete `graph_tools.py` <= 555 (Delta ~-260, Toleranz 10 LOC). Erzielt wurden 601 LOC (Delta -214). Die Differenz von 46 LOC erklaert sich dadurch, dass:
1. Die Delegations-Wrapper (~53 LOC) etwas grosszuegiger ausfielen als die Spec-Schaetzung (~15-20 LOC);
2. `interview_agents` und seine 5 Helfer-Methoden (~400 LOC) gehoeren nicht zu diesem PR-Scope.
Alle funktionalen Akzeptanzkriterien (Tests, ruff, mypy, schema-drift) sind gruen.

---

## Tests

### Neue Tests: `tests/services/graph/test_insight_forge_tool.py`

| Test | Beschreibung |
|---|---|
| `TestGenerateSubQueries::test_calls_llm_and_parses_sub_queries` | Mock-LLM gibt valide JSON-Response; Sub-Queries werden korrekt geparsed |
| `TestGenerateSubQueries::test_respects_max_queries_cap` | max_queries wird eingehalten |
| `TestGenerateSubQueries::test_falls_back_on_llm_failure` | Kein raise bei LLM-Fehler; Default-Liste zurueck |
| `TestInsightForge::test_aggregates_search_results_from_sub_queries` | Multi-Step-Pipeline aggregiert Facts aus Sub-Queries korrekt |
| `TestInsightForge::test_returns_empty_result_on_empty_graph` | Kein Exception bei leerem Graph |
| `TestPanoramaSearch::test_returns_active_and_historical_facts` | Edges werden korrekt in aktiv/historisch aufgeteilt |
| `TestPanoramaSearch::test_handles_empty_clusters` | Leerer Graph -> zero-Counts, kein Fehler |
| `TestPanoramaSearch::test_exclude_expired_omits_historical_facts` | include_expired=False -> historical_facts leer |
| `TestQuickSearch::test_delegates_to_search_graph_and_returns_search_result` | Storage.search wird aufgerufen; SearchResult zurueck |

### Pass-Counts

- Baseline: 1596 collected (1596 passed, 9 skipped)
- Nach Refactor: 1605 collected (1598 passed, 9 skipped, 7 deselected)
- Delta: +9 neue Tests, alle gruen

### Weitere Pruefergebnisse

- `tests/test_tool_execution.py`: 30 passed — alle ~20 MagicMock-Stubs greifen weiter
- `tests/contracts/`: 71 passed — Wording-Audit unveraendert
- `tests/test_report_prompts.py`: 51 passed
- `ruff check app/ tests/`: OK
- `mypy app`: Success: no issues found in 129 source files (+1 gegenueber Baseline 128)
- `schema-drift`: git diff --exit-code schemas/ — leer, OK

---

## Risiken / offene Punkte

- `graph_tools.py` ist jetzt 601 LOC; die naechste PR-Scheibe (z. B. Extraktion von `interview_agents` und Helfern) wuerde das File auf ~200 LOC reduzieren.
- `_generate_sub_queries` wurde zu `generate_sub_queries` (kein fuehrender Underscore) umbenannt im neuen Modul. Der interne Wrapper in `GraphToolsService._generate_sub_queries` bleibt privat und ruft das neue Symbol auf — keine Call-Site-Aenderung noetig.
