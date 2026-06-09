# Sub-Slice 2.2 — GraphToolbar.vue extrahieren

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #34 (EPIC-04-ST-01) — GraphPanel zerlegen, **Teil 2 von 3**
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Header-Toolbar (Refresh, GraphML/SVG/PNG/PDF-Export, Maximize) in eigene Komponente überführt. Toolbar bleibt rein präsentational: keine Export-Logik, nur Buttons + Events.

Architektur-Entscheidung: **Export-Funktionen bleiben weiterhin in `GraphPanel.vue`**. Sie greifen auf `graphSvg`-DOM-Ref zu, der erst in Sub-Slice 2.3 zusammen mit der Renderlogik in `GraphCanvas.vue` wandert. DOM-Refs durch Props zu reichen wäre häßlich; lieber pinge Funktionen über Toolbar-Events an den Composer und verschiebe sie sauber im nächsten Sub-Slice.

Edge-Labels-Toggle wandert nicht mit in die Toolbar — er ist semantisch eine **View-Option des Canvas** und sitzt visuell unten. Er kommt in Sub-Slice 2.3 mit dem Canvas mit (oder bleibt im Composer und wird per Prop an Canvas gereicht).

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/components/graph/GraphToolbar.vue` (NEU) | +138 Zeilen |
| `frontend/src/components/GraphPanel.vue` | −95 Zeilen (831 → 736) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Schnitt

| Verantwortung | Wo |
|---|---|
| Button-Layout, `:disabled`/`v-if`-Logik | GraphToolbar.vue (Props: `loading`, `hasGraphId`, `hasGraphData`) |
| Export-Funktionen (`downloadGraphml`, `_buildStandaloneSvg`, `downloadSvg`, `downloadPng`, `printGraphPdf`) | GraphPanel.vue — DOM-Ref `graphSvg` lebt dort |
| Outer-Emits (`refresh`, `toggle-maximize`) | per `$emit` aus Toolbar nach oben durchgereicht |

## Bewusst nicht geändert

- **Styles 1:1 übernommen** — `.panel-header`, `.panel-title`, `.header-tools`, `.tool-btn`, `.tool-btn:hover`, `.tool-btn .btn-text`, `.icon-refresh.spinning` plus `@keyframes spin` in `GraphToolbar.vue`. `@keyframes spin` bleibt zusätzlich in `GraphPanel.vue` für `.loading-spinner` (Vue scoped-styles isolieren keyframes — Duplikat ist nötig und ohne Side-Effect).
- **Export-Funktionen bleiben unverändert.** Kein Verhalten-Diff, nur Aufruf jetzt via Event-Handler.
- **i18n-Strings unverändert** (`$t('graph.panel')`, `$t('common.refresh')`).

## Verifikation

`npm run check` 5/5 grün — Backend 488 passed, 2 skipped; Frontend lint 0; Vitest 11 passed; Build 730+ Module.

## Folge-Slice

Sub-Slice 2.3: `GraphCanvas.vue` extrahieren — D3-`renderGraph`, SVG-Container-Ref, Edge-Labels-Toggle, Selection-State. Nimmt die Export-Funktionen mit (oder schiebt sie in ein `useGraphExport.js`-Composable). Schließt Issue #34.
