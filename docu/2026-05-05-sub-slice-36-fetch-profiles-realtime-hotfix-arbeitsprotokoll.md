# Sub-Slice 36 — Hotfix: fetchProfilesRealtime in useSimulationPrepare exposen (Closes #292)

**Datum:** 2026-05-05
**Branch:** `fix/issue-292-fetch-profiles-realtime-expose`
**Basis:** `origin/main` HEAD `95bf321`

---

## Bug-Befund

Sub-Slice 34 (commit `04c0b70`) extrahierte den Prepare-Lifecycle aus `Step2EnvSetup.vue` in `useSimulationPrepare.ts`. Dabei wurde die Funktion, die Profile per Polling-Endpunkt nachlaedt, mit einem Underscore-Prefix (`_fetchProfilesRealtime`) als rein intern deklariert und **nicht** im Return-Objekt des Composables exponiert.

`Step2EnvSetup.vue` verwendet aber `fetchProfilesRealtime()` (ohne Underscore) an drei Stellen:

- Z. 318 — nach `addSimulationProfile` (Persona manuell hinzufuegen)
- Z. 404 — nach `addSimulationProfile` (Library-Template wiederverwenden)
- Z. 436 — nach `deleteSimulationProfile` (Persona loeschen)

Da `Step2EnvSetup.vue` kein `<script setup lang="ts">` hat, faengt `vue-tsc` den fehlenden Binding-Eintrag nicht. CI blieb gruen. Im Browser tritt ein `ReferenceError: fetchProfilesRealtime is not defined` auf, sobald ein User eine Persona hinzufuegt oder loescht.

---

## Fix

### `frontend/src/composables/useSimulationPrepare.ts`

1. `UseSimulationPrepareReturn`-Interface: neues Feld `fetchProfilesRealtime: () => Promise<void>` ergaenzt (alphabetisch vor `startPrepare`).
2. Funktionsdefinition: `async function _fetchProfilesRealtime()` umbenannt in `async function fetchProfilesRealtime()`.
3. Interne Aufrufe angepasst:
   - Polling-Callback im `usePolling()`-Aufruf fuer `profilesPolling`: `_fetchProfilesRealtime()` -> `fetchProfilesRealtime()`
   - `_loadPreparedData()`: `await _fetchProfilesRealtime()` -> `await fetchProfilesRealtime()`
4. Return-Objekt: `fetchProfilesRealtime` unter `// actions` vor `startPrepare` eingetragen.

### `frontend/src/components/Step2EnvSetup.vue`

Im Destructure-Block von `useSimulationPrepare()` (ab Z. 116): `fetchProfilesRealtime` zwischen `simulationConfig` und `startPrepare` ergaenzt. Die drei Aufrufstellen (Z. 318, 404, 436) waren bereits korrekt — sie greifen jetzt auf die nun vorhandene destrukturierte Variable zu.

### `frontend/src/composables/__tests__/useSimulationPrepare.spec.ts`

Neuer `describe`-Block **Case 8** mit zwei Tests:

1. `exposes fetchProfilesRealtime als Funktion` — Typ-Check, der bei einer kuenftigen Entfernung des Exports sofort rot wird. Kommentar im Test weist explizit auf den Zusammenhang mit `Step2EnvSetup.vue` hin.
2. `fetchProfilesRealtime() aktualisiert profiles.value wenn API Erfolg liefert` — Verhaltens-Test: ruft `fetchProfilesRealtime()` nach `probeAlreadyPrepared()` (um `_simulationId` zu setzen) und verifiziert, dass `profiles.value` aktualisiert wird.

---

## Test-Counts

| Suite | Ergebnis |
|---|---|
| `useSimulationPrepare` spec (vitest) | alle Cases gruen, +2 neue Tests |
| `Step2EnvSetup` Regression | gruen |
| Frontend `npm run check` | gruen |
| Backend `pytest -x -q` | unveraendert gruen |
| Schema-Drift (`git diff --exit-code schemas/`) | clean |

---

## Offene Punkte

Die eigentliche Wurzel, die diese Klasse von Bugs strukturell moeglich macht, ist das fehlende `lang="ts"` in `<script setup>` von `Step2EnvSetup.vue`. Ohne `lang="ts"` prueft `vue-tsc` die Destructure-Bindings nicht gegen den Return-Type des Composables.

**Migration auf `<script setup lang="ts">` fuer `Step2EnvSetup.vue` ist als Folgearbeit unter Issue #203 offen.** Erst nach dieser Migration werden solche Regressionen (fehlende Destructure-Eintraege, Type-Mismatches in Template-Expressions) permanent per CI gefangen.
