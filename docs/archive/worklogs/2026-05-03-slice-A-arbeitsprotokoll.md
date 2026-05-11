# Sub-Slice A — Step3 → Step4-Übergang absichern

**Datum:** 2026-05-03
**Branch:** fix/task-A-step3-zu-step4-uebergang
**Issue:** #209
**Subagent:** agora-frontend-worker (Sonnet)

## Root-Cause (verifiziert)

**H2 disproven.** `rg -n "function pollStatus"` findet die Funktion bei Zeile 312 — sie ist korrekt definiert und ruft `getRunStatus` auf. Die Briefing-Hypothese war falsch.

**H3 bestätigt.** `pollDetail` (Zeilen 322–347 vor Fix) las ausschließlich `res.data.all_actions` — kein Pfad, der `runner_status` aus der Detail-Response prüft. Das bedeutet: SSE ist der einzige Kanal, der `phase=2` setzen kann. Wenn der letzte SSE-Frame beim Stream-Close verloren geht (Browser schließt EventSource bevor der `completed`-Frame ankommt), bleibt `phase` auf 1, und der goReport-Button erscheint nie. HTTP-Detail-Polling liefert `runner_status: completed` via `run_state.to_dict()` (Backend-Zeile 432), aber die Frontend-Komponente ignorierte diesen Wert.

Beweis: Backend `GET /<sim_id>/run-status/detail` serialisiert `result = run_state.to_dict()` vor dem Anhängen der Actions-Listen — `runner_status` ist immer in der Response vorhanden.

## Edits

### `frontend/src/components/Step3Simulation.vue`

- **Zeilen 289–303 (vor Fix):** Neuer Helper `promoteToCompletedPhase(status, data)` extrahiert (Zeilen 289–303 nach Fix). Idempotent-Guard `if (phase.value === 2) return` verhindert doppelte Log-Einträge und Events.
- **`applyRunStateEvent` (SSE-Pfad):** Ruft jetzt `promoteToCompletedPhase(status, data)` auf statt inline phase/log/emit/stop — DRY.
- **`pollDetail` (HTTP-Polling-Pfad):** Prüft `res.data?.runner_status` nach jedem Tick. Bei `completed`/`failed`/`stopped` wird `runStatus.value` aktualisiert und `promoteToCompletedPhase` aufgerufen. Damit ist der Button auch bei verlorenem SSE-Frame sichtbar.

### `frontend/src/components/__tests__/Step3Simulation.spec.ts`

- **`useEventStream`-Mock erweitert:** Return-Objekt hat nun `isStreaming`, `error`, `lastEventAt`, `start`, `stop` (statt dem rudimentären `connected`/`close`). `_capturedStateCallback` wird beim Mock-Setup befüllt, damit Tests den SSE-state-Handler synchron auslösen können.
- **3 neue Tests** in `describe('Step3Simulation — phase promotion (Sub-Slice A, #209)')`:
  1. HTTP-Polling-Tick meldet `completed` → goReport-Button erscheint (fakeTirers, 2500 ms advance).
  2. SSE-`completed`-Event via `_capturedStateCallback` → goReport-Button erscheint.
  3. Nach phase=2 via SSE: `doStart()` mit fehlschlagendem `startSimulation` ruft `resetState()` → phase=0, Start-Button sichtbar.

## Tests

```
npm test -- --run Step3Simulation

 Test Files  1 passed (1)
      Tests  5 passed (5)
   Duration  2.81s
```

Alle 5 Tests grün (2 Smoketest-Tests, 3 Phase-Promotion-Tests).

## Verify

```
npm run check

 Tests  146 passed (146)
 Build  ✓ built in 5.10s
```

Lint (vue-tsc), alle 146 Tests, Build — alles grün. Keine TS-Errors, keine neuen Warnungen.
