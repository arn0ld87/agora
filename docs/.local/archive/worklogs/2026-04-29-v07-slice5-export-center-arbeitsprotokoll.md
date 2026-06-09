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

## Sub-Slice 5.3 — GraphML-Export

### Ziel

Wissensgraphen lassen sich als GraphML rausziehen, damit sie in Gephi, NetworkX, Cytoscape & Co. weiterverarbeitet werden können — ohne Roh-JSON parsen zu müssen.

### Vorgehen

1. `backend/app/api/graph.py`
   - Neuer Endpoint `GET /api/graph/<graph_id>/export?format=graphml`.
   - Reuse vorhandener `Neo4jStorage.get_graph_data()` → kein zusätzlicher DB-Pfad.
   - Mapping über `_build_networkx_graph()` (MultiDiGraph): Knoten- und Kanten-Attribute werden via `_stringify()` auf GraphML-kompatible Skalare bzw. JSON-Strings reduziert (Listen/Dicts würden sonst werfen).
   - `nx.write_graphml(g, buf, named_key_ids=True)` schreibt in BytesIO und wird als Attachment ausgeliefert. Filename: `agora-graph-<graph_id>.graphml`.
   - Leerer Graph (keine Nodes UND keine Edges) → `404`.
   - Forward-kompatibel: anderes `format` → `400`.
2. `frontend/src/api/graph.js`
   - Neuer Helper `exportGraphMl(graphId)` mit `responseType: 'blob'`.
3. `frontend/src/components/GraphPanel.vue`
   - `.graphml`-Button neben dem Refresh-Knopf, nur sichtbar wenn `graphData.graph_id` gesetzt ist.
   - `downloadGraphml()` lädt Blob und triggert Browser-Download.
4. `backend/tests/test_graph_export.py` (neu)
   - 5 Tests: ungültige `graph_id`, ungültiges `format`, leerer Graph (404), GraphML-Attachment mit Knoten/Kanten-Asserts via XML-Parsing, Default-Format.

### Bewusst nicht geändert

- Snapshot-Variante (`/snapshot/<gid>/<round>/export`) bleibt offen — der TemporalGraphService liefert nur Edges, eine konsistente Knotenmenge müsste dafür extra synthetisiert werden. Folgeticket, kein Blocker.
- Knoten-/Kanten-Attribute werden flach als String oder JSON-String exportiert. GraphML stützt formal `bool/int/double/string`; Listen/Dicts werden bewusst als JSON serialisiert, damit kein Datenverlust entsteht.
- Kein neuer Frontend-Knopf für JSON-Graph-Export — der bestehende `/api/graph/data/<gid>` reicht; GraphML füllt nur die Lücke für Graphtools.

### Verifikation

```bash
cd backend && uv run pytest tests/test_graph_export.py
npm run check
```

`npm run check` grün: 286 Backend-Tests (281 vorher + 5 neue), Frontend-Lint, Vite-Build.

## Sub-Slice 5.4 — PNG/SVG-Export der Graph-Visualisierung

### Ziel

Die aktuell gerenderte d3-Graph-Ansicht lässt sich als SVG (vektoriell) und PNG (raster) speichern, damit Reports und Präsentationen einen visuellen Anker bekommen.

### Vorgehen

1. `frontend/src/components/GraphPanel.vue`
   - Zwei neue Header-Buttons `.svg` und `.png`, sichtbar sobald `graphData` geladen ist.
   - `_buildStandaloneSvg()`: klont das live `<svg>`, setzt `xmlns`/`xmlns:xlink`, hängt einen `<style>`-Block ein, der per `getComputedStyle(document.documentElement)` alle CSS-Custom-Properties einsammelt und am Klon-Root als `:root { --… }` injiziert. Damit lösen die `var(--rule-strong)`-Referenzen aus den d3-`.attr()`-Calls auch ohne unsere scoped Vue-Stylesheets auf.
   - `downloadSvg()`: serialisiert via `XMLSerializer`, prependet `<?xml version="1.0"?>`, triggert Blob-Download.
   - `downloadPng()`: lädt das Standalone-SVG als `Blob`-URL in ein `Image`, zeichnet es auf ein DPR-skaliertes `<canvas>` (2× bei HiDPI) und exportiert über `canvas.toBlob('image/png')`.
   - Filename-Konvention: `agora-graph-<graph_id>.{svg,png}`.

