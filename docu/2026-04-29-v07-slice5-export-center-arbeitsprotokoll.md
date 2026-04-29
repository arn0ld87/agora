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

## Sub-Slice 5.2 — CSV-Export für Polarisations-Metriken

### Ziel

Polarisationsmetriken (`NetworkAnalyticsService`) lassen sich neben dem bestehenden JSON-Endpoint auch als flache CSV-Dateien ziehen — pro Aspekt (Summary, Cluster, Bridge-Agents) eine eigene CSV-Sicht.

### Vorgehen

1. `backend/app/api/simulation_metrics.py`
   - Neuer Endpoint `GET /api/simulation/<simulation_id>/metrics/export?format=csv&view=summary|clusters|bridges`.
   - `format` aktuell nur `csv` (Forward-Kompatibel angelegt — `400` bei anderem Wert).
   - `view=summary` (Default): wide CSV mit `simulation_id, window_size_rounds, total_agents, total_interactions, echo_chamber_index, cluster_count`.
   - `view=clusters`: eine Zeile pro Cluster (`cluster_id, size, agent_ids`); `agent_ids` als Semikolon-getrennte Liste, damit Excel/pandas die Zelle nicht splittet.
   - `view=bridges`: eine Zeile pro Brücken-Agent (`rank, agent_id`).
   - Fehlerpfade abgesichert: ungültige `simulation_id`, unbekanntes `format`/`view`, kaputtes `window_size_rounds` → 400.
   - `_compute()` und `_csv_response()` Helper, damit der bestehende JSON-Endpoint die Berechnung weiter über denselben Pfad fährt (kein Verhaltensdrift).
   - Filename-Konvention: `agora-metrics-<simulation_id>-<view>.csv`.
2. `backend/tests/test_simulation_metrics_export.py` (neu)
   - 7 Tests: ungültige IDs, ungültige `format`/`view`/`window`, Summary-Default, Clusters, Bridges. Service läuft live, `SimulationRunner.get_all_actions` ist gemockt.

### Bewusst nicht geändert

- Kein Frontend-Knopf für den Metrik-CSV-Export — die UI hat (Stand v0.7) noch keine Metrik-Ansicht; sobald die existiert, lässt sich der Button trivial nachziehen. Bis dahin bleibt der Endpoint API-only und ist über `curl` / Notebooks nutzbar.
- JSON-Endpoint bleibt unverändert; der CSV-Endpoint ist additiv.
- Keine Aggregation über mehrere Plattformen in einer CSV — `?platform=twitter|reddit` wird wie bisher pro Aufruf gefiltert.

### Verifikation

```bash
cd backend && uv run pytest tests/test_simulation_metrics_export.py
npm run check
```

`npm run check` grün: 281 Backend-Tests (274 vorher + 7 neue), Frontend-Lint, Vite-Build.
