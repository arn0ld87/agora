# Arbeitsprotokoll — Issue #47, Sub-Slice 1: Tool-Schema-Modul extrahieren

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-07-ST-03 → Sub-Slice 1 (von 3)
**Issue:** [#47 — Tool-Schema und Tool-Execution trennen](https://github.com/arn0ld87/agora/issues/47)
**Vorgänger-Commit:** `1c8f654` (PR #113, Issue #52 Backend-Graph-DTOs)

## Ziel

Erste Akzeptanz-Bedingung von Issue #47 erfüllen: Tool-Beschreibungen aus
`backend/app/services/report_agent.py` in ein eigenes Modul ziehen, damit
Schema-Pflege unabhängig von der Execution-Logik passieren kann. Re-Export
hält alle Aufrufstellen (intern: `_define_tools()`, extern: keine) stabil.

## Änderungen

### Neu: `backend/app/services/tool_schema.py` (96 LOC)

- Modul-Docstring mit Issue-Verweis und Begründung des Splits.
- Vier Konstanten 1:1 aus `report_agent.py` Z.69–141 übernommen:
  `TOOL_DESC_INSIGHT_FORGE`, `TOOL_DESC_PANORAMA_SEARCH`,
  `TOOL_DESC_QUICK_SEARCH`, `TOOL_DESC_INTERVIEW_AGENTS`.
- `__all__`-Export für klares Modul-API.
- Pattern analog zu `services/report_logger.py` (Issue #46) — Re-Export im
  Konsumenten, Quelle hier.

### Geändert: `backend/app/services/report_agent.py` (2705 → 2640 LOC, −65)

- Import-Block ergänzt: `from .tool_schema import TOOL_DESC_INSIGHT_FORGE,
  TOOL_DESC_PANORAMA_SEARCH, TOOL_DESC_QUICK_SEARCH, TOOL_DESC_INTERVIEW_AGENTS`.
- Konstanten-Block Z.69–141 durch Kommentar-Notiz ersetzt (verweist auf
  `tool_schema.py`).
- `_define_tools()` Z.938–962 unverändert — konsumiert die re-exportierten
  Namen unverändert.

### Neu: `backend/tests/test_tool_schema.py` (4 Tests)

1. `test_tool_schema_exports_all_four_descriptions` — `__all__` deckt alle
   vier Konstanten ab.
2. `test_tool_descriptions_are_non_empty_strings` — alle Konstanten sind
   nicht-leere Strings.
3. `test_report_agent_re_exports_identity` — der Re-Export im
   `report_agent`-Modul liefert dasselbe Objekt (Wire-Identity, schützt
   vor versehentlicher Kopie/Drift).
4. `test_descriptions_carry_use_cases_and_return_content_sections` —
   pinnt das Schema-Format (`[Use Cases]`, `[Return Content]`) gegen
   versehentliche Verkürzung in künftigen Slices.

## Verifikation

```bash
npm run check
```

Ergebnis: **5/5 grün**
- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **535 passed, 2 skipped** (vorher 531 → +4 tool_schema-Tests)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand, unverändert)
- `test:frontend` → **40 passed**
- `build:frontend` → ✓ built in 3.13s

## Akzeptanzkriterien Issue #47

- [x] Tool-Beschreibung separat — Sub-Slice 1 ✓
- [ ] Tool-Validation separat testbar — Sub-Slice 2 (folgt)
- [ ] Tool-Ausführung separat — Sub-Slice 3 (folgt)

## LOC-Bilanz

- `report_agent.py`: 2705 → **2640 LOC** (−65 LOC, −2.4 %)
- Seit v0.9.0-Pfad-A-Beginn: 3184 → 2640 LOC (−544, −17 %)
- `tool_schema.py`: 0 → 96 LOC (neu, davon ~74 LOC reine Konstanten-Strings)

## Folge-Slices

- **Sub-Slice 2**: `_is_valid_tool_call` + `_parse_tool_calls` (Z.~1133)
  in `services/tool_validation.py` ziehen, separat unit-testbar machen.
- **Sub-Slice 3**: `_execute_tool` (Z.~996) + Tool-Dispatch in
  `services/tool_execution.py`; ReportAgent-Methode bleibt 1-Zeilen-Delegation.

Beide Sub-Slices folgen dem hier etablierten Re-Export-Pattern.
