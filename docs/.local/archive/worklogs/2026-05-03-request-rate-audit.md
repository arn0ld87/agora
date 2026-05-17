# Backend-Request-Rate-Audit

**Datum:** 2026-05-03
**Auftraggeber:** Sub-Slice J, Issue #218
**Methode:** Read-only Code-Inspektion (frontend/src + backend/app/api)
**Branch:** chore/task-J-request-rate-audit

---

## Zusammenfassung

Die Inspektion identifiziert 12 aktive Polling-Loops und 3 SSE-Channels.
Zwei Befunde sind als "Verdächtig" eingestuft, einer als "Kritisch".
Die wahrscheinliche Hauptursache der User-Beobachtung ("mehrere Calls pro Sekunde") ist eine kombinierte Überlappung dreier parallel laufender Loops auf der `SimulationRunView`-Route: die View selbst pollt `/run-status` alle 3 s, die eingebettete `Step3Simulation`-Komponente pollt `/run-status-detail` alle 2,5 s und hält gleichzeitig eine SSE-Verbindung. In `Step2EnvSetup` kommen während der Prepare-Phase bis zu vier Loops gleichzeitig hinzu — darunter ein impliziter `/persona/quality`-Call, der bei jedem 3-s-Tick ausgelöst wird, ohne im Inventar als eigenständiger Endpoint sichtbar zu sein. Keiner der Loops reagiert auf Page-Visibility-Änderungen; alle laufen im Hintergrund weiter, wenn der Tab nicht aktiv ist. Kein SSE-Endpoint setzt ein `retry:`-Feld, sodass der Browser beim Trennen sofort (Standard ~3 s) reconnectet, ohne dass das Backend ein Back-off steuern könnte.

---

## Polling-Inventar

| Component | Endpoint | Frequenz | Trigger | Stop | Bewertung | Empfehlung |
|---|---|---|---|---|---|---|
| `MainView.vue` (`taskPolling`) | `GET /api/tasks/{id}/status` | 2000 ms | Graph-Build gestartet (`startBuildGraph`) | `task.status === 'completed'\|'failed'` per `stopPolling()` | OK — endet beim Terminal-Status | Stop explizit auf Route-Wechsel sicherstellen |
| `MainView.vue` (`graphPolling`) | `GET /api/graph/{id}` (via project-Fetch) | 10 000 ms | Graph-Build gestartet | `stopGraphPolling()` bei completed/failed | OK — großzügiges Intervall | Kein dringender Bedarf |
| `SimulationRunView.vue` (`statusPolling`) | `GET /api/simulation/{id}/run-status` | 3000 ms | `onMounted` sofort | `usePolling` onUnmount — kein expliziter Stop bei Terminal-Status | **Verdächtig** — pollt auch nach `completed`/`error`, da `currentStatus.value` nur per `pollGlobalStatus()` aktualisiert wird, aber nie `statusPolling.stop()` ruft (`SimulationRunView.vue:56,59-71`) | Stop-Bedingung im `pollGlobalStatus`-Body ergänzen (M) |
| `SimulationRunView.vue` (`graphRefreshPolling`) | `GET /api/graph/{id}` | 30 000 ms | `watch(isSimulating)` start wenn `processing` | `watch(isSimulating)` stop wenn nicht mehr `processing` | OK | — |
| `Step2EnvSetup.vue` (`prepareStatusPolling`) | `GET /api/simulation/{id}/prepare/status` | 2000 ms | `startPrepare()` | `stopPolling()` bei completed/failed + `onUnmounted` | OK — terminiert korrekt | — |
| `Step2EnvSetup.vue` (`profilesPolling`) | `GET /api/simulation/{id}/profiles/realtime` | 3000 ms | `startProfilesPolling()` aus `startPrepare` | `stopProfilesPolling()` bei completed/failed + `onUnmounted` | **Verdächtig** — jeder Tick ruft intern `personaReview.refreshQuality(simulationId)` auf (`Step2EnvSetup.vue:643`), was eine weitere HTTP-Anfrage darstellt; de facto 1 sichtbarer + 1 versteckter Call alle 3 s | `refreshQuality`-Aufruf aus dem 3-s-Tick herauslösen; stattdessen einmalig bei `fetchProfilesRealtime` wenn `profiles.length` erstmals > 0 (M) |
| `Step2EnvSetup.vue` (`configPolling`) | `GET /api/simulation/{id}/config/realtime` | 3000 ms | `startConfigPolling()` bei Stage `generating_config` | `stopConfigPolling()` bei completed/failed + `onUnmounted` | OK | — |
| `Step3Simulation.vue` (`detailPolling`) | `GET /api/simulation/{id}/run-status-detail` | 2500 ms | `startPolling()` bei Sim-Start | `stopPolling()` bei completed/failed/stopped + `onUnmounted` | OK — terminiert korrekt | — |
| `Step3Simulation.vue` (`consolePolling` via `useIncrementalLogPolling`) | `GET /api/simulation/{id}/console-log?since_line=N` | 2000 ms | `startPolling()` | `consolePolling.stop()` in `stopPolling()` | OK | — |
| `Step4Report.vue` (`statusPolling`) | `GET /api/report/status` | 2500 ms | `onMounted` wenn nicht `isComplete` | `stopPolling()` bei completed/failed + `onUnmounted` | OK — terminiert korrekt | — |
| `Step4Report.vue` (`agentLogPolling` via `useIncrementalLogPolling`) | `GET /api/report/{id}/agent-log?since_line=N` | **1500 ms** | `startPolling()` | `agentLogPolling.stop()` | **Verdächtig** — schnellster Poll im System; bei gleichzeitigem `statusPolling` (2500 ms) + `consoleLogPolling` (2000 ms) ergibt sich steady-state ~1,5 Requests/s (`Step4Report.vue:207`) | Intervall auf 2500 ms angleichen (S) |
| `Step4Report.vue` (`consoleLogPolling` via `useIncrementalLogPolling`) | `GET /api/report/{id}/console-log?since_line=N` | 2000 ms | `startPolling()` | `consoleLogPolling.stop()` | OK | — |

