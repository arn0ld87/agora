# Slice 4c — `useIncrementalLogPolling` einführen (Closes #39)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #39 (EPIC-05-ST-03) — useIncrementalLogPolling einführen
**Branch:** `claude/elegant-engelbart-ab0ebd`

## Vorgehen

Drei Konsumenten teilten exakt dasselbe Append-/Cursor-/Scroll-Muster:

- `Step3Simulation.vue` — Simulation Console Log (`getSimulationConsoleLog`, 2 s)
- `Step4Report.vue` — Agent Log mit JSON-Parse (`getAgentLog`, 1,5 s)
- `Step4Report.vue` — Console Log raw (`getConsoleLog`, 2 s)

Das neue Composable `frontend/src/composables/useIncrementalLogPolling.js` hält Cursor (`since_line`) und Lines-Array intern, wickelt den Fetcher in ein `usePolling`-Tick, parsed bei Bedarf und scrollt den Container nach jedem Append automatisch ans untere Ende. Der Konsument hängt nur den `containerRef` an sein Log-Element und liest `lines` für die Anzeige.

## Composable-Vertrag

```js
const { lines, containerRef, polling, reset, tick } = useIncrementalLogPolling({
  fetcher,            // (sinceLine) => API-Envelope { lines, next_line, total_lines }
  intervalMs,         // optional, default 2000
  parseLine,          // optional, (raw) => entry|null — null filtert Zeile raus
})
```

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/composables/useIncrementalLogPolling.js` (NEU) | +96 Zeilen |
| `frontend/src/components/Step3Simulation.vue` | −18 / +14 (Konsole-Polling auf Composable) |
| `frontend/src/components/Step4Report.vue` | −36 / +27 (Agent + Console auf Composable) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Akzeptanz-Mapping zu Issue #39

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| Log-Zeilenstand wird sauber verwaltet | Cursor `sinceLine` lebt nur im Composable; `next_line ?? total_lines`-Fallback an einer Stelle. Konsumenten haben keine Möglichkeit, den Cursor zu desynchronisieren. |
| Keine duplizierte Scroll-/Append-Logik | `for (const ...) lines.value.push(...)` plus `nextTick`/`scrollTop = scrollHeight` lebt nur in `useIncrementalLogPolling.tick()`. Drei vorher identische Blöcke (Step3 Console, Step4 Agent, Step4 Console) sind weg. |

## Bewusst nicht geändert

- **`parseAgentEntry` bleibt in `Step4Report.vue`.** Das ist domänenspezifisch (Action-Type → Title/Subtitle/Body), gehört nicht in ein generisches Log-Composable. Wird via `parseLine`-Hook eingehängt.
- **Polling-Intervalle bleiben** (Step3 Console 2 s, Step4 Agent 1,5 s, Step4 Console 2 s). Verhalten unverändert.
- **API-Wrapper-Verträge unverändert.** `getSimulationConsoleLog`/`getAgentLog`/`getConsoleLog` werden weiterhin mit `(id, sinceLine)` gerufen.

## Verifikation

`npm run check` 5/5 grün — Backend 488 + Frontend 11 + Build 736 Module.

## Folge-Slice

Verbleibende Issues v0.8.0: **#36** (Graph-DTO-Normalisierung) und **#84** (Composable-Tests).
