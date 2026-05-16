# Sub-Slice 2.1 — GraphHints.vue extrahieren

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #34 (EPIC-04-ST-01) — GraphPanel zerlegen, **Teil 1 von 3**
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Erste Etappe der GraphPanel-Zerlegung. Hint-Overlays (Building/Simulating + Finished) in eigene Komponente überführt, weil sie der mit Abstand kleinste und stabilste Block sind und sich risikolos isolieren lassen.

State-Verteilung nach diesem Sub-Slice:

- `showSimulationFinishedHint`, `wasSimulating` und der `watch` auf `props.isSimulating` bleiben in `GraphPanel.vue` — Hint-Sichtbarkeit ist State, der durch Lifecycle-Übergänge entsteht. Hints-Komponente bleibt rein präsentational.
- `currentPhase`, `isSimulating`, `showFinishedHint` werden als Props in die neue Komponente gereicht.
- `dismissFinishedHint` wird als Event `dismiss-finished` zurückgegeben.

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/components/graph/GraphHints.vue` (NEU) | +132 Zeilen |
| `frontend/src/components/GraphPanel.vue` | −102 Zeilen (933 → 831) |
| `.gitignore` | +1 Negativ-Pattern für dieses Protokoll |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Bewusst nicht geändert

- **Styles 1:1 übernommen** — `.graph-building-hint`, `.finished-hint`, `.memory-icon-wrapper`, `.memory-icon`, `.hint-icon-wrapper`, `.hint-icon`, `.hint-text`, `.hint-close-btn` plus `@keyframes breathe` wurden identisch aus dem GraphPanel-Style-Block in `GraphHints.vue` (`<style scoped>`) verschoben. Visual-Diff ausgeschlossen.
- **Texte unverändert.** Das englische Hint-Wording (`"GraphRAG short-term/long-term memory updating in real-time"` etc.) bleibt für diesen Refactor stehen — Internationalisierung ist Issue für separaten Slice.
- **Edge-Labels-Toggle, Toolbar, D3-Renderlogik bleiben** im `GraphPanel.vue`. Wandern in Sub-Slices 2.2 (`GraphToolbar.vue`) und 2.3 (`GraphCanvas.vue`).

## Verifikation

`npm run check` 5/5 grün:

| Stage | Ergebnis |
|---|---|
| `lint:backend` | erwartet 0 Findings (siehe PR-Run) |
| `test:backend` | 488 passed, 2 skipped |
| `lint:frontend` | 0 Findings |
| `test:frontend` | 11 passed |
| `build:frontend` | 728 modules transformed, build ok |

Visuelle Stichprobe der zwei Hint-States ist Issue der QA — Stilklassen identisch, kein Render-Pfad verschoben.

## Folge-Slice

Sub-Slice 2.2: `GraphToolbar.vue` extrahieren (Header-Buttons + 4 Export-Funktionen + Edge-Labels-Toggle).
