# Sub-Slice 2.3 — GraphCanvas.vue extrahieren (Closes #34)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #34 (EPIC-04-ST-01) — GraphPanel zerlegen, **Teil 3 von 3 — abschließend**
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Letzte Etappe der GraphPanel-Zerlegung. Die D3-Renderlogik samt SVG-Container, Selektions-State, Loading/Empty-States, Edge-Labels-Toggle, Hint- und Detail-Panel-Einbindung sowie alle vier Export-Funktionen wandern in eine eigene Komponente `GraphCanvas.vue`. `GraphPanel.vue` bleibt als reine Kompositionsdatei zurück (98 Zeilen).

Toolbar-Click-Events werden über die Komposition an Canvas-Methoden gepingt: `GraphCanvas` exposed `downloadGraphml`, `downloadSvg`, `downloadPng`, `printPdf` via `defineExpose`; `GraphPanel` hält einen `canvasRef` und ruft die Methode beim entsprechenden Toolbar-Event auf.

## Zielarchitektur (final)

```
GraphPanel.vue            (98 Zeilen, Komposition pur)
├── GraphToolbar          (Header-Buttons, emittiert Events)
├── GraphCanvas           (SVG, D3, Selektion, Hints, Detail, Export)
│   ├── GraphHints
│   └── GraphDetailPanel
├── GraphLegend
└── GraphRoundSlider
```

State-Verteilung:

| State | Wo | Begründung |
|---|---|---|
| `selectedRound`, `showSimulationFinishedHint`, `wasSimulating` | GraphPanel | Domain-State über Lifecycle-Übergänge |
| `displayedGraphData`, `entityTypes`, `maxRound` | GraphPanel (computed) | Round-Filter wird auf Composer-Ebene angewandt, Canvas rendert nur was es bekommt |
| `selectedItem`, `expandedSelfLoops`, `showEdgeLabels` | GraphCanvas | reine Canvas-Selektions- und View-State |
| `currentSimulation`, `linkLabelsRef`, `linkLabelBgRef` | GraphCanvas | D3-Lifecycle-Refs |

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/components/graph/GraphCanvas.vue` (NEU) | +641 Zeilen |
| `frontend/src/components/GraphPanel.vue` | −638 Zeilen (736 → 98) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

Σ-Zeilen über alle vier Komponenten: 933 → 1.009 (+76 für Boilerplate aus 3 neuen `<script setup>`/`<style scoped>`-Blöcken). Tradeoff für saubere Komponentengrenzen.

## Bewusst nicht geändert

- **D3-Renderlogik bleibt in der Komponente, nicht in einem Composable.** Issue #35 (EPIC-04-ST-02) hebt sie in einer eigenen Story in ein `useGraphRender.js`-Composable.
- **Verhalten unverändert.** Klick-Selektion, Drag-Threshold, Zoom-ScaleExtent, Tick-Updates, Edge-Labels-Visibility — alles 1:1 übernommen.
- **Styles 1:1 übernommen.** `.graph-container`, `.graph-view`, `.graph-svg`, `.graph-state`, `.empty-icon`, `.edge-labels-toggle`, `.toggle-switch`, `.slider`, `.toggle-label`, `.loading-spinner` plus `@keyframes spin` aus `GraphPanel.vue` in `GraphCanvas.vue` verschoben. `.graph-panel`-Outer-Style bleibt im Composer.

## Akzeptanz-Mapping zu Issue #34

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| `GraphPanel.vue` wird primär Kompositionsdatei | 98 Zeilen, nur `<GraphToolbar>`, `<GraphCanvas>`, `<GraphLegend>`, `<GraphRoundSlider>` plus Composition-State |
| D3-Rendering nicht direkt mit Detailpanel/Hint-Logik vermischt | D3 lebt isoliert in `GraphCanvas`; Hints und Detail-Panel sind als saubere Children eingebunden |
| Zielstruktur `GraphCanvas.vue` | ✅ neu |
| Zielstruktur `GraphLegend.vue` | ✅ existiert seit v0.6.0 |
| Zielstruktur `GraphDetailPanel.vue` | ✅ existiert seit v0.6.0 |
| Zielstruktur `GraphToolbar.vue` | ✅ Sub-Slice 2.2 |
| Zielstruktur `GraphHints.vue` | ✅ Sub-Slice 2.1 |

## Verifikation

`npm run check` 5/5 grün:

| Stage | Ergebnis |
|---|---|
| `lint:backend` | 0 |
| `test:backend` | 488 passed, 2 skipped |
| `lint:frontend` | 0 |
| `test:frontend` | 11 passed |
| `build:frontend` | 734 modules, 2,76 s |

## Folge-Slice

Issue #34 ist erfüllt. Nächster Sub-Slice geht in EPIC-04-ST-02 (Issue #35) — D3-Logik aus `GraphCanvas.vue` in ein `useGraphRender.js`-Composable extrahieren.
