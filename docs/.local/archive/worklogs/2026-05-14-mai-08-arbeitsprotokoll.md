# MAI-08 · `report_prompts.py` Paket-Split

**Datum:** 2026-05-14
**Slice:** MAI-08
**Block:** C
**Aufwand:** M
**Subagent:** agora-refactor-worker (via Haupt-Claude, da Subagent-Dispatch nicht verfügbar)

## Ziel

`backend/app/services/report_prompts.py` (508 LOC) in vier semantische Module aufteilen:
- `planning.py` — Outline-Prompts + Default-Sections
- `sections.py` — Section-Generation-Prompts
- `react.py` — ReACT-Loop-Templates
- `chat.py` — Chat-Mode-Prompts

Re-Export über `__init__.py` garantiert Backward-Compatibility für alle Call-Sites.

## Durchführung

1. Paket-Struktur `backend/app/services/report_prompts/` angelegt.
2. Konstanten/Funktionen in vier Module verteilt (keine semantische Änderung).
3. `__init__.py` mit `__all__` erstellt — alle bestehenden Namen re-exportiert.
4. Altes `report_prompts.py` via `git rm` entfernt.
5. Import-Test bestanden:
   ```bash
   uv run python -c "from app.services.report_prompts import ..."
   ```
6. Contract-Tests: 146 passed.
7. Ruff + mypy: clean.
8. Schema-Dump idempotent (keine Drift).

## Akzeptanzkriterien

- [x] `uv run pytest tests/contracts/ -x -v` → 146 passed
- [x] `uv run ruff check .` → clean
- [x] `uv run mypy app` → Success: no issues found in 155 source files
- [x] `uv run python -m app.contracts.dump_schemas` + `git diff --exit-code schemas/` → clean
- [x] Keine Call-Site geändert (Import-Test bestätigt Re-Export)

## Referenzen

- Refs REFACTORING_PLAN (1).md §R13
- Refs `backend/app/services/report_prompts.py` (alt, 508 LOC)
