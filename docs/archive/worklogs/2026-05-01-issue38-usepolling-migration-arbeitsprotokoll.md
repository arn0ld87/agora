# Slice 4b — `usePolling`-Migration für Build-/Status-/Graph-Polling (Closes #38)

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issue:** #38 (EPIC-05-ST-02) — `useTaskPolling` für Graph/Prepare-Tasks

## Vorgehen

Die vier verbleibenden raw-`setInterval`-Stellen aus der EPIC-05-Inventur (siehe `docs/2026-05-01-issue37-usepolling-status.md`) wandern auf das bestehende `usePolling`-Composable um. **Kein neues `useTaskPolling`-Wrapper-Composable** — das wäre ein leerer Adapter über `usePolling` ohne Eigennutzen. `usePolling` deckt die Issue-Akzeptanz vollständig: zentraler Mechanismus, sauberer Cleanup über `onUnmounted`.

## Migrierte Stellen

| Datei | Vorher | Nachher |
|---|---|---|
| `MainView.vue` Build-Status | `pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)` | `taskPolling = usePolling(async () => { if (currentTaskId.value) await pollTaskStatus(currentTaskId.value) }, 2000)` |
| `MainView.vue` Graph-Daten | `graphPollTimer = setInterval(fetchGraphData, 10000)` | `graphPolling = usePolling(fetchGraphData, 10000)` |
| `SimulationRunView.vue` Status | `statusTimer = setInterval(pollGlobalStatus, 3000)` | `statusPolling = usePolling(pollGlobalStatus, 3000)` |
| `SimulationRunView.vue` Graph-Refresh | `graphRefreshTimer = setInterval(refreshGraph, 30000)` | `graphRefreshPolling = usePolling(refreshGraph, 30000)` |

`MainView.startPollingTask(taskId)` schreibt `currentTaskId` in einen Ref und startet das Composable. `stopPolling()` setzt den Ref auf `null` und stoppt — falls ein noch laufender Tick weiterläuft, fängt der Guard `if (currentTaskId.value)` den Edge-Case ab.

## Cleanup-Vereinfachung

`onUnmounted`-Cleanups in beiden Views werden schlanker:

- `MainView.vue`: `onUnmounted(() => { stopPolling(); stopGraphPolling() })` entfernt — `usePolling` hängt seinen `onUnmounted(stop)` selbst beim Setup.
- `SimulationRunView.vue`: gleicher Effekt.

`stopGraphRefresh()`-Aufruf in `handleGoBack()` (war `clearInterval`-Wrapper) ist jetzt `graphRefreshPolling.stop()`.

`onUnmounted`-Imports raus, weil keiner der beiden Views ihn mehr nutzt.

## Geänderte Dateien

| Datei | Δ |
|---|---|
| `frontend/src/views/MainView.vue` | −10 / +9 (Cleanup-Logik vereinfacht) |
| `frontend/src/views/SimulationRunView.vue` | −15 / +8 (zwei Timer-Definitionen + Cleanup) |
| `.gitignore` | +1 Negativ-Pattern |
| `CHANGELOG.md` | `[Unreleased]`-Block ergänzt |

## Akzeptanz-Mapping zu Issue #38

| Akzeptanzkriterium | Erfüllt durch |
|---|---|
| Graph Build und Prepare nutzen denselben Polling-Mechanismus | Build (`MainView.taskPolling`) und Prepare (`Step2EnvSetup.prepareStatusPolling`) gehen beide über `usePolling`. Plus alle anderen Polling-Stellen in den Views/Steps. |
| Cleanup bei Unmount sauber | `usePolling` registriert `onUnmounted(stop)` selbst. View-eigene `onUnmounted`-Aufräumblöcke für Polling sind weg. |

## Bewusst nicht gemacht

- **Kein `useTaskPolling`-Wrapper.** Issue-Title schlug das Composable-Naming vor, aber die Akzeptanzkriterien fordern nur denselben Mechanismus + Cleanup. Ein Wrapper ohne Eigennutzen wäre Boilerplate.
- **`pollTaskStatus`-Auto-Stop bei `task.status === 'completed'` bleibt unverändert.** Die existierende Logik ruft `stopPolling()` aktiv auf — saubere Domain-Logik, soll nicht hinter ein generisches Composable wandern.
- **Step3/Step4-Logs** (Simulation Console, Report Agent/Console Logs) sind Scope von Issue #39 (`useIncrementalLogPolling`).

## Verifikation

`npm run check` 5/5 grün — Backend 488 + Frontend 11 + Build 735+ Module, eslint 0.

## Folge-Slice

Issue #39 — `useIncrementalLogPolling` für die drei Log-Konsumenten (`Step3Simulation.consolePolling`, `Step4Report.agentLogPolling`, `Step4Report.consoleLogPolling`).
