# Sub-Slice M11.7c — ReportSection.hypotheses[] + Frontend-Renderer

**Datum:** 2026-05-10  
**Branch:** `feat/m11-7c-report-hypotheses`  
**Spec:** ADR-0002 Evidence-Gating, Roll-out M11.7c  
**Vorgaenger:** M11.7b (`EvidenceSourceKind` + Cross-Stakeholder/Inferred-Validators)

## Ziel

Hypothesen ohne Evidence duerfen nicht als belegte `claims[]` erscheinen. Dieser
Slice fuehrt dafuer einen separaten, streng validierten Slot ein:

- `ReportSectionHypothesisModel` mit `hypothesis_id`, `hypothesis_text`,
  `rationale`, `suggested_evidence`.
- `ReportSectionModel.hypotheses[]` mit Default `[]`.
- Frontend-Zod-Spiegel und Evidence-Inspector-Rendering getrennt von Claims.

Die bestehende `claims`-Semantik bleibt bewusst unveraendert: belegte Claims
laufen weiter durch Confidence-/Evidence-Validatoren, Hypothesen werden im UI
als "Hypothesen ohne Evidence" markiert.

## Geaenderte Dateien

| Datei | Änderung |
|---|---|
| `backend/app/contracts/report_contract.py` | Neues `ReportSectionHypothesisModel`, Feld `ReportSectionModel.hypotheses` |
| `backend/app/contracts/__init__.py` | Re-Export `ReportSectionHypothesisModel` |
| `frontend/src/contracts/reportContract.ts` | Zod-Spiegel `ReportSectionHypothesisSchema` + `hypotheses` |
| `frontend/src/components/step4/ReportEvidencePanel.vue` | Separater Hypothesen-Block vor Claims |
| `backend/tests/contracts/test_report_section_hypotheses.py` | Neue Contract-Guards |
| `backend/tests/contracts/test_report_contract.py` | Canonical Roundtrip mit Hypothese |
| `frontend/src/contracts/__tests__/reportContract.spec.ts` | Zod-Guards fuer Hypothesen |
| `frontend/src/components/__tests__/Step4Report.spec.ts` | Render-Guard fuer Hypothesen |
| `schemas/evidence-map.schema.json` / `schemas/report-contract.schema.json` | Auto-Dump mit Hypothesen-DTO |

## Verifikation

```bash
cd backend && uv run pytest tests/contracts/test_report_section_hypotheses.py tests/contracts/test_report_contract.py -q
# 20 passed

cd backend && uv run ruff check app/contracts/report_contract.py tests/contracts/test_report_section_hypotheses.py tests/contracts/test_report_contract.py
# All checks passed

cd backend && uv run python -m app.contracts.dump_schemas
# 12/12 schemas refreshed

cd frontend && npm ci
cd frontend && npm test -- --run src/contracts/__tests__/reportContract.spec.ts src/components/__tests__/Step4Report.spec.ts
# 2 files / 31 tests passed
```

## Bewusst nicht enthalten

- Keine Relaxation von `ReportSectionModel.claims` (`min_length=1`). Der Slice
  fuehrt den Hypothesen-Slot ein, ohne bestehende Evidence-Map-Validierung zu
  lockern.
- Keine Generator-Logik fuer automatisches Befuellen von `hypotheses[]`. Das
  bleibt Teil der naechsten Evidence-Gating-Welle bzw. der Snapshot-Eval-Suite.

## Folgeauftrag

**M11.7d:** Snapshot-Eval-Suite mit fixen Bad-/Good-Cases gegen Evidence-Gating,
inklusive Beispielen fuer Hypothesen ohne Evidence und cross-stakeholder-konforme
High-Claims.