### Bewusst nicht geändert

- Kein Backend-Pfad — die SVG-Geometrie lebt nur clientseitig (D3 mit Force-Layout). Sie serverseitig zu reproduzieren würde headless-browser oder eine eigene Layout-Engine erfordern; nicht im Scope.
- Keine externe Library (kein `dom-to-image`, kein `html2canvas`) — `XMLSerializer` + `<canvas>` reichen für den Force-Graph völlig.
- Keine "exportiere alle Round-Snapshots als PNG-Sequenz"-Funktion. Kann später als Folge-Ticket dazu, wenn jemand Bedarf hat.

## Sub-Slice 5.5 — PDF-Export

### Ziel

Reports und Graphen lassen sich als PDF speichern, ohne eine schwere Render-Pipeline (WeasyPrint, jsPDF) ins Repo zu holen.

### Vorgehen

Bewusst minimalistisch — `window.print()` mit "In PDF speichern" als Browser-Default ist die Standard-Lösung und reicht für DACH-Schul-/IHK-Workflows:

1. **Report-PDF** existiert bereits in `frontend/src/components/Step4Report.vue` als Button "Drucken / PDF" (`printReport()`). Der baut ein Standalone-HTML-Dokument mit Print-CSS und triggert `window.print()`. Kein Neubau nötig.
2. **Graph-PDF** in `frontend/src/components/GraphPanel.vue` (neu): `.pdf`-Button öffnet ein neues Fenster gegen eine HTML-`Blob`-URL, in der das Standalone-SVG aus 5.4 inline eingebettet ist und Print-CSS für saubere Skalierung sorgt. Auf `load` wird `window.print()` aufgerufen; der Nutzer wählt im Druckdialog "Als PDF speichern".

### Bewusst nicht gewählt

- **Kein jsPDF / pdf-lib im Frontend.** Das blust den Bundle um ~500 KB auf für eine Funktion, die der Browser nativ kann.
- **Kein WeasyPrint / reportlab im Backend.** Heavy Dependency, plus zusätzlicher Asset-Pfad für Font-/Bild-Embedding. Nicht local-first-freundlich.
- **Keine Print-CSS-Engine im Backend.** Die Report-Daten liegen ohnehin schon als JSON+MD vor; wer Server-PDF braucht, kann pandoc o.ä. extern auf das `agora-report-<id>.md` ansetzen.

### Verifikation

```bash
npm run check
```

`npm run check` grün: 286 Backend-Tests, Frontend-Lint, Vite-Build (Bundle ~159 KB gzipped, +1 KB ggü. 5.3).

## Stand Slice 5

| Sub-Slice | Inhalt | Status |
| --- | --- | --- |
| 5.1 | Report JSON+MD via `/api/report/<id>/export` | ✓ |
| 5.2 | Polarisations-CSV via `/api/simulation/<id>/metrics/export` | ✓ |
| 5.3 | GraphML via `/api/graph/<gid>/export` | ✓ |
| 5.4 | Graph als SVG/PNG (Frontend) | ✓ |
| 5.5 | PDF via `window.print()` (Report + Graph, Frontend) | ✓ |

Damit ist der Plan-Punkt **Slice 5: Export Center** abgeschlossen. Folge-Tickets als Backlog:

- Snapshot-GraphML (`/api/graph/snapshot/<gid>/<round>/export`) — TemporalGraphService liefert nur Edges; konsistente Knotenmenge müsste extra synthetisiert werden.
- Frontend-View für Polarisations-Metriken; sobald die existiert, fällt der Knopf zum CSV-Export trivial dazu.
- PNG-Sequenz-Export pro Round, falls Animationen gewünscht werden.
