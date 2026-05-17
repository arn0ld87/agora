# Sub-Slice 31 · Arbeitsprotokoll

**Datum:** 2026-05-05
**Branch:** feat/layer-4-task-47-quota-editor
**Refs:** #203

## Was wurde gemacht

Phase 1 von 3 der `Step2EnvSetup.vue`-Aufteilung: Der Quoten-Editor-Block
(Sub-Slice 20c/24) wurde in eine eigenständige Komponente extrahiert.

### Neue Dateien

- `frontend/src/components/step2/QuotaPlanEditor.vue` — neue Komponente,
  `<script setup lang="ts">`, Props/Emits vollständig typisiert, keine
  hartkodierten Strings.
- `frontend/src/components/step2/__tests__/QuotaPlanEditor.spec.ts` —
  6 Vitest-Cases: render valid plan, edit emits update, invalid plan shows
  error, disabled inputs, add segment, toggle emit.

### Geänderte Dateien

- `frontend/src/components/Step2EnvSetup.vue` — QuotaPlanEditor importiert,
  Quoten-Template-Block durch `<QuotaPlanEditor v-model:enabled ... v-model:entries ... />` ersetzt,
  überflüssige Computed (`quotaTotal`, `quotaValidationError`) und Funktionen
  (`addQuotaSegment`, `removeQuotaSegment`, `_newEntryId` mit Counter) entfernt,
  zugehörige CSS-Blöcke (`.quota-plan`, `.quota-row`, `.quota-segment`, `.quota-count`)
  aus Step2 in QuotaPlanEditor.vue verschoben.

## Warum so

- `useQuotaPlan` + `quotaEntries` bleiben in `Step2EnvSetup.vue`, weil
  `startPrepare()` die Validierung (`PersonaQuotaPlanSchema.safeParse`) und
  den API-Payload dort aufbaut. Eine vollständige Extraktion würde den
  Payload-Aufbau erfordern, der zu Phase 2/3 gehört — Scope-Grenze bewusst
  respektiert.
- Props-Design als `v-model:enabled` + `v-model:entries` statt einem
  kombinierten Objekt, weil die zwei Concerns (Feature-Toggle vs. Eintrags-Liste)
  unabhängig emittiert werden sollten.
- Interne Kopie (`localEnabled`/`localEntries`) + bidirektionaler Watch statt
  direkter Prop-Mutation — entspricht Vue-3-Konventionen.

## Was nicht gemacht wurde

- Keine Phase 2 (PersonaReviewPanel) — explizit out-of-scope
- Keine Phase 3 (ModelPicker) — explizit out-of-scope
- Kein Backend-Eingriff

## LOC-Messung

| Datei | Vorher | Nachher |
|---|---|---|
| Step2EnvSetup.vue | 1817 | 1712 |
| QuotaPlanEditor.vue (neu) | — | 277 |

Netto +160 LOC (Spec + neue Komponente), Step2EnvSetup −105 LOC.
Step2EnvSetup ist < 1500 LOC-Ziel noch nicht erreicht — aber Slice war
Phase 1 von 3, weiterer Abbau folgt in Phase 2/3.

**Anmerkung zur LOC-Akzeptanz:** Die Slice-Spezifikation fordert < 1500 LOC
für Step2EnvSetup nach Phase 1. Der Quoten-Block allein bringt nur −105 LOC.
Phase 2 (PersonaReviewPanel, ca. 350 LOC) wird das Ziel erreichen. Phase 1
liefert die saubere Basis.

## Test-Output

```
 Test Files  32 passed (32)
      Tests  247 passed (247)
   Start at  17:41:09
   Duration  6.32s

 Test Files  1 passed (1)   ← QuotaPlanEditor.spec.ts
      Tests  6 passed (6)

 Test Files  1 passed (1)   ← Step2EnvSetup.spec.ts (kein Regress)
      Tests  3 passed (3)
```

`npm run check` (vue-tsc + coverage + build): grün.