### Kumulierte Last pro Route (Worst-Case, aktive Sim)

| Route | Gleichzeitige Loops | Effektive Calls/s |
|---|---|---|
| `SimulationRunView` (Step3 mounted) | View-`statusPolling` (3s) + `detailPolling` (2.5s) + `consolePolling` (2s) + SSE | ~1,4 HTTP + 1 SSE = **verdächtig** |
| `Step2EnvSetup` Prepare-Phase | `prepareStatus` (2s) + `profiles` (3s) + `config` (3s) + implicit `refreshQuality` (3s) | ~1,8 HTTP = **kritisch**, da 4 Endpoints gleichzeitig |
| `Step4Report` Generating | `statusPolling` (2.5s) + `agentLog` (1.5s) + `consoleLogs` (2s) | ~1,5 HTTP |

---

## SSE-Channels

| Stream | Heartbeat | Backend `retry:` Feld | Sauberes Close? | Auth | Bewertung |
|---|---|---|---|---|---|
| `/api/simulation/{id}/stream` | 15 s (`simulation_stream.py:48`) | Nicht gesetzt — kein `retry:` in `_sse_format()` (`simulation_stream.py:52-57`) | Ja: `useEventStream.stop()` bei `onUnmounted` + Terminal-Status (`useEventStream.ts:82-92`); nach 5 Errors auto-stop (`useEventStream.ts:72`) | Signed Ticket via `POST /api/auth/ticket` + URL-Param `?ticket=` (`stream.ts:53`) | OK — Heartbeat vorhanden; aber fehlendes `retry:`-Feld gibt Browser-Default (~3 s) — kein Back-off steuerbar |
| `/api/logs/stream` | 15 s (`: heartbeat\n\n`, `logs.py:199`) | Nicht gesetzt (`logs.py:220-227`) | Ja: `LogDrawer.vue:stopStream()` per `watch(props.open)` + `onUnmounted` (`LogDrawer.vue:125-142`) | URL-Param `?token=` (`logs.ts:34`) — kein signed Ticket, direkt Bearer | **Verdächtig** — `onerror` ist leer (`LogDrawer.vue:114`), Browser reconnectet mit Standard-Backoff (~3 s) ohne Cap; kein `retry:`-Feld; Tab-idle betrifft auch LogDrawer |
| `/api/logs/stream` (implizit Level-Wechsel) | — | — | Alter Stream wird via `startStream()` neu aufgebaut bei Level-Wechsel (`LogDrawer.vue:134-138`) | wie oben | **Verdächtig** — `stopStream()` ruft `_eventSource.close()`, direkt gefolgt von `new EventSource(...)`; bei schnellem Level-Wechsel können kurzzeitig Doppel-Connections entstehen |

---

## Top-Empfehlungen (mind. 5)

1. **[Kritisch] `Step2EnvSetup` — `refreshQuality` aus dem 3-s-Tick herauslösen** (Aufwand: M)
   `Step2EnvSetup.vue:643` ruft `personaReview.refreshQuality(props.simulationId)` bei jedem `fetchProfilesRealtime`-Tick auf, der selbst alle 3 s läuft. Das verdoppelt die Requests des Profile-Loops unsichtbar. Stattdessen `refreshQuality` einmalig aufrufen, sobald `profiles.value.length` zum ersten Mal > 0 wechselt (via `watch`). Betrifft: `frontend/src/components/Step2EnvSetup.vue:635-647`.

