# Arbeitsprotokoll Task #274 — plan_outline: ReportOutlineModel mit description-Feld

**Datum:** 2026-05-04
**Branch:** feat/task-274-outline-section-contract
**Layer:** 0 / 1

---

## Symptom

Frontend-Zod-Validation schlaegt fehl bei jedem generierten Report:

```
Schema-Mismatch in outline:
sections.0.description: Invalid input
sections.1.description: Invalid input
...
```

## Root Cause

`report_agent.py::plan_outline()` (Z. 947-955) baute Outline-Sections mit dem
falschen Typ `ReportSection` (Dataclass mit `title`/`content`), statt mit
`ReportOutlineSectionModel` (Pydantic, `title`/`description`).

Zwei konkrete Fehler:
1. `ReportSection.to_dict()` emittierte `{"title", "content"}` — kein `description`.
2. Das `description`-Feld aus dem LLM-Response wurde komplett ignoriert.
3. Auch der Fallback-Pfad (Z. 967-974) und der Disk-Load-Pfad (Z. 2291-2294)
   waren gleich fehlerhaft.

Konsequenz: `_map_outline_for_contract()` in `api/report.py` mappt `content` auf
`description` (Zeile 412), aber der Streaming-Status-Endpoint (Z. 227) ruft
`outline.to_dict()` direkt ohne diese Umformung auf. Zod-strict im Frontend
failt dann, weil `description` fehlt oder leer ist.

## Fix

### 1. `backend/app/models/report.py`

`ReportSection`-Dataclass um `description: str = ""` erweitert.
`to_dict()` emittiert jetzt auch `"description"`.

### 2. `backend/app/services/report_agent.py`

- Import `ReportOutlineModel`, `ReportOutlineSectionModel` aus
  `app.contracts.report_contract` ergaenzt (Z. 26).
- `plan_outline()` happy path (Z. 944-972): Baut erst `ReportOutlineSectionModel`
  mit Pydantic-Validation (description-Pflichtfeld, Default-Fill `"—"` bei leer),
  dann `ReportOutlineModel`, dann konvertiert zurueck zu `ReportOutline`/`ReportSection`
  mit `description` gesetzt.
- `plan_outline()` fallback path (Z. 979-999): Alle 3 Default-Sections haben
  jetzt sinnvolle `description`-Texte.
- `ReportManager.get_report()` Disk-Load (Z. 2313-2322): Laedt `description`
  aus JSON (Prio 1: gespeichertes `description`, Prio 2: `content` fuer Legacy-Eintraege,
  Default: `"—"`).

## Verify

```
rg -n "ReportSection\(title=" backend/app/services/report_agent.py
```
→ kein Output (clean).

```
uv run pytest tests/services/test_report_agent_outline.py -x -v
```
→ 4 passed (happy-path, leeres-description, fallback, rauchtest).

```
uv run pytest -x -q
```
→ 1429 passed, 9 skipped.

```
uv run ruff check app/ tests/
```
→ All checks passed!

```
uv run python -m app.contracts.dump_schemas && git diff --exit-code schemas/
```
→ Schema-Drift: CLEAN.

## Akzeptanz-Haekchen

- [x] `plan_outline()` baut `ReportOutlineModel` intern, konvertiert zu `ReportOutline`.
- [x] `description` aus LLM-Response wird uebernommen, nicht verworfen.
- [x] Leeres `description` wird mit `"—"` aufgefuellt (min_length=1 erfuellt).
- [x] Fallback-Pfad liefert valide Outline (alle Felder contract-konform).
- [x] Disk-Load-Pfad laedt `description` korrekt (Legacy-Fallback auf `content`).
- [x] Test in `backend/tests/services/test_report_agent_outline.py`:
      - happy-path (3 sections mit description)
      - leeres-description-edge-case (Default-Fill)
      - fallback-Pfad (LLM raised)
      - Rauchtest (to_dict emittiert description)
- [x] Bestandstests gruen: 1429 passed.
- [x] Schema-Dump idempotent.
- [x] ruff clean, mypy-Fehler in geaenderten Dateien nur pre-existing.
- [ ] Frontend laedt Report ohne Zod-Fehler (Frontend-Verifikation Folge-Schritt).
