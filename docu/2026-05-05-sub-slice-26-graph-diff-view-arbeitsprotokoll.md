# Sub-Slice 26 — Graph-Diff-View für Branch-Vergleich (Closes #76)

**Datum:** 2026-05-05
**Branch:** feat/layer-7-task-26-graph-diff-view
**Issue:** Closes #76 (EPIC-15-ST-03 — Confidence-Heatmap-Anteil bereits in Sub-Slice 16a/b geliefert)
**Backend-Voraussetzung:** Sub-Slice 22 (#74, commit 1484344) — `GET /api/graph/<id>/diff`

## Was wurde gebaut

- `frontend/src/contracts/graphDiffContract.ts` — Zod-Spiegel zu `backend/app/contracts/graph_diff.py` (10 Schemas: EdgeData, NodePropertyShift, ClusterShift, BridgeAgentShift, ClusterSummary, GraphSnapshot, EdgeReinforcement, EdgeWeakening, GraphDiffMetrics, GraphDiff)
- `frontend/src/composables/useGraphDiff.ts` — Fetch-Wrapper mit strict `GraphDiffSchema.parse()` als Layer-0-Boundary; Envelope-Unwrap toleriert beide API-Shapes (`data.diff` und direkt `diff`)
- `frontend/src/components/graph/GraphDiffPanel.vue` — Side-by-side-Visualisierung mit Diff-Layer (added/removed/reinforced/weakened) als CSS-Klassen-Mapping über existierender `<GraphCanvas>` (kein neuer D3-Renderer)
- i18n-Keys unter `graphDiff.*` in de.json + en.json (16 Keys)
- Tests: 3 neue Spec-Files (Contract-Roundtrip, Composable-Pfade, Component-States)

## Designentscheidungen

- Diff-Annotations als `:class`-Binding über existierender GraphCanvas, kein neuer D3-Renderer
- Strict-Zod-Parse via `.parse()` (nicht `.safeParse()`) — Boundary wirft bei Contract-Drift
- Cluster-Listen aus Snapshot-Vergleich abgeleitet (kein separater Endpoint nötig)
- Empty-State bei `snapshotA === snapshotB` mit i18n-Hinweis
- Loading-/Error-States explizit als getrennte Templates
- TS-Fix (vue-tsc): `GraphCanvas` ist Options-API ohne TypeScript; sein `graphData`-Prop wird von vue-tsc als `Record<string, any> | undefined` inferiert. Da die Computed-Properties `snapshotAGraphData` / `snapshotBGraphData` bei leerem Diff `null` zurückgeben, entstand ein TS2322. Fix via **Option B** (`?? undefined` am Bind-Ort in Zeilen 96/106) — minimalinvasiv, kein Template-Umbau, da der umgebende Block bereits `v-else-if="diff"` als Guard hat.

## Out of Scope

- Compare-UI für BranchComparison-Metriken (#67 / Sub-Slice 27)
- Persona-Diff (#69 Layer 8)
- Multi-Way-Diff (>2 Snapshots)
- Animated Transitions zwischen Snapshots

## Akzeptanz (Ist-Zustand)

- ESLint: clean
- Vitest: 202 passed (27 Test-Files, 3 neue Spec-Files: graphDiffContract / useGraphDiff / GraphDiffPanel)
- vue-tsc --noEmit: clean (nach Fix Option B in GraphDiffPanel.vue Zeilen 96/106)
- Vite-Build: erfolgreich
- Voice-Lint: keine "future prediction"/"god's eye view"-Strings

## Backend-Pendant

- `backend/app/contracts/graph_diff.py` (Sub-Slice 21)
- `backend/app/api/graph.py::diff_endpoint` (Sub-Slice 22, commit 1484344)
- `schemas/graph-diff.schema.json`
