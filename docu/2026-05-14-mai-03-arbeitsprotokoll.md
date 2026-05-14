# MAI-03 · R11 Hypothesen-Slot voll integrieren — Arbeitsprotokoll

**Datum:** 2026-05-14
**Subagent:** keiner (User-Freigabe: Umsetzung ohne Subagent)
**Branch:** feat/mai-03-hypotheses-slot
**Commit:** ausstehend

## Befund

ReportV3 hatte keinen dedizierten `hypotheses[]`-Slot. `ReportManager.build_report_v3()` routete Hypothesen aus der Evidence-Map in `data_gaps[]`; dadurch wurden strukturelle Datenlücken und unbelegte inhaltliche Hypothesen vermischt.

## Edits

- `backend/app/contracts/report_v3.py` — neues `Hypothesis`-DTO und `ReportV3.hypotheses` ergänzt.
- `backend/app/contracts/__init__.py` — `Hypothesis` re-exportiert.
- `backend/app/services/report_agent/manager.py` — Hypothesen werden in `ReportV3.hypotheses[]` gemappt, nicht mehr in `data_gaps[]`.
- `backend/app/services/report_agent/markdown_renderer.py` — separater ReportV3-Markdown-Block `## Hypothesen ohne Evidence` plus Tabelle.
- `frontend/src/contracts/reportV3Contract.ts` — Zod-Spiegel um `HypothesisSchema` und `ReportV3Schema.hypotheses` erweitert.
- `schemas/report-v3.schema.json` — per `python -m app.contracts.dump_schemas` regeneriert.
- `backend/tests/services/test_report_v3_hypotheses.py` — Regressionstest für Routing und Rendering ergänzt.
- `backend/tests/contracts/test_report_v3_contract.py` — Contract-Roundtrip um Hypothesen erweitert.
- `backend/tests/services/test_report_v3_markdown_renderer.py` — Markdown-Renderer auf separaten Hypothesen-Block gepinnt.
- `frontend/src/contracts/__tests__/reportV3Contract.spec.ts` — Zod-Drift-Guard um `HypothesisSchema` erweitert.

## Tests

- `cd backend && uv run python -m app.contracts.dump_schemas` — grün; zweiter Dump erzeugt keinen weiteren Schema-Diff.
- `cd backend && uv run pytest tests/contracts/ -x -v` — 146 passed.
- `cd backend && uv run pytest tests/services/test_report_v3_hypotheses.py -x -v` — 3 passed.
- `cd backend && uv run pytest tests/contracts/test_report_v3_contract.py tests/services/test_report_v3_hypotheses.py tests/services/test_report_v3_markdown_renderer.py -q` — 35 passed.
- `cd backend && uv run pytest -x -q` — rot ohne lokale `LLM_API_KEY` (`test_add_progress_callback_sets_progress_detail_on_task_manager`), danach `LLM_API_KEY=test uv run pytest -x -q` — 1999 passed, 9 skipped, 7 deselected.
- `cd backend && uv run ruff check .` — grün.
- `cd backend && uv run mypy app` — grün.
- `cd frontend && npm run check` — 84 files / 689 tests passed, Build grün.

## Akzeptanz erfüllt?

- [x] `ReportV3.hypotheses` existiert als eigener Slot.
- [x] Hypothesen landen nicht mehr in `data_gaps[]`.
- [x] Markdown rendert Hypothesen getrennt von Data Gaps.
- [x] Zod-Spiegel und Schema-Dump enthalten `hypotheses`.

## Folge-Slices

MAI-14 ist bereits auf `origin/main`; Block B ist nach erfolgreichem Verify von MAI-03 fachlich geschlossen.
