# Handover — Onboarding/Provider-Unification Slice 5.4

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-4`
- Branch: `codex/onboarding-model-picker-slice-5-4`
- Basis: `origin/main` @ `165d22f5` (Slice 5.3, PR #700, gemergt)
- Slice: 5.4 — Auswahlstellen auf `AiModelPicker` migrieren

## Fertig (Sub-Slice 5.4)

Alle sechs im Sub-Plan benannten Stellen sind auf den
kanonischen `AiModelPicker.vue` (Slice 5.1) migriert. Der
Vertrags-Wechsel `StageLLMRoute` (v3, `provider_id`) → `AiModelRef`
(v4, `provider_connection_id`) wird durch den neuen
`useAiModelRefAdapter`-Composable (pure + Vue-Factory) gekapselt,
damit 5.5 den v3-Vertrag abschaffen kann, ohne dass eine der
migrierten Stellen erneut angefasst werden muss.

### Schritt 0 — Adapter (Vertragsbrücke)

- `frontend/src/contracts/aiModelRef.ts` (Zod-Spiegel):
  `AiModelRefSchema`, `AiModelSourceSchema`,
  `AiModelRefInputSchema`, `AiModelProviderKindSchema`,
  `AiModelCapabilitySchema`, `AiModelStatusSchema`,
  `AiModelPickerModeSchema`. localStorage-Validierung in HeroNewRun.
- `frontend/src/composables/useAiModelRefAdapter.ts` (neu):
  pure Funktionen `toStageLlmRoutePure`, `toAiModelRefPure`,
  `migrateStoredRoutePure`, `buildProviderKindLookup`,
  `firstConnectionId`, `toStoredModelStringPure`; Vue-Factory
  `useAiModelRefAdapter()` mit Connection-Lookup aus
  `useLlmProvidersStore.connections`. Defensive Fallbacks
  loggen via `console.warn`, wenn eine `provider_connection_id`
  nicht im Connection-Store aufgeloest werden kann.

### Migration 1 — `StepModelOverrideChip.vue`

`v4/forms/StepModelOverrideChip.vue`: `ModelPicker` (alt) →
`AiModelPicker` im Popover. `selectRoute` akzeptiert
`AiModelRef | null`, konvertiert via
`adapter.toStageLlmRoute(...)` fuer `setStageOverride` und
loescht via `clearStageOverride(stageId)` bei `null`. 16
Spec-Tests in `__tests__/StepModelOverrideChip.spec.ts`.

### Migration 2 — `LlmProvidersView.vue`

`views/Settings/LlmProvidersView.vue`: Workspace-Default-Card
nutzt `AiModelPicker` (mode=chat, allow-workspace-default=true).
`setDefault(aiRef)` konvertiert via
`adapter.toStageLlmRoute(aiRef)` und ruft
`defaultsStore.setGlobalDefault(stageLlmRoute)`. Provider-Cards
(Key-Input, Save, Test, Refresh, Disconnect) bleiben unveraendert.
16 Spec-Tests in `__tests__/LlmProvidersView.spec.ts`.

### Migration 3 — `HeroNewRun.vue` (Dashboard)

`v4/dashboard/HeroNewRun.vue`: Hybrid (Profile-Dropdown +
Picker) bleibt. `ModelPicker` → `AiModelPicker` mit mode=chat.
`STORAGE_HERO_ROUTE` (StageLLMRoute-JSON, alt) wird durch
`STORAGE_HERO_AI_REF` (AiModelRef-JSON, neu) ersetzt; `loadStoredModel`
liest **beide** Keys, bevorzugt den neuen und faellt via
`adapter.migrateStoredRoute` auf Legacy zurueck. `STORAGE_MODEL`
(`agora.lastModel`) wird via `adapter.toStoredModelString(aiRef)`
gespiegelt, damit `MainView.handleNewProject` ohne Touch
weiterlaeuft. Legacy-Key wird bei jeder neuen Auswahl explizit
geloescht, um stale Eintraege zu vermeiden. 19 Spec-Tests
in `__tests__/HeroNewRun.spec.ts`. **Bestehender** `HeroNewRun.profiles.spec.ts`
(P5.5) brauchte Pinia-Setup + AiModelPicker-Stub nach der
Migration; in-place angepasst.

### Migration 4 — `LlmRouting/LlmRoutingView.vue` (v3)

`components/LlmRouting/LlmRoutingView.vue` (v3-`RunLlmRoutingPanel`):
Global-Default und Stage-Overrides (7 Stages) jeweils
`ModelPicker` → `AiModelPicker`. `onGlobalDefaultPicked` /
`onStageOverridePicked` konvertieren via
`adapter.toStageLlmRoute(aiRef)`. `RuntimeLlmRouting`-Vertrag
bleibt stabil (v3-Backend-Endpoint `updateRunLlmRouting` /
`patchStageLlmRouting` unveraendert). Reasoning-Effort-Select,
Active-Snapshots-Pane und Call-Events-Pane bleiben unveraendert.
`defineExpose` fuer Testbarkeit der Refs. 14 Spec-Tests in
`__tests__/LlmRoutingView.spec.ts`.

### Migration 5 — `SettingsGeneralView.vue` (Pilot-Abschluss)

`views/Settings/SettingsGeneralView.vue`: bestehender Pilot
(5.2) wird mit Persistenz an `useLlmRoutingDefaultsStore`
geschlossen. `setWorkspaceDefault(aiRef)` ruft
`adapter.toStageLlmRoute` und `defaultsStore.setGlobalDefault`.
Initial-Wert via `adapter.toAiModelRef(defaultsStore.globalDefault)`.
i18n-Key `settings.v4.general.workspaceDefaultModel` ersetzt
das generische `aiModelPicker.label`. 14 Spec-Tests in
`__tests__/SettingsGeneralView.spec.ts`.

### i18n-Keys

- `aiModelPicker.*` (in 5.1 angelegt) bleibt unveraendert.
- `stepModelOverrideChip.{label,modelPlaceholder,overrideBadge,clearOverride,close,lockedBadge}`
  in `de.json` + `en.json` neu.
- `settings.v4.general.workspaceDefaultModel` in `de.json` + `en.json` neu.

### Konfliktstellen, die der Sub-Plan aufgedeckt hat

1. `LlmRoutingView.vue` existiert in zwei Dateien (Settings-View
   ist nur Run-Picker, v3-Komponente hat die 4 Sub-Cards). 5.4
   migriert **beide**; v3-View-Komponente war die 4-Card-Stelle.
2. `SettingsGeneralView` war bereits Pilot aus 5.2 mit totem
   State. 5.4 schliesst mit Persistenz + i18n.
3. `HeroNewRun` hat Profile-Dropdown + Picker als Hybrid; Profil
   bleibt, Picker rechts wird ersetzt (K4-Option i, Alex-Sign-off).
4. `StageLLMRoute` ↔ `AiModelRef` ID-Raum-Wechsel (provider_id
   vs. provider_connection_id) wird komplett durch den Adapter
   versteckt — Aufrufer sehen nur `AiModelRef` ein/aus, der
   v3-Store arbeitet intern weiter mit `StageLLMRoute`.
5. `STORAGE_HERO_ROUTE` (alt) → `STORAGE_HERO_AI_REF` (neu):
   HeroNewRun liest beide Keys parallel, bevorzugt den neuen
   und loescht den alten bei jeder Auswahl, damit kein
   stale Eintrag die spaetere Migration faelscht.

## Verifikation

- `frontend bun x vitest run`: 1344 / 1344 gruen (insgesamt
  161 Test-Files, 4 neue in 5.4: Adapter 16, StepChip 16,
  LlmProviders 16, Hero 19, LlmRouting 14, SettingsGeneral 14).
- `frontend bun x vue-tsc --noEmit`: clean.
- `bash scripts/pre-push-gate.sh`: ALL GREEN (Schemas, Backend
  ruff + mypy + 374 contract tests, sync-status, Frontend lint +
  typecheck + tests + build + Zod-Spiegel).
- `graphify`: nicht erneut gerendert (keine Topologie-Aenderung
  der dokumentierten Symbole; soll im PR-Pipeline-Hook laufen).

## Bewusst offen

- 5.5 deprecatet die alten Picker (`v4/forms/ModelPicker.vue`),
  v3-Picker (`components/ui/ModelPicker.vue`),
  `LlmProfilePicker.vue` und `ActiveModelBadge.vue` vollstaendig.
  Auch die Stores `llmProviders`, `llmProfiles`,
  `llmRoutingDefaults` werden zu `aiModels` zusammengefuehrt;
  der `useAiModelRefAdapter` wird dann obsolet und kann
  entfernt werden.
- 5.6 ergaenzt Playwright-E2E (Tastatur, Provider-offline,
  Run-Snapshot). Aktuelle Spec-Tests decken das Glue-Code;
  echte Browser-Tastatur-Tests sind 5.6-Material.
- Der v3 `ModelPicker` (`components/ui/ModelPicker.vue`) wird
  in v3-Views (Step2EnvSetup, Step3Simulation,
  step4/ReportModelControls) weiterhin benutzt; 5.5+
  migriert diese auch, ist aber explizit nicht Teil von 5.4.
- `STORAGE_HERO_ROUTE` (alter Key) wird in 5.4 bei jeder
  AiModelRef-Auswahl explizit geloescht. Falls ein HeroNewRun
  nach 5.4 noch alte Daten ohne den neuen Key hat, faellt
  `loadStoredModel` via `migrateStoredRoute` auf Legacy
  zurueck; in 5.5 wird der Legacy-Pfad hart abgeschaltet.
- Slice 6 (Persona-Count) und Slice 7 (Golden-Gate-Designsystem)
  folgen nach 5.5/5.6.

---

- 5.4 migriert die produktiven Auswahlstellen auf den neuen Resolver. Die
  bestehende, bereits verflachte `RuntimeLlmRouting` bleibt bis dahin ein
  Legacy-Read-Adapter und erfindet keine Project-/Workspace-Provenienz.
- 5.5 deprecatet alte Picker/Stores vollständig.
- 5.6 ergänzt Playwright-E2E einschließlich Run-Snapshot.
- Danach folgen Slice 6 (Persona-Count) und Slice 7 (Golden-Gate-Designsystem).

## Sub-Slice 5.5 — Grep-Prep

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-5-grep-prep`
- Branch: `codex/onboarding-model-picker-slice-5-5-grep-prep`
- Basis: `origin/main` @ `165d22f5` (PR #700, gemergt)
- PR: [#702](https://github.com/arn0ld87/agora/pull/702)
- Slice: 5.5 (Vorbereitung) — Grep-CI-Check gegen v3-Picker-Importe

### Notiz an 5.5 (Deprecation)

Check ist scharf, Opt-in-Marker existiert, Wrapper-Dateien können sich
freischalten via `<!-- legacy-model-picker-allow: ... -->` bzw.
`// legacy-model-picker-allow: ...`. Subpfade wie
`@/store/llmProviders/index` sind auch ohne Marker erlaubt — der Check
matcht nur den genauen Bare-Specifier.

Aktuell tragen 18 v3-Importe einen Grandfather-Marker
(`pre-5.5 v3 picker importer — see slice-5-subplan.md`); mit der
Migration in 5.4/5.5 sind die Importe zu entfernen (damit fällt der
Marker automatisch mit weg). Leere Opt-in-Reason-Strings werden
zurückgewiesen — der Reason bleibt Pflicht für die Audit-Spur.

CI-Workflow: `.github/workflows/check-legacy-model-picker.yml`
(triggert auf `pull_request` mit `paths: frontend/src/**`).
Lokaler Aufruf: `python3 .github/scripts/check_legacy_model_picker.py`
(Spiegel siehe `docs/runbooks/pre-push-gate.md`, Abschnitt
„Legacy-Picker-Check").
