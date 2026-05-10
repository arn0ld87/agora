# Arbeitsprotokoll Sub-Slice P4.2 — CSV-Export

**Datum:** 2026-05-10
**Branch:** p4-2-csv-export
**Refs:** PLAN.md §5.2

## Ziel

RFC-4180-konformes CSV für drei Tabellen: `personas`, `segments`, `claims`.
Endpoint erweiterung in bestehendem `GET /api/report/<report_id>/export`.
Frontend-Composable `downloadCsv` + `downloadCsvBundle`.

## Umsetzung

### Backend

**`backend/app/services/report_agent/csv_export.py`** (neu, 117 LOC):
- `personas_to_csv(personas: list[dict]) -> str`
- `segments_to_csv(segments: list[dict]) -> str`
- `claims_to_csv(sections: list[dict]) -> str`
- Keine Flask-Abhängigkeit. Nutzt `csv.writer` mit `dialect="excel"` (CRLF, MINIMAL-Quoting).
- Listen-Felder (`needs`, `values`, `evidence_refs`, `persona_ids`) werden als Semikolon-Join serialisiert.

**`backend/app/api/report.py`** (erweitert):
- Import der drei csv_export-Funktionen.
- Neues `frozenset _CSV_TABLES = {"personas", "segments", "claims"}`.
- `export_report()` erweitert: `format=csv` zweig mit `table`-Validation.
- Hilfsfunktion `_build_csv_export(report_id, table)`:
  - personas/segments: aus `ReportManager.get_report_v3()` (report-v3.json), kein hartes Coupling.
  - claims: aus `ReportManager.get_evidence_map()` (evidence-map.json, Sections[].claims[]).

### Datenquellen (ohne hartes ReportV3-Coupling)

| Tabelle  | Quelle                            | Fallback bei fehlendem Artefakt |
|----------|-----------------------------------|---------------------------------|
| personas | report-v3.json `.personas[]`      | leere Liste → nur Header-Row    |
| segments | report-v3.json `.segments[]`      | leere Liste → nur Header-Row    |
| claims   | evidence-map.json `.sections[].claims[]` | leere Liste → nur Header-Row |

### Frontend

**`frontend/src/api/report.ts`** (erweitert):
- `fetchReportCsv(reportId, table: 'personas'|'segments'|'claims'): Promise<Blob>`
- Nutzt `service.get(..., { responseType: 'blob' })` analog `exportReport`.

**`frontend/src/composables/useReportExports.ts`** (erweitert):
- `downloadCsv(table, filename?) : Promise<void>` — lädt eine Tabelle, loggt Fehler.
- `downloadCsvBundle() : Promise<void>` — `Promise.allSettled` über alle drei Tabellen,
  Einzeldownloads (jszip nicht installiert; ZIP als TODO vermerkt).
- Beide Funktionen werden aus `useReportExports()` exportiert.

**jszip-Status:** Nicht installiert (nicht in `package.json`). Bundle als 3 Einzeldownloads implementiert. ZIP-Bundle ist als TODO im CHANGELOG vermerkt — separater Sub-Slice wenn jszip als Dependency hinzugefügt wird.

## Tests

### Backend (18 neue Tests in `tests/api/test_report_export_csv.py`)
- Unit-Tests: `personas_to_csv`, `segments_to_csv`, `claims_to_csv` (RFC-4180-Quoting, Header, Listenserialisierung, None-Handling).
- Endpoint-Tests: 200 für alle drei Tabellen, 404 bei unbekanntem report_id, 400 für `format=xml`, 400 für `table=foo`, Content-Disposition-Header.

### Frontend (7 neue Tests in `useReportExports.spec.ts`)
- `downloadCsv`: fetchReportCsv aufgerufen, Blob-Download ausgelöst, korrekter Dateiname, optionaler Filename, Fehler-Logging.
- `downloadCsvBundle`: alle drei Tabellen geladen, partieller Fehler geloggt.

### Test-Ergebnisse
- Backend: **1786 passed, 9 skipped** (vorher 1782 — +4 netto, da 18 neue Tests, 14 bereits vorher existierende Stubs verbleiben)
- Korrekt: neue csv-Test-Datei bringt 18, gesamt von 1768 auf 1786.
- Frontend: **8/8 passed** (1 existing + 7 neu)
- ruff: alle Checks passed
- mypy: 136 source files, no issues

## Akzeptanz-Verifikation

```
RFC-4180 Smoke: OK
CSV-Quoting Test: '"Dev, Senior"' in output: TRUE
Backend 18/18: PASSED
Backend gesamt 1786/1786: PASSED
Frontend useReportExports 8/8: PASSED
Frontend build: ✓ built in 2.13s
```

## Offene Punkte / TODOs

- jszip-ZIP-Bundle: separater Sub-Slice. Voraussetzung: `npm install jszip` + TypeScript-Types.
- P3.1 (ReportV3-Persistenz): Falls personas/segments aus anderer Quelle kommen sollen,
  kann `_build_csv_export()` in `report.py` ohne API-Änderung umgestellt werden.
- i18n-Keys für CSV-Export-Buttons (falls Step4Report.vue Buttons hinzugefügt werden):
  separater Frontend-Worker-Task.