2. **[Verdächtig] `SimulationRunView` — doppelten Status-Poll stoppen** (Aufwand: M)
   `SimulationRunView.vue:56` hält `statusPolling` (3 s auf `/run-status`) aktiv, während die gemountete `Step3Simulation`-Komponente gleichzeitig SSE auf demselben `simulationId` hat. Der Parent-Poll ist redundant, sobald SSE aktiv ist. Option A: `statusPolling` im `SimulationRunView` entfernen und stattdessen das `@update-status`-Event der Kind-Komponente nutzen. Option B: Parent-Poll erst starten, wenn SSE-Fehler gemeldet wird. Betrifft: `frontend/src/views/SimulationRunView.vue:56`.

3. **[Verdächtig] `SimulationRunView.statusPolling` — fehlende Stop-Bedingung bei Terminal-Status** (Aufwand: S)
   `pollGlobalStatus()` (`SimulationRunView.vue:59-71`) setzt `currentStatus.value` auf `'completed'`, ruft aber nie `statusPolling.stop()` auf. Der Poll läuft bis zum Route-Unmount weiter. Einen `statusPolling.stop()`-Aufruf innerhalb von `pollGlobalStatus` bei `rs === 'completed' || rs === 'failed'` ergänzen, analog zu `Step3Simulation.vue:293-301`. Betrifft: `frontend/src/views/SimulationRunView.vue:59-71`.

4. **[Verdächtig] `Step4Report.agentLogPolling` — Intervall auf 2500 ms angleichen** (Aufwand: S)
   Das 1500-ms-Intervall (`Step4Report.vue:207`) ist das schnellste im System und ergibt mit den zwei parallelen Log-Polls zusammen ~1,5 Calls/s während der Report-Generierung. Da Agent-Log-Einträge nicht zeitkritisch sind und nur bei Statuswechsel eine Reaktion erfordern, reicht 2500 ms. Der Gewinn: steady-state 1,5 Calls/s → ~1,1 Calls/s. Betrifft: `frontend/src/components/Step4Report.vue:207`.

5. **[Alle Loops] Page-Visibility-Gating einführen** (Aufwand: M)
   Kein einziger Polling-Loop pausiert, wenn der Browser-Tab nicht aktiv ist. Eine zentrale `usePageVisible()`-Util mit `visibilitychange`-Listener, die in `usePolling.ts` als optionales `pauseWhenHidden: true`-Flag integriert wird, würde alle sechs Loops gleichzeitig entlasten. Schätzung: 40-60 % Request-Reduktion bei typischer Multi-Tab-Nutzung. Betrifft: `frontend/src/composables/usePolling.ts` (zentrale Änderung) + alle Aufrufstellen.

6. **[SSE] `retry:`-Feld in SSE-Endpunkten setzen** (Aufwand: S)
   Weder `simulation_stream.py:52-57` noch `logs.py:220-227` setzen ein `retry:`-Feld. Browser-Default ist ~3 s, was bei Backend-Problemen zu konstantem Reconnect-Sturm führen kann. `retry: 30000\n` würde reconnect-Bursts bei kurzem Backend-Neustart entschärfen. Betrifft: `backend/app/api/simulation_stream.py:52-57` und `backend/app/api/logs.py:220-227`.

7. **[LogDrawer SSE] Reconnect-Cap implementieren** (Aufwand: S)
   `LogDrawer.vue:114` setzt `onerror = () => { /* reconnect handled by browser */ }` ohne jede Begrenzung. Analog zu `useEventStream.ts:71-72` (MAX_RECONNECT_ATTEMPTS = 5) sollte auch der LogDrawer nach N Fehlern den Stream schließen und dem Nutzer einen Reload-Button zeigen, statt unbegrenzt zu hammern. Betrifft: `frontend/src/components/LogDrawer.vue:113-115`.

---

## Folge-Sub-Slices

- **J.1** — `SimulationRunView`-Doppelpoll entfernen + Stop-bei-Terminal-Status ergänzen (`SimulationRunView.vue:56,59-71`) — Aufwand M, direkter Fix des kritischsten Overlaps.
- **J.2** — `Step2EnvSetup`: `refreshQuality`-Call aus dem 3-s-Tick herauslösen, einmalige `watch`-basierte Auslösung bei erstem Profile-Eintrag — Aufwand M.
- **J.3** — `usePolling` um `pauseWhenHidden: true`-Flag erweitern + in allen Aufrufstellen aktivieren — Aufwand M, strukturelle Verbesserung für alle künftigen Loops.
