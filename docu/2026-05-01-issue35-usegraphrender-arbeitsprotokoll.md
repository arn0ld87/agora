# Slice 3 — D3-Logik in `useGraphRender`-Composable extrahieren (Closes #35)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #35 (EPIC-04-ST-02) — D3-Logik in Composable extrahieren
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Direkt im Anschluss an Issue #34 (drei Sub-Slices, Refs #34 / Closes #34): die `renderGraph`-Funktion samt D3-Lifecycle-State (`currentSimulation`, `linkLabelsRef`, `linkLabelBgRef`), den drei Watchern (`graphData` deep, `showEdgeLabels`, plus Erst-Render im Mount) und dem `window.resize`-Listener wandern aus `GraphCanvas.vue` in das neue Composable `frontend/src/composables/useGraphRender.js`.

`selectedItem` lebt jetzt im Composable und wird per Return-Ref an die Komponente zurückgereicht. Der Aufrufer kann den Ref auch von außen leeren (`closeDetailPanel()` setzt `selectedItem.value = null`).

## Composable-Vertrag

```js
const { selectedItem, render } = useGraphRender({
  svgRef,           // Ref<SVGSVGElement>
  containerRef,     // Ref<HTMLElement>
  graphData,        // MaybeRefOrGetter<object|null>
  entityTypes,      // MaybeRefOrGetter<Array>
  showEdgeLabels,   // Ref<boolean>
})
```

| Schnittstelle | Mechanismus |
|---|---|
| **Resize** | Composable hängt `window.resize` → `nextTick(render)`; cleanup in `onUnmounted` |
| **Re-Render** | Watch auf `graphData` (deep) und `showEdgeLabels`; Erst-Render im `onMounted` |
| **Selection** | `selectedItem` ist Output-Ref; D3-Click-Handler schreiben hinein, Konsument darf ihn auch von außen auf `null` setzen |

`render` wird zusätzlich als manueller Trigger zurückgegeben — derzeit ungenutzt, hält aber die Tür für Composable-Tests und expliziten Re-Render bei externen Events offen.

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/composables/useGraphRender.js` (NEU) | +317 Zeilen |
| `frontend/src/components/graph/GraphCanvas.vue` | −266 Zeilen (641 → 375) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Bewusst nicht geändert

- **D3-Verhalten unverändert.** Drag-Threshold (3 px), Force-Parameter (`charge: -400`, `collide: 50`, `gravity x/y: 0.04`), Zoom-ScaleExtent (0.1–4), Tick-Updates, Edge-Labels-Visibility — alles 1:1.
- **Export-Funktionen bleiben in `GraphCanvas.vue`.** Sie sind eng an den `graphSvg`-DOM-Ref gebunden und sind kein Render-Belang.
- **`expandedSelfLoops`, `closeDetailPanel`, `toggleSelfLoop` bleiben in der Komponente.** Das ist Detail-Panel-State, nicht Render-State.
- **Keine Tests neu** — Composable-Tests sind Issue #84 (eigene Story).

## Akzeptanz-Mapping zu Issue #35

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| `useD3Graph.js` oder ähnliches existiert | `frontend/src/composables/useGraphRender.js` |
| Resize, Re-Render und Selection laufen über klar definierte Schnittstellen | Composable ownt `window.resize`-Lifecycle, watcht `graphData`+`showEdgeLabels`, returnt `selectedItem` als Ref. Komponente lädt nur `svgRef`, `containerRef`, `showEdgeLabels` und reagiert auf `selectedItem` |

## Verifikation

`npm run check` 5/5 grün — Backend 488 passed, 2 skipped; Frontend lint 0; Vitest 11 passed; Build 735 Module.

## Folge-Slice

EPIC-05 (Polling-Composables): #37 generisches `usePolling` einführen → #38 `useTaskPolling` → #39 `useIncrementalLogPolling`. Drei p0-Issues, hängen logisch aneinander.
