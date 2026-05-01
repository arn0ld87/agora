# Slice 4a — `usePolling` ist bereits erledigt (Closes #37)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #37 (EPIC-05-ST-01) — generisches `usePolling` einführen

## Befund

`frontend/src/composables/usePolling.js` existiert seit **v0.4.1** (siehe `CHANGELOG.md` v0.4.1: *„`frontend/src/composables/usePolling.js` als gemeinsamer Polling-Baustein für Langläufer"*). Schnittstelle deckt die Akzeptanz vollständig:

```js
const { isRunning, isTicking, start, stop, tick } = usePolling(task, intervalMs, options)
```

| Akzeptanzkriterium | Erfüllung |
|---|---|
| Start/Stop/Cleanup zentral geregelt | ✓ `start()`, `stop()`, `onUnmounted(stop)` ist verdrahtet |
| Komponenten definieren nur callback + interval | ✓ `task` plus `intervalMs` plus optional `{ immediate, onError }` |

## Bestehende Konsumenten (8 Stellen)

- `Step2EnvSetup.vue` — Prepare-Status (2 s), Profiles-Realtime (3 s), Config-Realtime (3 s)
- `Step3Simulation.vue` — Detail (2,5 s), Console (2 s)
- `Step4Report.vue` — Report-Status (2,5 s), Agent-Log (1,5 s), Console-Log (2 s)

## Nicht-migriert (4 Stellen — Scope der Folge-Issues)

| Datei | Zeile | Aufruf | Folge-Issue |
|---|---:|---|---|
| `MainView.vue` | 200 | `setInterval(fetchGraphData, 10000)` | #38 (Graph-Polling) |
| `MainView.vue` | 219 | `setInterval(() => pollTaskStatus(taskId), 2000)` | #38 (Task-Polling) |
| `SimulationRunView.vue` | 177 | `setInterval(refreshGraph, 30000)` | #38 (Graph-Polling) |
| `SimulationRunView.vue` | 190 | `setInterval(pollGlobalStatus, 3000)` | #38 (Status-Polling) |

Diese Stellen werden mit Issue #38 (`useTaskPolling`) und Issue #39 (`useIncrementalLogPolling`) überführt — eigene Stories, eigene Akzeptanzkriterien.

## Konsequenz für v0.8.0

Issue #37 wird mit dieser Status-Doku geschlossen. Verbleibender v0.8.0-Backlog: **5 echte Issues** (#36, #38, #39, #40, #84).

## Folge-Slice

Issue #38 — `useTaskPolling` über `usePolling` als Adapter für die 4 raw-`setInterval`-Stellen.
