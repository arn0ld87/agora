# Arbeitsprotokoll — Issue #48: Prompt-Building modularisieren

**Datum:** 2026-05-01
**Branch:** `claude/eloquent-chandrasekhar-9ef8ff`
**Slice:** v0.9.0 → EPIC-07-ST-04 — **schließt Issue #48 und EPIC-07**
**Issue:** [#48 — Prompt-Building modularisieren](https://github.com/arn0ld87/agora/issues/48)
**Vorgänger-Commit:** `2302c0e` (PR #114, Issue #47 Tool-Schema/Validation/Execution)

## Ziel

Akzeptanzkriterium: „Planung, Sections, Chat und Reflection haben
getrennte Prompt-Bausteine." Zwölf Prompt-Konstanten aus
`backend/app/services/report_agent.py` herauslösen und semantisch in
vier Clustern bündeln.

## Änderungen

### Neu: `backend/app/services/report_prompts.py` (356 LOC)

Vier semantische Cluster mit Section-Header im Modul:

1. **Planning — Outline** (2 Konstanten)
   - `PLAN_SYSTEM_PROMPT_TEMPLATE` (Outline-System-Prompt mit
     JSON-Schema und 2–5-Section-Constraint)
   - `PLAN_USER_PROMPT_TEMPLATE` (User-Prompt mit Simulationsstats und
     Sample-Facts)
2. **Sections — Body Generation** (2 Konstanten)
   - `SECTION_SYSTEM_PROMPT_TEMPLATE` (Section-System-Prompt mit
     Tool-Use-Pflicht, Markdown-Header-Verbot, Quote-Format)
   - `SECTION_USER_PROMPT_TEMPLATE` (User-Prompt mit
     `previous_content` zur Duplicate-Vermeidung)
3. **Reflection — ReACT-Loop Messages** (6 Konstanten)
   - `REACT_OBSERVATION_TEMPLATE` (Tool-Result-Injection, Counter-Anzeige)
   - `REACT_INSUFFICIENT_TOOLS_MSG` + `REACT_INSUFFICIENT_TOOLS_MSG_ALT`
     (Hinweise wenn min_tool_calls noch nicht erreicht)
   - `REACT_TOOL_LIMIT_MSG` (Cap erreicht)
   - `REACT_UNUSED_TOOLS_HINT` (Anregung zu Tool-Mischung)
   - `REACT_FORCE_FINAL_MSG` (Final-Answer erzwingen)
4. **Chat — Q&A on Finished Report** (2 Konstanten)
   - `CHAT_SYSTEM_PROMPT_TEMPLATE` (Bevorzugt Report-Content vor Tools)
   - `CHAT_OBSERVATION_SUFFIX` (kurze Concise-Aufforderung)

`__all__` listet alle 12 Namen explizit. Modul-Docstring beschreibt die
vier Cluster und verweist auf die Konsumenten in `report_agent.py`
(`plan_outline`, `_generate_section`, `_run_react_loop`,
`chat_with_report`).

### Geändert: `backend/app/services/report_agent.py` (2474 → 2179 LOC, **−295**)

- Import-Block ergänzt: `from .report_prompts import (...)` mit allen
  12 Konstanten.
- Prompt-Region Z.84–397 (313 Zeilen Template-Strings + Cluster-Header)
  durch eine 4-Zeilen-Notiz ersetzt: „Prompt-Templates leben in
  `services/report_prompts.py` (Issue #48) und werden oben re-exportiert".
- Konsumstellen unverändert:
  - `plan_outline` (Z.~1001–1002): `PLAN_*_TEMPLATE`
  - `_generate_section` (Z.~1092, 1112): `SECTION_*_TEMPLATE`
  - `_run_react_loop` (Z.~1222, 1251, 1294, 1299, 1320, 1345):
    `REACT_*`-Cluster
  - `chat_with_report` (Z.~1666, 1727):
    `CHAT_SYSTEM_PROMPT_TEMPLATE` + `CHAT_OBSERVATION_SUFFIX`

### Neu: `backend/tests/test_report_prompts.py` (47 Tests)

- **Parametrisierte Existenz/Nicht-Leere** (12×): jede Konstante ist
  `str` und nicht-whitespace-only.
- **Parametrisierte Platzhalter-Inventur** (12×): jeder Prompt enthält
  die erwarteten `{...}`-Platzhalter; schützt Caller wie
  `PLAN_USER_PROMPT_TEMPLATE.format(simulation_requirement=…, total_nodes=…, …)`
  vor versehentlicher Verkürzung.
- **`__all__`-Vollständigkeit** (1×).
- **Re-Export-Identität** (12×): `report_agent.<NAME> is
  report_prompts.<NAME>` für jede Konstante.
- **Semantik-Pinning** (`TestPromptSemantics`, 5 Tests): JSON-Outline-
  Forderung in PLAN, Markdown-Header-Verbot in SECTION, Tool-Counter
  in REACT_OBSERVATION, Report-First-Policy in CHAT, Suffix bleibt
  knapp (`< 60` Zeichen).
- **Format-Callability** (`TestFormatCallability`, 5 Tests): zentrale
  Templates werden mit Beispiel-kwargs durch `str.format()` geschickt
  — sichert balancierte `{{` / `}}`-Sequenzen für die `<tool_call>`-
  Beispielblöcke und fängt Format-Crashes zur Test-Zeit statt zur
  Laufzeit.

## Verifikation

```bash
npm run check
```

- `lint:backend` → All checks passed (Ruff)
- `test:backend` → **637 passed, 2 skipped** (vorher 590 → +47 prompt-Tests)
- `lint:frontend` → 1 warning, 0 errors (Vorzustand)
- `test:frontend` → 40 passed
- `build:frontend` → ✓ built in 3.12s

Bestehende Report-Tests (`test_report_manager`, `test_report_export`,
`test_runs_api`) unverändert grün — Re-Exports sind identitätserhaltend,
keine Caller-Anpassung nötig.

## Akzeptanzkriterium Issue #48

- [x] Planung, Sections, Chat und Reflection haben getrennte
  Prompt-Bausteine — vier Cluster in `report_prompts.py` mit explizitem
  Section-Header und gruppiertem `__all__`.

## LOC-Bilanz

- `report_agent.py`: 2474 → **2179 LOC** (−295 LOC, −11,9 %)
- Seit Issue #47-Start (vor Sub-Slice 1): 2705 → 2179 (−526, −19,4 %)
- **Seit v0.9.0-Pfad-A-Beginn: 3184 → 2179 LOC (−1005, −31,6 %, ein Drittel raus)**
- `report_prompts.py`: 0 → 356 LOC (neu, davon ~310 LOC reine Template-Strings)

## EPIC-07 Stand — abgeschlossen

Mit #48 closed: 5/5 Stories durch (#45, #46, #47, #48, #49). EPIC-07
„Domain Cleanup — Report-Agent" ist vollständig.

## v0.9.0 Stand nach diesem Slice

- **10/12 Issues closed (83 %)**
- EPIC-06 ✓ (4/4), **EPIC-07 ✓ (5/5)**, EPIC-08 zu 25 % (1/4)
- Verbleibend: nur noch **EPIC-08 #50, #51** auf `neo4j_storage.py`

## Test-Counter

- Backend: **637** (Baseline-Sprung 531 → 637, +106 in v0.9.0-Pfad-A)
- Frontend: 40 (unverändert)
- Total: **677**
