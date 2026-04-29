# Slice 5: Export Center

## Sub-Slice 5.1 — Report-Export stabilisieren (JSON + MD)

### Ziel

Reports lassen sich in einer kombinierten JSON-Hülle exportieren (Report + Evidence-Map mit `schema_version`) und es gibt einen einheitlichen Markdown-Endpoint mit konsistenter Dateibenennung.

### Vorgehen

1. `backend/app/api/report.py`
   - Neuer Endpoint `GET /api/report/<report_id>/export?format=md|json`.
   - `format=md` schickt die gerenderte Markdown-Datei als Attachment, Fallback auf `report.markdown_content`, wenn `report.md` (noch) nicht persistiert ist.
   - `format=json` liefert eine Hülle `{schema_version, exported_at, report, evidence}` als Attachment. `evidence` ist `null`, wenn keine Evidence-Map vorliegt.
   - Dateiname-Konvention: `agora-report-<report_id>.{md,json}`.
   - `EXPORT_SCHEMA_VERSION = 1`.
   - Bestehender `/<report_id>/download`-Endpoint bleibt unverändert (Alias / Abwärtskompatibilität).
2. `frontend/src/api/report.js`
   - Neuer Helper `exportReport(reportId, format)` mit `responseType: 'blob'`.
3. `frontend/src/components/Step4Report.vue`
   - Neuer `.json`-Button neben `.md` in der Report-Toolbar.
   - `downloadCombinedJson()` lädt das JSON-Bundle über den neuen Endpoint und triggert den Browser-Download.
   - `Evidence JSON`-Knopf bleibt erhalten — die zwei Exports sind komplementär (kombiniert vs. nur Evidence-Subset).
4. `backend/tests/test_report_export.py` (neu)
   - Tests: ungültige `report_id`, ungültiges `format`, fehlender Report (404), MD-Default, MD-Attachment, JSON-Hülle inklusive Evidence, JSON ohne Evidence (`evidence: null`).

### Bewusst nicht geändert

- `/<report_id>/download` wurde nicht entfernt oder umgebaut, damit externe Consumer / bestehende Bookmarks nicht brechen.
- `getReport` / `getReportEvidence` bleiben bestehen — der neue Export-Endpoint ist additiv und ersetzt sie nicht.
- HTML-Export bleibt clientseitig (`buildStandaloneHtml` in `Step4Report.vue`) — kein Server-Endpoint nötig, solange der Markdown-Renderer im Frontend lebt.
- CSV-, GraphML-, PNG/SVG- und PDF-Exports sind in den Sub-Slices 5.2–5.5 verortet und werden hier bewusst nicht angefasst.

### Verifikation

```bash
cd backend && uv run pytest tests/test_report_export.py
npm run check
```

`npm run check` grün: 274 Backend-Tests, Frontend-Lint, Vite-Build.
