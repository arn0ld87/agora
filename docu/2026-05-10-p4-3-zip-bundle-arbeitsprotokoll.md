# Sub-Slice P4.3 — ZIP-Bundle-Export

**Datum:** 2026-05-10
**Refs:** PLAN.md §5.3, Issue-Kontext: P4.2-Followup (jszip-Marker)

## Was wurde gemacht

Neuer Export-Modus `format=zip` für `GET /api/report/<id>/export`.
Das ZIP wird on-the-fly aus Python-stdlib (`zipfile.ZipFile` + `io.BytesIO`) gebaut —
kein neues npm/pip-Dep.

### Inhalt des ZIP

Alle 6 Artefakte im Top-Level-Ordner `agora-report-<id>/`:

| Datei | Quelle |
|---|---|
| `report-v3.md` | Datei via `_get_report_v3_markdown_path()`, Fallback `report.markdown_content` |
| `report-v3.json` | Datei via `_get_report_v3_path()` |
| `evidence-map.json` | `ReportManager.get_evidence_map()` als JSON-Bytes |
| `personas.csv` | `personas_to_csv()` aus `report-v3.json.personas[]` |
| `segments.csv` | `segments_to_csv()` aus `report-v3.json.segments[]` |
| `claims.csv` | `claims_to_csv()` aus `evidence-map.json.sections[].claims[]` |

### 404-Bedingung

Wenn weder `report-v3.md` noch `report-v3.json` auf dem Dateisystem existieren
(Report noch nicht finalisiert), gibt der Endpoint `404 report_not_finalised` zurück.
Leere CSVs und eine leere `evidence-map.json` sind erlaubt.

## Geänderte Dateien

| Datei | Art | Beschreibung |
|---|---|---|
| `backend/app/api/report.py` | erweitert | `_REPORT_MODES` Validierung um `'zip'`, ZIP-Branch + `_build_zip_bundle()`-Helper (~55 LOC) |
| `backend/tests/api/test_report_export_zip.py` | neu | 5 Tests (6-Einträge-Check, Header-Check, 404-ohne-v3, 400-xml, 404-unbekannter-Report) |
| `frontend/src/api/report.ts` | erweitert | `fetchReportBundle()` — analog `fetchReportCsv`, `responseType: 'blob'` |
| `frontend/src/composables/useReportExports.ts` | erweitert | `downloadAllBundle()` + TODO(jszip)-Marker ersetzt durch Hinweis auf serverseitiges ZIP |
| `frontend/src/composables/__tests__/useReportExports.spec.ts` | erweitert | 3 neue Tests für `downloadAllBundle` |
| `CHANGELOG.md` | erweitert | `[Unreleased]` Eintrag P4.3 |

## Tests

```
backend: 5/5 ZIP-Tests grün, 1807 passed total
frontend: 11/11 useReportExports Tests grün (3 neue)
```

## TODO(jszip)-Marker

Zeile 175 in `useReportExports.ts` hatte `TODO(jszip): Bundle als ZIP sobald jszip installiert ist`.
Ersetzt durch JSDoc-Kommentar: `Kein jszip-Install nötig — ZIP wird auf dem Server via Python-stdlib gebaut.`
Der Marker gilt als erledigt.

## Refactor-Entscheidung

`_build_csv_export` wurde nicht strukturell verändert — die CSV-Logik in `_build_zip_bundle`
liest direkt aus `report_v3` und `evidence_map` statt `_build_csv_export` aufzurufen,
da letztere per `table`-String arbeitet (Loop) und der ZIP-Pfad alle drei Tabellen parallel
benötigt. Kein Code-Duplikat: Die eigentliche CSV-Generierung liegt in den pure-Funktionen
`personas_to_csv`, `segments_to_csv`, `claims_to_csv` aus `csv_export.py` — beide Pfade
nutzen dieselben Funktionen.
