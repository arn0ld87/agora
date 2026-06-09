# Arbeitsprotokoll Sub-Slice J.4 — usePolling visibilitychange-Gating (Issue #222)

**Datum:** 2026-05-03
**Branch:** `feat/task-J4-visibility-gating`
**Layer:** 6 (Frontend-TypeScript — Composable-Erweiterung)

## Befund (Audit J)

`rg "visibilitychange|document.hidden" frontend/src/` war leer — kein einziger
der Polling-Loops reagierte auf Hintergrund-Tabs. Bei typischer Multi-Tab-Nutzung
laufen alle Loops weiter, obwohl der Nutzer den Tab verlassen hat. Schätzung:
40–60 % unnötige Requests bei Multi-Tab-Betrieb.

## Scope-Klarstellung

Der Audit sprach von "12 Polling-Loops". `rg "usePolling\b" frontend/src/components/`
ergab 5 Aufrufer. Die Differenz liegt wahrscheinlich darin, dass der Audit auch
raw-`setInterval`, `useEventStream` und `useIncrementalLogPolling` mitzählte. Diese
sind Out of Scope für diesen Slice — das Visibility-Gating in `usePolling.ts`
deckt alle 5 `usePolling`-basierten Loops ab.

## Aufrufer-Analyse

Alle 5 Aufrufer sind user-facing Status-Polls:

| Datei | Aufruf | pauseWhenHidden |
|---|---|---|
| `Step2EnvSetup.vue:515` | `usePolling(pollPrepareStatus, 2000)` | `true` (Default) |
| `Step2EnvSetup.vue:516` | `usePolling(fetchProfilesRealtime, 3000)` | `true` (Default) |
| `Step2EnvSetup.vue:517` | `usePolling(fetchConfigRealtime, 3000)` | `true` (Default) |
| `Step3Simulation.vue:186` | `usePolling(pollDetail, 2500)` | `true` (Default) |
| `Step4Report.vue:187` | `usePolling(pollStatus, 2500)` | `true` (Default) |

**Kein einziger Aufrufer braucht `pauseWhenHidden: false`.** Begründung: Der
Backend-Server-Prozess läuft unabhängig vom Browser-Tab weiter. Wenn der Nutzer
zu einem Tab zurückwechselt, liefert der Catch-up-Tick sofort frische Daten.
Das ist das korrekte UX-Verhalten für alle diese Loops.

## Architekturentscheidungen

### Pause = clearInterval, nicht tick()-Gate

Der Interval wird bei `document.hidden` via `clearInterval()` tatsächlich
gestoppt — nicht nur in `tick()` gebailout. Das ist wichtig, damit keine Timer-Fires
akkumulieren, während der Tab versteckt ist.

### Listener-Lifecycle = an start()/stop() gebunden

Der `visibilitychange`-Listener wird in `start()` registriert und in `stop()`
entfernt. `onUnmounted(stop)` (bereits vorhanden) sorgt für automatisches Cleanup.

### start() während document.hidden

Wenn `pauseWhenHidden=true` und der Tab beim Aufruf von `start()` bereits
versteckt ist: Listener wird registriert, `isRunning=true` gesetzt, aber kein
Interval gestartet und kein sofortiger Tick. Der Catch-up erfolgt beim nächsten
`visibilitychange` (Tab wird wieder sichtbar). Dieses Verhalten ist intentional
und im JSDoc dokumentiert.

### isRunning bleibt true während Hintergrund-Pause

`isRunning` bleibt `true` während der Hintergrund-Pause (der Nutzer hat logisch
eine laufende Polling-Session). Kein separates `isPaused`-Ref — minimale
API-Oberfläche.

## Implementierte Änderungen

### `frontend/src/composables/usePolling.ts`

- Neues `pauseWhenHidden?: boolean` in `UsePollingOptions` (Default: `true`)
- Hilfsfunktionen `_startInterval()` und `_stopInterval()` extrahiert aus `start()`
- `_handleVisibilityChange()`: bei `document.hidden` → `_stopInterval()`; sonst
  → sofortiger `void tick()` (Catch-up) + `_startInterval()`
- `start()`: registriert Listener wenn `pauseWhenHidden=true`, respektiert
  `document.hidden` beim Start
- `stop()`: entfernt Listener, setzt `visibilityListener = null`
- Start-Guard erweitert: `if (timerId || isRunning.value) return` (vorher nur
  `if (timerId)` — war ein latenter Bug bei stop/restart-Zyklen ohne saubere
  Deallokation)
- JSDoc auf `pauseWhenHidden`-Option

### Keine Änderungen an den 5 Aufrufer-Dateien

Alle Aufrufer nutzen Default `pauseWhenHidden: true`. Keine Opt-outs notwendig.

## Tests

3 neue Tests in `frontend/src/composables/__tests__/usePolling.spec.ts`
(describe: `usePolling — pauseWhenHidden`):

1. **pausiert Tick wenn document.hidden=true bei pauseWhenHidden=true (Default)**
2. **resumed sofort mit Catch-up-Tick bei visibilitychange → sichtbar**
3. **pauseWhenHidden=false → läuft auch im Hintergrund weiter**

Vorher RED (Tests 1+2), Test 3 trivial-green (da kein Gating existierte).
Nach Implementierung alle 10 Tests grün (7 vorhandene + 3 neue).

## Verifikation

```
npm test -- --run usePolling   →  10/10 grün
npm run check                  →  149/149 grün, TypeScript clean, Build success
```

## Backwards-Compat-Hinweis

Das Default-Verhalten von `usePolling` ändert sich: Alle Loops pausieren jetzt
automatisch, wenn der Browser-Tab in den Hintergrund geht. Für Loops, die im
Hintergrund laufen müssen, ist `{ pauseWhenHidden: false }` als Opt-out möglich.
Im Kontext dieses Projekts braucht kein bestehender Aufrufer den Opt-out.

## Refs

- Issue #222 (Audit-J-Befund: Polling ohne Visibility-Gating)
- Branch: `feat/task-J4-visibility-gating`
