# Arbeitsprotokoll: M11 Phase 5b PR 1 — `graph_dtos`-Extraktion

**Datum:** 2026-05-08
**Branch:** `feat/m11-phase5b-pr1-graph-dtos`
**Basis-Commit:** d3f3faa

---

## Was wurde gemacht?

Die 7 Dataclasses aus `backend/app/services/graph_tools.py` (Zeilen 24–373, ~350 LOC) wurden in ein neues Submodul `backend/app/services/graph/graph_dtos.py` ausgegliedert. `graph_tools.py` re-exportiert alle 7 Symbole via aliased imports (PEP 484 §re-exports-Muster, identisch zu M11 Phase 5 sim-Submodulen).

---

## Wohin wurden welche Symbole verschoben?

| Symbol | Vorher | Nachher |
|---|---|---|
| `SearchResult` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `NodeInfo` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `EdgeInfo` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `InsightForgeResult` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `PanoramaResult` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `AgentInterview` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |
| `InterviewResult` | `app.services.graph_tools` | `app.services.graph.graph_dtos` |

Alle Methoden (`to_dict`, `to_text`, Properties `is_expired`/`is_invalid`) wurden 1:1 mit verschoben.

---

## Neue Dateien

- `backend/app/services/graph/__init__.py` — Package-Init (1 LOC Docstring)
- `backend/app/services/graph/graph_dtos.py` — 360 LOC (die 7 Dataclasses)

---

## Backward-Compat (Re-Export-Pattern)

`graph_tools.py` re-exportiert alle 7 Symbole via aliased imports analog zum sim-Phase-5-Pattern:

```python
from .graph.graph_dtos import SearchResult as SearchResult  # noqa: PLC0414
from .graph.graph_dtos import NodeInfo as NodeInfo  # noqa: PLC0414
# ... etc.
```

Smoke-Test bestaetigt:
- `from app.services.graph_tools import SearchResult` funktioniert weiter
- Das importierte Objekt ist `app.services.graph.graph_dtos.SearchResult` (korrekte Herkunft)

Externe Caller (`app/services/report_agent/agent.py`, `app/api/report.py`, `app/api/runs.py`) wurden nicht angefasst — ihre Imports aus `graph_tools` funktionieren unveraendert.

---

## Wording-Audit-Erweiterung

`backend/tests/test_report_prompts.py::TestPromptSemantics::test_graph_tools_to_text_has_no_forecast_marketing` wurde erweitert:

- Liest jetzt **beide** Dateien: `graph_tools.__file__` UND `_graph_dtos.__file__`
- Konkateniert beide Sourcen vor dem Audit
- Positive Assertions (z.B. `"Scenario Evaluation Deep Analysis"`) greifen auf `graph_dtos.py` durch, da die `to_text()`-Methoden dort leben

Ohne diese Erweiterung waere die Wording-Audit-Abdeckung nach der Extraktion blind gewesen.

---

## LOC-Diff

| Datei | Vorher | Nachher | Delta |
|---|---|---|---|
| `backend/app/services/graph_tools.py` | 1492 | 1149 | -343 |
| `backend/app/services/graph/__init__.py` | neu | 2 | +2 |
| `backend/app/services/graph/graph_dtos.py` | neu | 360 | +360 |
| `backend/tests/test_report_prompts.py` | +5 Zeilen | — | +5 |

Netto: -343 + 362 = +19 LOC gesamt (Re-Export-Block + Package-Init + Audit-Erweiterung).

---

## Tests

| Suite | Ergebnis |
|---|---|
| `pytest -x -q` (gesamt) | 1584 passed, 9 skipped (Baseline unveraendert) |
| `pytest tests/contracts/ -x -v` | 71 passed |
| `pytest tests/test_report_prompts.py -v` | 51 passed |
| `ruff check app/ tests/` | All checks passed |
| `mypy app` | Success: no issues found in 127 source files (+2 gegenueber Baseline 125) |
| Schema-Drift (`git diff schemas/`) | kein Diff |
| Re-Export-Smoke | OK |

---

## Risiken / Offene Punkte

- **Dataclasses bleiben als Dataclasses** (nicht auf Pydantic migriert). Die CLAUDE.md-Konvention
  verbietet neue `@dataclass` nur in `app/api/` und `app/contracts/`. DTOs in `app/services/graph/`
  sind akzeptabel. Eine spaetere Pydantic-Migration ist moeglich, aber ausserhalb dieses PRs.
- **`AgentInterview.to_text()` enthaelt komplexe Unicode-String-Manipulation** (chinesische Zeichen).
  Wurde 1:1 uebernommen, keine Verhaltensaenderung.
- Der Wording-Audit-Test prueft nur Source-Code auf verbotene Phrasen, nicht Runtime-Output.
  Das ist ausreichend, da die Phrasen statische Strings in `to_text()` sind.
