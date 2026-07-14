# Slice 7.6d — Migrationsplan: LlmProfileManager → AiModelPicker

Stand: 2026-07-14. Konkreter Umsetzungsplan für den letzten offenen
7.6d-Scope (siehe `slice-7.6-picker-migration-matrix.md`). Wurde gegen den
aktuellen Code auf `origin/main` verifiziert, nicht gegen die Sub-Plan-Prosa.

## Ist-Zustand (verifiziert)

`frontend/src/components/v4/forms/LlmProfileManager.vue` (646 LoC):

- CRUD-Panel für **provider-zentrische** `LlmProfile` (`@/contracts/llmProfileContract`):
  Felder `name`, `provider` (`LlmProvider`: openai/ollama/gemini/anthropic/…),
  `baseUrl`, `model`, `api_key`. Store: `useLlmProfilesStore` (`@/store/aiModels`)
  mit `create / update / remove / setDefault / fetch`.
- Nutzt legacy `./ModelPicker.vue` (line 13, `<ModelPicker>` line 347,
  `:model-value="pickerValue" @update:model-value="onPickerChange"`).
- `RUNTIME_TO_PROFILE_PROVIDER` (line 24) mapt `ModelPicker.provider_id`
  (Runtime-Provider-String) → `{ provider, baseUrl }`.
- `pickerValue` (line ~130) baut aus `formProvider`/`formModel` ein
  route-ähnliches Objekt `{ provider_id, model_id, provider_options: {} }`.
- `onPickerChange` (line ~153) übersetzt eingehenden `route.provider_id`
  zurück nach `formProvider`/`formBaseUrl`.
- Spec `__tests__/LlmProfileManager.spec.ts` (188 LoC) stubt `ModelPicker`
  (`ModelPickerStub` line 80), testet: rendert Profile, `store.create`-Payload,
  `store.setDefault`. Kein ApiKey-/Fehler-Flow-Test.

`v4/forms/ModelPicker.vue` (160 LoC) ist **der einzige Importer** von
`LlmProfileManager.vue` (relativer Import `./ModelPicker.vue`); keine eigene Spec.

## Semantischer Shift (Kernschwierigkeit)

`ModelPicker` ist **provider-id-basiert** (`provider_id` = Runtime-String wie
`"openai"`). `AiModelPicker` ist **connection-basiert** (`AiModelRef` mit
`provider_connection_id` = UUID aus `ProviderConnectionStore`, plus `model_id`).

Die bisherige Abbildung `provider_id ⇄ LlmProfile.provider` wird ersetzt durch
**`ProviderConnection → LlmProfile`**:

- Ein `ProviderConnection` trägt selbst `provider` + `base_url` (zu prüfen gegen
  `ProviderConnectionStore` / `contracts/providerConnectionContract`).
- Pick im `AiModelPicker` → `AiModelRef{ provider_connection_id, model_id }`
  → lookup der Connection → `formProvider`/`formBaseUrl`/`formModel` ableiten.
- Edit/Load (bestehendes Profil) → aus `profile.provider` eine passende Connection
  best-effort finden. **Unbekannte/fehlende Connection = validierter Fehler**
  (kein silentes Default), wie §7.6d fordert.

Diese Abbildung muss vor der Codierung geklärt + getestet sein — sie ist der
Risikokern, kein reines Find-and-Replace.

## Dateien

| Datei | Änderung |
|---|---|
| `components/v4/forms/LlmProfileManager.vue` | `import ModelPicker` → `import AiModelPicker`; `<ModelPicker>` → `<AiModelPicker>`; `RUNTIME_TO_PROFILE_PROVIDER` ersetzen durch Connection-Lookup (`useProviderConnections` o. ä.); `pickerValue` → `AiModelRef`-Builder; `onPickerChange` → Connection→Profile-Mapping + unknown-connection-Fehler |
| `components/v4/forms/__tests__/LlmProfileManager.spec.ts` | `ModelPickerStub` → `AiModelPickerStub`; `store.create`-Payload-Test an Connection-Mapping anpassen; **neu**: unknown-connection → Fehler (kein create); a11y-Tastatur-Smoke für den Picker |
| `components/v4/forms/ModelPicker.vue` | **löschen** (nach Commit 1, wenn kein Importer mehr) |

## TDD-Reihenfolge

1. **RED** — Spec auf `AiModelPicker` + Connection-Mapping umstellen;
   `unknown-connection`-Fall als neuer Test (erwartet Fehler/anzeige, kein
   `store.create`-Aufruf). Build schlägt fehl (ModelPicker noch da, Spec
   erwartet AiModelPicker).
2. **GREEN** — `LlmProfileManager.vue` auf `AiModelPicker` migrieren;
   Mapping implementieren; Spec grün; `bun run typecheck` grün.
3. **DELETE** — `rg "forms/ModelPicker"` leer → `ModelPicker.vue` löschen;
   `bun run typecheck` + targeted Spec grün.
4. **Doku-Sync** — Matrix + dieser Plan: Status auf »done«; `AGENTS.md` /
   `docs/STATUS.md` / `CHANGELOG.md` (LlmProfileManager retired).

## Akzeptanz

- `grep -r "AiModelPicker" frontend/src` = einziger Produktionspicker.
- `grep -rln "v4/forms/ModelPicker" frontend/src` = leer; Datei entfernt.
- `LlmProfileManager.spec.ts` grün (inkl. unknown-connection + a11y).
- `bun run typecheck` + `bun run build` grün; `pre-push-gate.sh frontend` grün.
- Keine neue Contract-Klasse.

## Risiken / Offenpunkte (vor Codierung klären)

- Hat `ProviderConnection` wirklich `provider` + `base_url`? (gegen
  `contracts/providerConnectionContract` + Store verifizieren — nicht
  angenommen). Wenn nicht, ist die Abbildung Connection→Profile nicht
  verlustfrei und braucht eine explizite Selektion im Form.
- `LlmProfile.api_key` vs. Connection-Secrets: Profile verwalten ihr eigenes
  `api_key`; Connections haben separate Secrets. Migration darf das
  Secret-Modell nicht vermischen — nur Provider/BasisURL/Modell mappen.
- Mapping-Implikation für **bestehende Profile** (persistiert im
  Profile-Store): ein Profil mit `provider="ollama"` ohne hinterlegte
  Connection darf im Picker nicht crashen → best-effort-Anzeige + klare
  Aufforderung, eine Connection auszuwählen.

## Empfehlung

Eigener fokussierter PR (`feat/slice-7.6d-llm-profile-manager-ai-picker`),
2 Commits (migrate / delete), dedizierter Frontend-Worker, der nur targeted
Specs laufen lässt (kein Full-Suite-Loop). Nicht am Ende einer langen Session
in Eile — die Connection↔Profile-Abbildung verdient eine eigene Aufmerksamkeitsspanne.