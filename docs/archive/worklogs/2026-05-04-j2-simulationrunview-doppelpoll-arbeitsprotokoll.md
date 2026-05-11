# Arbeitsprotokoll: Slice J.2 / Issue #220 — SimulationRunView Doppelpoll-Bereinigung

## Slice

J.2 / Issue #220

## Problem

`SimulationRunView.vue` betrieb einen eigenen `statusPolling`-Loop (alle 3 s) auf `/api/simulation/{id}/run-status`, während die eingebettete `Step3Simulation`-Komponente bereits eine SSE-Verbindung sowie einen `detailPolling`-Loop (alle 2,5 s) auf `/api/simulation/{id}/run-status/detail` auf dieselbe `simulationId` hielt. Laut `docs/2026-05-03-request-rate-audit.md` (Empfehlungen 2 und 3) resultierte das in ~1,4 redundanten HTTP-Calls/s; zudem lief `statusPolling` auch nach Terminal-Status (`completed`/`failed`) weiter, weil ein explizites `stop()` fehlte.

## Lösung

Variante B (sauberer Umbau statt Dedup-Patch): Der `statusPolling`-Loop in `SimulationRunView` wurde vollständig entfernt. Stattdessen emittiert `Step3Simulation` ein neues `update-progress`-Event mit den Feldern `{ paused, current_round, total_rounds }` nach jedem Status-Update aus SSE (`applyRunStateEvent`, `applyControlEvent`) und HTTP-Detail-Poll (`pollDetail`). Die View abonniert dieses Event und befüllt `isPaused`, `currentRound` und `totalRounds` daraus. Ein lokaler Snapshot-Vergleich (`_lastProgressSnapshot`) verhindert unnötige Emits bei unveraenderten Werten.

Der Ansatz ist additiv (kein bestehendes Event verändert), rückwärtskompatibel und eliminiert die doppelte Polling-Schicht vollständig. Ein manueller `stop()` bei Terminal-Status war mit dem Loop-Entfernen obsolet — das Problem ist von Grund auf gelöst.

## Files geändert

- `frontend/src/components/Step3Simulation.vue` — `defineEmits` erweitert um `update-progress`; `maybeEmitProgress()`-Helper hinzugefügt; Aufrufe nach `applyRunStateEvent`, `applyControlEvent`, `pollDetail`-Merge und `doPauseResume`; `total_rounds` in `pollDetail`-Merge übernommen.
- `frontend/src/views/SimulationRunView.vue` — `getRunStatus`-Import entfernt; `statusPolling`-Variable, `pollGlobalStatus`-Funktion und `statusPolling.start({ immediate: true })`-Aufruf entfernt; `updateProgress(p)`-Handler hinzugefügt; `@update-progress`-Binding im Template ergänzt.
- `frontend/src/views/__tests__/SimulationRunView.spec.js` — neu erstellt.
- `docs/2026-05-04-j2-simulationrunview-doppelpoll-arbeitsprotokoll.md` — diese Datei.
- `CHANGELOG.md` — `[Unreleased] ### Fixed`-Eintrag ergänzt.

## Tests

Neue Vitest-Spec: `frontend/src/views/__tests__/SimulationRunView.spec.js`

- **Test 1:** Nach Mount werden keine `/run-status`-Requests gefeuert — `getRunStatus` bleibt `not.toHaveBeenCalled()`.
- **Test 2:** Ein `update-progress`-Event mit `{ paused: true, current_round: 5, total_rounds: 10 }` setzt `isPaused`, `currentRound`, `totalRounds` korrekt und spiegelt sich in `statusText` (Pause-Variante mit 5/10).

Ergebnis: 2 neue Tests grün; Gesamtsuite 156/156 grün; Build erfolgreich.

## Audit-Effekt

Empfehlung 2 (doppelten `run-status`-Poll entfernen) und Empfehlung 3 (Stop bei Terminal-Status) aus `docs/2026-05-03-request-rate-audit.md` sind vollständig adressiert. Laut Audit-Schätzung sinkt die Request-Rate von ~1,4 auf ~0,9 calls/s (verbleibend: `detailPolling` + `consolePolling` in Step3, SSE zählt nicht). Der fehlende Terminal-Stop ist durch Entfernen des Loops von Grund auf beseitigt.

## Risiken / Caveats

Die Event-Surface von `Step3Simulation` ist um `update-progress` erweitert — additiv, kein Breaking Change. Bestehende Elternkomponenten ohne `@update-progress`-Handler sind nicht betroffen (Vue ignoriert nicht-abonnierte Emits). Das `_lastProgressSnapshot`-Objekt lebt als Modul-Variable im `<script setup>`-Closure und wird bei Komponenten-Destroy automatisch freigegeben.
