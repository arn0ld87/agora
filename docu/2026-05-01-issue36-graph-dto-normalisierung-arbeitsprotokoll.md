# Slice 5 — Graph-DTO-Normalisierung im Frontend (Closes #36)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #36 (EPIC-04-ST-03) — Graph-DTO-Normalisierung im Frontend
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Befund vor dem Slice

`frontend/src/components/graph/graphPanelData.js` ist faktisch bereits ein Mapper:

- `buildGraphNodes` liefert `{ id, name, type, rawData }`-ViewModels.
- `buildCurvedEdge` und `buildSelfLoopEdge` liefern `{ source, target, type, name, curvature, isSelfLoop, pairIndex, pairTotal, rawData }`-ViewModels.
- `buildGraphRenderData` ist die Public-API.

Was **fehlte**, um die Akzeptanz buchstäblich zu erfüllen:

1. Eine **explizit benannte** Stelle für die Legacy-Alias-Auflösung (`fact_type` ↔ `name` aus der NER-Pipeline).
2. **Dokumentierte ViewModel-Typen**, damit Konsumenten (`GraphCanvas`, `GraphDetailPanel`, `useGraphRender`) den Vertrag stabil lesen können.

## Vorgehen

Minimal-invasiver Refactor:

1. **`normalizeEdgeAliases(edge)`** als eigene Funktion extrahiert. Einziger Ort, an dem die `fact_type`/`name`-Alias-Logik landet. Backend-Konvention im JSDoc dokumentiert (aktuelles Schema: `name`; Legacy NER-Pipeline: `fact_type`).
2. **`buildCurvedEdge`** nutzt jetzt `normalizeEdgeAliases(edge)` statt der inline Aliasse — der Aufruf ist die einzige Stelle im Modul, an der die Aliasse aufgelöst werden.
3. **JSDoc-Typdefinitionen** `GraphNodeViewModel` und `GraphEdgeViewModel` an den Modul-Header. `buildGraphRenderData` hat einen vollen `@returns`-Block mit den ViewModel-Typen.

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/components/graph/graphPanelData.js` | +51 / −5 (JSDoc-Types + named alias function + Public-API-Doc) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Akzeptanz-Mapping zu Issue #36

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| UI arbeitet mit stabilen Node-/Edge-ViewModels | `GraphNodeViewModel` und `GraphEdgeViewModel` als JSDoc-Types am Modul-Header. `buildGraphRenderData` hat dokumentierten `@returns`-Vertrag. |
| Legacy-Feldaliasse sind in einem Mapper gekapselt | `normalizeEdgeAliases(edge)` ist die einzige Stelle, an der `fact_type`/`name` aufgelöst werden. `buildCurvedEdge` ruft sie auf, sonst niemand. |

## Bewusst nicht gemacht

- **Kein TypeScript-Cutover.** JSDoc-Types reichen für die Akzeptanz und sind kompatibel mit dem laufenden TypeScript-PoC (siehe v0.6.0 — `frontend/tsconfig.json` mit `allowJs: true`).
- **Kein neuer Mapper-Test.** Tests für `buildGraphRenderData` und `normalizeEdgeAliases` sind Scope von Issue #84 (Composable-Tests / Vitest-Coverage).
- **Keine Verhaltensänderung.** Output von `buildGraphRenderData` ist bit-identisch zum Vorzustand für alle bekannten Eingaben.
- **Self-Loop-Edge bleibt mit hardcoded `type: 'SELF_LOOP'` und Label aus `selfLoopEdges.length`.** Das ist semantisch kein Alias, sondern eine UI-Aggregation.

## Verifikation

`npm run check` 5/5 grün — Backend 488 + Frontend 11 + Build 736 Module, eslint 0.

## Folge-Slice

Letztes verbleibendes v0.8.0-Issue: **#84** — Composable-Tests (Vitest) für `usePolling`, `useEventStream`, `useWorkspaceStatus` und potenziell auch `useGraphRender`/`useIncrementalLogPolling`/`normalizeEdgeAliases`.
