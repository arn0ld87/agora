# Arbeitsprotokoll — Sub-Slice 15 · Task 15 · Step4Report.vue strict-Zod

**Datum:** 2026-05-03
**Layer:** 4
**Branch:** feat/layer-4-task-15-step4report-strict-zod
**Refs:** #15 (Heuristik-Tabelle)

## Ist-Stand vor dem Slice

- Zod-Schemas (`ReportSchema`, `EvidenceMapSchema`, `ReportOutlineSchema`) waren bereits in `reportContract.ts` vorhanden
- `Step4Report.vue` nutzte die Schemas beim Laden von Report, Evidence und Outline (via `.parse()`)
- `schemaError`-State und `recordSchemaError` existierten, Template zeigte Fehler an
- `parseReportContract` (der vollständige Envelope-Validator) wurde **nicht** verwendet
- `downloadCombinedJson` lieferte unvalidierten Blob-Download

## Änderungen

### `frontend/src/components/Step4Report.vue`

1. **Import:** `parseReportContract` hinzugefügt (aus `../contracts/reportContract`)
2. **`downloadCombinedJson`**: Strikte Validierung des Export-Responses
   - Blob → Text → JSON.parse → `parseReportContract`
   - Bei `!parsed.ok`: `recordSchemaError('export', ...)` + Log-Meldung, **kein** Download
   - Bei `parsed.ok`: validierter Daten-Download (statt roher API-Response)

## Verifikation

```bash
cd frontend && npm run check
# vue-tsc --noEmit → clean
# vitest run → 146 passed
# vite build → success
```

## Akzeptanz

- [x] `parseReportContract` wird beim JSON-Export verwendet
- [x] Schema-Mismatch bricht Download ab und zeigt Fehler
- [x] TypeScript clean
- [x] 146 Frontend-Tests grün
- [x] Build success

## Nächster Slice

Reihe 14 → Task 16 · Diff/Confidence-UI (#76) · Aufwand L · `agora-frontend-worker` (Sonnet)
