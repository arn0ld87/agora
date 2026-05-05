# Sub-Slice 34 — Arbeitsprotokoll: `useSimulationPrepare`-Composable

Datum: 2026-05-05
Branch: `feat/layer-4-task-47a-use-simulation-prepare`
Refs: #203

## Ziel

`Step2EnvSetup.vue` (1780 LOC zum Zeitpunkt des Schnitts, ein voriger Commit hatte bereits `QuotaPlanEditor.vue` extrahiert und 1817 → 1780 LOC erreicht) weiter reduzieren durch Extraktion des Simulation-Prepare-Lifecycles in ein eigenes Composable.

## Gewählter Cut

### Was in `useSimulationPrepare.ts` lebt

Alles, was direkt die drei API-Endpunkte

- `POST /api/simulation/prepare`
- `POST /api/simulation/prepare/status`
- `GET  /api/simulation/<id>/profiles/realtime`
- `GET  /api/simulation/<id>/config/realtime`

orchestriert:

- Reaktiver State: `phase`, `isPreparing`, `prepareProgress`, `progressMessage`, `profiles`, `expectedTotal`, `simulationConfig`, `error`
- Drei `usePolling`-Instanzen (Status, Profiles, Config) inkl. Lifecycle-Teardown via `onUnmounted`
- `startPrepare(opts)`: nimmt fertigen `PrepareSimulationData`-Payload entgegen, koordiniert Polling-Start und State-Transitionen
- `probeAlreadyPrepared(simId, opts)`: hydratiert State beim Mount ohne erneuten Prepare-Trigger
- `reset()`: setzt State zurück (für Sim-Wechsel)

### Was in `Step2EnvSetup.vue` bleibt

- Quota-Plan-Validierung (Zod `PersonaQuotaPlanSchema.safeParse`) — diese kombiniert lokalen `quotaEntries`-State mit i18n-Fehlertexten und baut den API-Payload; sie ist nicht vom Prepare-Lifecycle trennbar ohne unnötige Prop-Durchreichung
- Wrapper-Funktion `triggerPrepare()` — liest Model, Language, AgentCap, Quota aus lokalen Refs, baut den Payload und delegiert an `startPrepare()`
- Alle Persona-Bearbeitungs-Helpers (approve/reject/regenerate/edit), Persona-Bibliothek, manuelle Persona, Suchfilter
- UI-State für Modalpanel, Editorfenster, Review-Actions

### Abweichung vom ursprünglichen Plan

Die Task-Spec sprach von der Möglichkeit, den Cut zu verschieben, falls Prepare-State eng mit Quota-State gekoppelt ist. Das ist tatsächlich der Fall: `startPrepare` in der Spec-Beschreibung validiert den QuotaPlan inline. Die Lösung: Die Validierungslogik bleibt im `.vue`, aber der eigentliche Netzwerk-/Polling-Code wandert ins Composable. Das ist der natürlichste Schnitt — Composable ist rein datengetrieben, `.vue` hält UI-spezifische Logik.

## LOC-Delta

| Datei | vorher | nachher | Delta |
|---|---|---|---|
| `Step2EnvSetup.vue` | 1780 | 1666 | −114 |
| `useSimulationPrepare.ts` | — | 307 | +307 (neu) |
| `useSimulationPrepare.spec.ts` | — | 300 | +300 (neu) |

Netto-Reduktion in `Step2EnvSetup.vue`: −114 LOC. Liegt innerhalb des Zielkorridors (−100 bis −200 LOC). Der Hauptblock der entfernten Zeilen: ~170 Zeilen Prepare-Logik, Polling-Management, Realtime-Fetch-Helpers minus ~55 Zeilen für die neue `triggerPrepare()`-Wrapper-Funktion.

## Test-Ergebnisse

- `useSimulationPrepare.spec.ts`: 9 Cases, alle grün
- `Step2EnvSetup`-Regression: 3 Cases, alle grün (bestehende Spec)
- Frontend `npm run check` (vue-tsc + vitest + build): 266 Tests, 0 Fehler, Build erfolgreich
- Backend pytest: 1541 passed, 9 skipped
- Schema-Drift: clean

## Verhaltensäquivalenz

- Network-Calls identisch: gleiche Endpoints, gleiche Payloads, gleicher Retry-Mechanismus (`requestWithRetry` kommt aus `api/simulation.ts`, bleibt unberührt)
- Polling-Verhalten identisch: `pauseWhenHidden: false` für alle drei Loops, da der Prepare-Task auf dem Server weiterläuft auch wenn der Tab in den Hintergrund geht
- `onUnmounted`-Teardown ist jetzt im Composable selbst verankert (über das eigene `onUnmounted`-Call in `useSimulationPrepare.ts`)
- Pinia-Store: kein Pinia-State involviert; der Composable-State ist komponentenlokal (kein globaler Store-Sync nötig)

## Risiken / Offene Punkte

Keine. Die `Step2EnvSetup.vue` ist mit 1666 LOC noch weit vom 800-LOC-Ziel aus Issue #203 entfernt. Weitere Cuts (Personas-Panel, Bibliothek-Section, Modal-Logik) sind als nachfolgende Sub-Slices geplant.
