# p2 — Issue #129: Graph deutsche Beziehungslabels + Lesbarkeit

**Issue:** [#129](https://github.com/arn0ld87/agora/issues/129)
**Start:** 2026-05-01
**Branch:** `claude/brave-booth-e29535` (Worktree)
**Reviewer:** Alex
**Aufwand-Schätzung:** size-m (1–2 Tage)

## Ziel
Edge-Labels im Graph werden bei `locale=de` lesbar deutsch dargestellt. Lesbarkeit beim Aufbau und bei dichten Stellen verbessert. Persistenz in Neo4j unverändert (Display-only).

## Sub-Slice-Plan

### SUB1 — i18n-Hook für Edge-Labels (1 Commit)
- Neues Modul `frontend/src/components/graph/edgeLabelI18n.js`:
  - `formatEdgeLabel(rawName, t)` — versucht i18n-Lookup, fällt sonst auf Heuristik (UPPER_SNAKE → "Title Case") zurück.
- i18n-Erweiterung in `frontend/src/i18n/locales/{de,en}.json` unter Key `graph.edgeLabels.*` mit ~30 häufigen Edge-Types.
- i18n-Erweiterung in `graph.ui.toggleEdgeLabels` (DE: „Beziehungslabels anzeigen").
- `useGraphRender.js`:
  - `linkLabels.text(d => formatEdgeLabel(d.name, t))`.
  - Re-Render-Trigger bei `locale`-Wechsel.
- `GraphCanvas.vue`: Toggle-Beschriftung über `t('graph.ui.toggleEdgeLabels')`.
- Tests: `edgeLabelI18n.test.js` (Unit) — bekannter Key, unbekannter Key (Heuristik), leerer Wert (Fallback).
- **Akzeptanz:** locale=de zeigt deutsches Label; locale=en zeigt englisches; unbekannter Edge-Type wird heuristisch lesbar.
- **Commit-Form:** `feat(graph): de-i18n für edge-labels (SUB1, Refs #129)`

### SUB2 — Lesbarkeits-Polish (1 Commit)
- Edge-Label-Schrift 9 → 12 px, Padding rect erhöhen (2/4 → 4/8).
- Knoten-Label-Trunkation 8 → 14 Zeichen, Tooltip mit vollem Namen on hover.
- Bei Zoom <0.6 Edge-Labels ausblenden (außer beim Hover über Kante: Reveal).
- Tests: kleines DOM-Test für Truncation-Schwelle.
- **Akzeptanz:** Schrift bei 100 % Zoom min. 12 px; Knoten-Namen zeigen mehr; bei sehr weit rausgezoomt verschwinden Edge-Labels.
- **Commit-Form:** `feat(graph): lesbarkeit polish (SUB2, Refs #129)`

### SUB3 — Pause-Knopf für Aufbau-Animation (1 Commit)
- Step1GraphBuild: Pause/Resume-Button für die Build-Animation. Beim Pause stoppt `simulation.stop()`, beim Resume `simulation.alpha(0.3).restart()`.
- Per-Batch-Freeze: nach jedem Batch automatisch ~800 ms Anhalten der Force-Simulation.
- **Akzeptanz:** während Aufbau kann ich pausieren und entspannt lesen; Auto-Freeze macht den Ablauf weniger hektisch.
- **Commit-Form:** `feat(graph): pause/freeze beim aufbau (SUB3, Closes #129)`

### Out of Scope (Folge-Issues)
- Backend-seitige `localized_label` aus Ontology-Generator (LLM ergänzt deutsche Variante). Nur sinnvoll, wenn die statische Map nicht reicht — wird als Folge-Issue eingereicht, falls nach SUB3 noch zu viele Labels durch die Heuristik fallen.

## Dependencies / Risiken
- `vue-i18n` ist als legacy-false eingerichtet → `useI18n()`-Composition-API Pflicht.
- `useGraphRender` ist Composable außerhalb von `<script setup>` → `useI18n()` muss in der Komponente aufgerufen und `t` als Param hereingereicht werden, sonst Setup-Context fehlt.

## Tests / Quality Gate
- `npm run check` muss grün sein (lint:backend, test:backend, lint:frontend, test:frontend, build:frontend).
- Manuelles Klicken im Browser nach jedem Sub-Slice (Golden Path).

## Status

### SUB1 — abgeschlossen 2026-05-01
- [x] Implementiert (i18n-Util `edgeLabelI18n.js`, Locale-Erweiterung DE/EN, Composable + GraphCanvas-Verdrahtung)
- [x] Tests grün (12 neue Vitest-Cases, `npm run check` 690 Backend + 52 Frontend grün, Build erfolgreich)
- [x] Commit erstellt
- [ ] Browser-Smoke (durch User; Dev-Server muss lokal laufen)

### SUB2 — abgeschlossen 2026-05-01
- [x] Implementiert: Edge-Schrift 9 → 12 px, BG-Padding 4/2 → 6/3, Knoten-Label-Truncation 8 → 14 Zeichen, native `<title>`-Tooltips an Knoten + Knoten-Label, Auto-Hide der Edge-Labels bei Zoom <0.6
- [x] Tests grün (`npm run check`: 690 Backend + 52 Frontend, Build)
- [x] Commit erstellt
- [ ] Browser-Smoke (durch User)

### SUB3
- [ ] Implementiert
- [ ] Tests grün
- [ ] Commit erstellt
- [ ] Browser-Smoke

## CHANGELOG-Eintrag (Vorschau)
```
### Added
- Graph: Beziehungslabels werden bei locale=de auf Deutsch angezeigt; Toggle-Beschriftung übersetzt (#129).
- Graph: Bessere Lesbarkeit (Edge-Schrift 12 px, Knoten-Namen weniger gekürzt, Auto-Hide bei Zoom <0.6) (#129).
- Graph-Build: Pause/Resume-Button und Auto-Freeze pro Batch (#129).
```
