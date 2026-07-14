# Slice 7.6 — Picker-Migrationsmatrix

Stand: 2026-07-14 (nach PR #727 / #728, gegen `origin/main`).

Diese Matrix präzisiert die Pickernutzung, den internen Typ, den Backend-Payload
und die Persistenz je Surface — und ersetzt die leicht widersprüchlichen
Angaben in den PR-Beschreibungen #727/#728 (»migriert« vs. »doch nicht
migriert«) durch eine verifizierte Ist-Aufnahme.

## Verifikationsmethode

Alle Zellen per `grep`/`Read` gegen den aktuellen Code auf `origin/main`
verifiziert (CRG + `ctx_execute`). Persistenz = tatsächliches
`localStorage.setItem(...)` mit dem `…aiModelRef`-Key, nicht nur eine
konstantendefinition.

## Matrix

| Bereich (Datei) | Picker-Komponente | interner Typ | Backend-Payload | Persistenz | Status |
|---|---|---|---|---|---|
| **Hero** (`v4/dashboard/HeroNewRun.vue`) | `AiModelPicker` | `AiModelRef` | `LlmRoute` via `adapter.toLlmRoute()` | `localStorage['agora.hero.aiModelRef']` (JSON, Zod-validiert); Legacy `agora.hero.route` wird nicht mehr gelesen und beim Schreiben entfernt | **fertig, persistiert** |
| **Home** (`views/Home.vue`) | `AiModelPicker` | `AiModelRef` | `LlmRoute` | `localStorage['agora.home.aiModelRef']`; Legacy `agora.home.route` entfernt | **fertig, persistiert** |
| **Report-Auswahl** (`Step4Report.vue`) | `AiModelPicker` (im Kind `step4/ReportModelControls.vue`) | `AiModelRef` | `LlmRoute` | `localStorage['agora.report.aiModelRef']`; Legacy `agora.report.route` entfernt | **fertig, persistiert** |
| **ReportModelControls** (`step4/ReportModelControls.vue`) | `AiModelPicker` | `AiModelRef` | — (controlled child, `emit('update:modelValue')`) | keine eigene — Persistenz obliegt dem Parent `Step4Report.vue` | **fertig** (controlled child, korrekt) |
| **StepModelOverrideChip** (`v4/forms/StepModelOverrideChip.vue`) | `AiModelPicker` | `AiModelRef` | per-Run-Override im Run-Snapshot | run-bounded (kein `localStorage`; Override lebt im Run, nicht pro-Surface) | **fertig** |
| **LlmRoutingView** (`LlmRouting/LlmRoutingView.vue`) | `AiModelPicker` | `AiModelRef` / `LlmRoute` | `LlmRoute` (`/api/llm-routing`) | server-seitig (RuntimeLlmRouting, Pydantic-SSoT) | **fertig** |
| **SettingsGeneralView** | `AiModelPicker` | `AiModelRef` | `LlmRoute` | server-seitig | **fertig** |
| **LlmProvidersView** | `AiModelPicker` | `AiModelRef` | `LlmRoute` | server-seitig | **fertig** |
| **LlmProfileManager** (`v4/forms/LlmProfileManager.vue`) | **legacy `./ModelPicker.vue`** (line 13 import, line 347 `<ModelPicker>`) | `LlmProfile` (provider-basiert) | `LlmProfile` | `localStorage` (Profile-Store) | **OFFEN — 7.6d** |
| **v4-Legacy-Picker** (`v4/forms/ModelPicker.vue`, 160 LoC) | — | `{ provider_id, model_id }` | — | — | **OFFEN — 7.6d: löschen** (einziger Importer ist `LlmProfileManager`) |

## Aufklärung der P1-Annahme »temporär / session-only«

Die Annahme, 7.6c habe für Home / Step4Report / Report-Auswahl nur eine
**session-only**-Auswahl hinterlassen (nicht dauerhaft gespeichert), trifft auf
den aktuellen Code **nicht** zu:

- `Home.vue:70` — `localStorage.setItem(STORAGE_HOME_AI_REF, JSON.stringify(aiRef))`
- `Step4Report.vue:132` — `localStorage.setItem(STORAGE_REPORT_AI_REF, JSON.stringify(val))`
- `HeroNewRun.vue:209` — `writeLocal(STORAGE_HERO_AI_REF, JSON.stringify(aiRef))`

Alle drei Surfaces persistieren die Auswahl nach `localStorage` unter dem
neuen `…aiModelRef`-Key und entfernen den Legacy-`…route`-Key beim Schreiben.
`ReportModelControls.vue` persistiert bewusst nicht selbst — es ist ein
controlled child (`emit('update:modelValue')`); die Persistenz liegt beim Parent
`Step4Report.vue`. Das ist die korrekte Architektur, keine Lücke.

Falls die PR-#728-Beschreibung ein »session-only, Persistenz in 7.6d«
angedeutet hat, war das konservativer als die tatsächliche Implementierung:
die Persistenz ist bereits in `origin/main` geschlossen.

## Echter verbleibender 7.6d-Scope

Gegen `docs/epics/onboarding-provider-unification/slice-7-subplan.md` §7.6d:

1. **`LlmProfileManager.vue` auf `AiModelPicker` migrieren** (646 LoC).
   Letzter Produktionsimporter des legacy `ModelPicker.vue`. Mapping
   `ModelPicker.provider_id` (Runtime) ⇄ `LlmProfile.provider` (Storage) wird
   durch die connection-basierte `AiModelPicker`-Abbildung ersetzt. Flows:
   Profil erstellen/bearbeiten/default setzen, unbekannte Connection als
   validierten Fehler, Picker komplett per Tastatur. Spec
   `__tests__/LlmProfileManager.spec.ts` mitziehen.
2. **`v4/forms/ModelPicker.vue` + ggf. Spec löschen** — nach 1. ist die Datei
   Dead Code (einziger Importer war `LlmProfileManager`). Vor Löschung
   `rg`-Nachweis, dann `bun run typecheck` + targeted Spec grün.

Der ursprünglich für 7.6d genannte »Picker-Spiegel für Home / ReportModelControls«
ist durch 7.6b (PR #727) bereits erledigt — keine Doppel-Migration.

## Akzeptanz für 7.6d (nach Sub-Plan)

- `grep -r "AiModelPicker"` ist der einzige Produktionspicker.
- `v4/forms/ModelPicker.vue` entfernt, kein Import mehr.
- Keine neue Contract-Klasse.
- `LlmProfileManager.spec.ts` + Build grün; `pre-push-gate.sh frontend` grün.