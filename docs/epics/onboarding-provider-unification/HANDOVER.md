# Handover — Onboarding/Provider-Unification Slice 4.4

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-slice-4-4-fact-embedding`
- Branch: `codex/onboarding-fact-embedding-reembed`
- Basis: `origin/main` @ `499d1bd0` (Slice 5.5, PR #705, gemergt)
- Slice: 4.4 — Fact-Embedding-Re-Embed (`RELATION.fact_embedding`)

## Aufgabe

Die in Slice 4.3.4 (PR #694) eingeführte `Neo4jReEmbedder`-Engine
re-embedded bisher **nur** `(n:Entity).entity_embedding`.
`RELATION.fact_embedding` war ein dokumentiertes „Bewusstes Nicht-Ziel"
und blieb beim Embedding-Modellwechsel stale → Search-Correctness-Lücke
für die Relations-Suche. Slice 4.4 zieht `fact_embedding` gleich: ein
zweiter, Resume-fähiger Re-Embed-Loop über die `:RELATION`-Kanten,
sequenziell nach der Entity-Phase, über denselben provider-neutralen
Embedding-Pfad.

## Storage-Modell-Befund (Verifikation vor Implementierung)

`fact_embedding` ist eine echte **`RELATIONSHIP`-Property** auf
`:RELATION`-Kanten — kein reifizierter Fakt-Knoten. Damit ist der
Entity-Loop (Node-Property via `db.create.setNodeVectorProperty`) **nicht**
1:1 übertragbar. Konsequenzen:

- Vector-Index-Ddl für Relationships: `FOR ()-[r:RELATION]-() ON (r.<prop>)`
  (Neo4j 5.13+, Stack ist 5.18 CE — supported).
- Schreibfunktion: `db.create.setRelationshipVectorProperty(r, ...)`
  statt `setNodeVectorProperty`.
- `:RELATION` trägt eine eigene `uuid` (siehe `neo4j_write`) → stabiler
  Cursor analog `n.uuid`, kein neues Sortierkriterium nötig.
- Fact-Text: `coalesce(r.fact, r.name, '')` (`r.fact` ist der beim Ingest
  embeddede Text; Fallback für Bestandsrelations ohne `fact`-Property).

## Entscheidung: Cursor-Strategie (mit Sign-off)

**Gewählt:** ein einzelnes Phasen-Feld `phase: Literal["entity","fact"]`
in `EmbeddingMigrationProgress` (statt zwei getrennter Cursor-Spalten
`entity_last_processed_id` / `fact_last_processed_id`).

- `last_processed_id` bleibt der einzige Cursor; `phase` disambiguiert,
  ob er eine Entity-UUID oder eine RELATION-UUID referenziert.
- Default `"entity"` hält persistierte Alt-Jobs (Slice 4.3.4) ohne
  Migration ladbar — backward-kompatibel, `extra="forbid"` gewahrt.
- Layer-0-Touch ist additiv/regenerierbar: Pydantic-Feld + `dump_schemas`
  + Zod-Spiegel `.strict()`/`superRefine`.

**Phasenwechsel ohne separaten Checkpoint:** Beim Übergang
`entity -> fact` setzt die Engine `phase` und `last_processed_id=None`
nur im Speicher (`model_copy`), ohne `checkpoint()` aufzurufen. Erst
`_drain(fact)` schreibt den ersten Fact-Checkpoint mit dem frisch
gezählten Fact-Bestand. Begründung: ein separater Checkpoint am
Phasenübergang hätte den Entity-Endstand (`total=3`) als irreführenden
„Fact-Start" persistiert. Crash-Sicherheit bleibt erhalten — beim
Resume läuft die (leere) Entity-Phase idempotent durch (kein Träger mit
`uuid > cursor` → kein Write, kein Doppel-Write) und wechselt dann zur
Fact-Phase.

## Implementierung

`backend/app/services/embedding_reembedder.py` (erweitert, kein Rewrite
der Entity-Phase):

- Zwei Query-Sätze: `_ENTITY_*` (unverändert, `setNodeVectorProperty`)
  und `_FACT_*` (`count(r)`, Cursor `r.uuid > $cursor`,
  `setRelationshipVectorProperty`).
- `run()` bekommt keyword-only `fact_target_index_name` /
  `fact_target_property_key` (beide `None` → backward-kompatibel, nur
  Entity-Phase wie 4.3.4).
- Phasen-Ablauf: Entity-Phase (übersprungen wenn `progress.phase=="fact"`)
  → bei `failed>0` sofort `return "failed"` (kein Switch auf
  unvollständigen Index-Satz) → Phasenwechsel im Speicher → Fact-Phase.
- `_drain(...)` als gemeinsamer Helper für beide Phasen: DDL anlegen
  (additiv, `IF NOT EXISTS`, niemals DROP — ADR-0007), count, fresh-Reset
  bei `last_processed_id is None` (sonst nur `total`-Update), Batch-Loop
  mit Alignment-Drift-Guard (Vektoranzahl ≠ Textanzahl ⇒ RuntimeError)
  und Dimensions-Guard pro Vektor, Checkpoint pro Batch.
- `_fact_index_ddl` / `_entity_index_ddl` als Modulfunktionen;
  `_require_identifier` bewacht alle vier Identifier (Entity- + Fact-
  Index-/Property-Namen) gegen Cypher-Injection.

`backend/app/services/embedding_migration.py`: `ReEmbedder`-Protocol und
`_NoopReEmbedder` um die beiden Fact-Parameter erweitert;
`EmbeddingMigrationService.run()` leitet die Fact-Namen **konventionell**
aus der Ziel-Version ab (`fact_embedding_v{N}`) und gibt sie an die Engine.

`EmbeddingIndexVersion` bleibt bewusst **entity-only** — der versionierte
Index-Vertrag verwaltet weiterhin nur `entity_embedding_vN`. Fact-Namen
werden konventionell abgeleitet und der Engine explizit übergeben. Ein
Folge-Slice kann fact-spezifische `EmbeddingIndexVersion`-Datensätze
einführen; das ist hier nicht vorgetäuscht.

## Verifikation

- `backend/tests/contracts/test_embedding_contract.py`: 3 neue Tests
  (phase default 'entity'/Legacy-Roundtrip, entity+fact Roundtrip,
  unbekannte phase abgelehnt).
- `backend/tests/services/test_embedding_reembedder.py`: 9 neue Fact-
  Tests (Happy Path, versionierter Relationship-Index, Fact-Resume,
  Fact-Dimension-Mismatch, leerer Graph beide Phasen, Entity-Skip bei
  `phase=="fact"`, Entity-Failure skippt Fact, backward-kompatibel ohne
  Fact-Targets, Fact-Identifier-Guard) + alle Entity-Regressionstests
  gegen `fact_target=None` laufen grün.
- `frontend/src/contracts/__tests__/embeddingContract.spec.ts`: 3 neue
  Zod-Tests (phase default, roundtrip, unbekannte phase abgelehnt).
- `schemas/embedding-migration-job*.schema.json`: regeneriert via
  `dump_schemas --check` (`phase` mit `default:"entity"`,
  `enum:["entity","fact"]`).
- Gates: 377 Contract-Tests, 46 Schemas driftfrei, ruff + mypy clean,
  32 ReEmbedder-/Migration-Service-Tests, 17 Frontend-Zod-Spec grün.

## Bewusst offen (Folge-Slices)

- Gemini-Re-Embedding / Batch-Embedding bleibt explizit **nicht
  unterstützt** — die Engine ist provider-neutral über den konfigurierten
  Embedding-Pfad und täuscht keine Gemini-Batch-API vor.
- `scope="project"`-Filter: die Zuordnung Projekt → Graph ist nicht Teil
  des Embedding-Vertrags; die Engine läuft global.
- fact-spezifische `EmbeddingIndexVersion`-Datensätze (Fact-Namen heute
  konventionell abgeleitet, nicht versioniert verwaltet).
- Search-Pfad-Umstellung: der Lesepfad muss für den Switch auf die neue
  `fact_embedding_v{N}`-Property/Suchindex angefasst werden (adjazent,
  bewusst nicht Teil dieses Slices — fact-Re-Embed ist ohne
  Index-Version verifizierbar, der Switch selbst ist Operator-Entscheidung).

## Doc-Impact-Matrix

| Dokument | Status | Anmerkung |
|---|---|---|
| README.md | geprüft-nicht-betroffen | keine User-Facing-Feature-Doku; Zahlen via STATUS zentralisiert |
| AGENTS.md | aktualisiert | Stack-Map-Zeile `embedding_reembedder.py` um Fact-Phase ergänzt; Aktive-Epics-Liste („Slices 1–4.3.4 gemerged") wird nach Merge via sync-status auf 4.4 gehoben |
| CLAUDE.md | geprüft-nicht-betroffen | keine Fact-spezifische Claude-Regel; ADR-0007-Referenz unverändert gültig |
| PLAN.md | aktualisiert | „Offen im Slice-4-Umfeld"-Liste: Fact-Embedding-Re-Embed entfernt (umgesetzt), Slice-4.4-Fact-Phase im Fließtext ergänzt |
| docs/STATUS.md | aktualisiert | Aktualisierungs-Protokoll-Eintrag für Slice 4.4; Test-Counts via `sync-status.sh` |
| CHANGELOG.md | aktualisiert | neuer `Added (embedding-reembedder-fact)`-Eintrag; „Bewusst offen: fact_embedding"-Vermerk im 4.3.4-Eintrag aufgelöst |
| HANDOVER.md | aktualisiert | dieser Abschnitt |

---

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
---

# Handover — Onboarding/Provider-Unification Slice 5.5 (final)

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-5`
- Branch: `codex/onboarding-model-picker-slice-5-5`
- Basis: `origin/main` @ `a31fe4f1` (Slice 5.4, PR #703, gemergt)
- Slice: 5.5 — Alte Komponenten und Stores deprecaten

## Entscheidung (Scope, mit Sign-off)

Zwei Spec-Widersprüche vor Umsetzung geklärt und bestätigt:

1. **`useRuntimeLlmOptions` ist kein Model-Picker**, sondern ein
   Per-Run-Credential-Override (Provider + API-Key + Base-URL). Bleibt als
   `@deprecated` Read-Adapter erhalten statt „auf AiModelPicker migriert"
   (das hätte die Ad-hoc-Key-Eingabe entfernt).
2. **v3-Picker als Read-Adapter deprecaten, nicht datenmodell-migrieren.**
   `LlmProfilePicker` ist profilbasiert, `AiModelPicker` connection-basiert —
   eine Voll-Migration der Consumer (EnvSetupModelPanel, Step4Report,
   ReportBranchControls) ist ein eigener Slice mit Gemini-Review, nicht
   Teil der Deprecation.

## Store-Konsolidierung

Neu: `frontend/src/store/aiModels.ts` — führt die drei Stores zusammen,
Pinia-IDs (`llmProviders`/`llmProfiles`/`llmRoutingDefaults`) unverändert,
plus Facade `useAiModelsStore()`. Alle 17 Importer auf `@/store/aiModels`
umgestellt.

### Gelöschte Dateien

- `frontend/src/store/llmProviders.ts`
- `frontend/src/store/llmProfiles.ts`
- `frontend/src/store/llmRoutingDefaults.ts`

### `@deprecated` markierte Dateien (Read-Adapter, bleiben funktional)

- `frontend/src/components/ui/ModelPicker.vue` (verwaist, kein Importeur)
- `frontend/src/components/llm/LlmProfilePicker.vue`
- `frontend/src/components/ActiveModelBadge.vue`
- `frontend/src/components/v4/forms/ModelPicker.vue`
- `frontend/src/components/v4/forms/LlmProfileManager.vue`
- `frontend/src/composables/useRuntimeLlmOptions.ts`

`useAiModelRefAdapter.ts` und `useAvailableModels.ts` bleiben **aktiv** (nicht
deprecatet): der Adapter ist Glue für die 5.4-migrierten v4-Views,
`useAvailableModels` ist die Datenquelle des neuen `AiModelPicker`. Beide nur
auf `@/store/aiModels` umgebogen, Marker entfernt.

## Grep-CI-Check

Umgestellt auf `@deprecated`-Ziel-Erkennung (ersetzt den Opt-in-Marker).
Ein verbotener Import ist erlaubt, wenn das importierte Ziel `@deprecated`
trägt. **Alle** `legacy-model-picker-allow`-Marker aus dem Frontend entfernt
(vorher 20 Marker-Zeilen, jetzt 0). Check lokal grün.

## Verifikation

- `python3 .github/scripts/check_legacy_model_picker.py frontend/src` — clean.
- `python3 .github/scripts/test_check_legacy_model_picker.py` — 8/8.
- `vue-tsc --noEmit` — clean.
- `store/__tests__/aiModels.spec.ts` — 19/19; betroffene View-/Component-Specs
  (StepModelOverrideChip, LlmProvidersView, StepWrapperViews, HeroNewRun,
  LlmRouting, SettingsGeneral, useAvailableModels.connection, LlmProfilePicker)
  — 112/112 grün. Backend `test_ai_route_*` unverändert (kein Backend-Touch).

## Bewusst offen (Folge-Slices)

- Voll-Migration der v3-Consumer (Step2/3-Runtime-Creds, LlmProfilePicker-
  Consumer) auf connection-basierten Picker — eigener Slice + Gemini-Review.
- Löschen der `@deprecated` Read-Adapter, sobald alle Consumer migriert sind.
- 5.6 final: Playwright-E2E (`.skip` entfernen).
---

# Handover — Onboarding/Provider-Unification Slice 5.6-Prep

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-6-prep`
- Branch: `codex/onboarding-model-picker-slice-5-6-prep`
- Basis: `origin/main` @ `165d22f5` (PR #700 gemergt, AiRoute +
  AiModelPicker Discovery in `main`)
- Slice: **5.6-Prep** — Playwright-E2E-Skeleton fuer AiModelPicker.
  Diese Vorbereitung laeuft PARALLEL zu Sub-Slice 5.4
  (`codex/onboarding-model-picker-slice-5-4`, derzeit offen) in einem
  separaten Branch. Der Prep-Branch haengt **nicht** von 5.4 ab und
  darf gemergt werden, sobald die Spec lauffaehig (mit `test.describe.skip()`)
  ist. 5.6 final muss dann nur die `.skip`-Annotation entfernen und
  ggf. Selektor-Pfade an die in 5.4 konkret migrierten Routen anpassen.

## Daten-testid-SSoT

`frontend/src/contracts/testIds.ts` (neu) — wird sowohl von der
Komponente (`AiModelPicker.vue` importiert `@/contracts/testIds`) als
auch von den E2E-Helpern (`frontend/tests/e2e/helpers/testIds.ts`
re-exportiert ueber relativen Pfad, weil
`tsconfig.playwright.json` keinen `@/`-Alias hat) verwendet.

Vergabe-Schema (collision-safe ueber Namespace-Prefix `ai-model-picker-*`):

| Konstante                  | data-testid-Wert           | Wer rendert                                                       |
| -------------------------- | -------------------------- | ----------------------------------------------------------------- |
| `AiModelPickerTestId.root`   | `ai-model-picker`            | Root-Container `<div class="ai-model-picker">`                      |
| `AiModelPickerTestId.input`  | `ai-model-picker-input`      | Trigger-Input (ComboboxInput)                                       |
| `AiModelPickerTestId.search` | `ai-model-picker-search`     | Such-Input im geoeffneten Content                                   |
| `AiModelPickerTestId.group`  | `ai-model-picker-group`      | ComboboxGroup, zusaetzlich `data-provider-connection-id`            |
| `AiModelPickerTestId.option` | `ai-model-picker-option`     | ComboboxItem, zusaetzlich `data-provider-connection-id` + `data-model-id` |
| `AiModelPickerTestId.status` | `ai-model-picker-status`     | Group-Status-Badge (Reserviert; aktuell nicht im Template, fuer 5.4) |
| `AiModelPickerTestId.empty`  | `ai-model-picker-empty`      | ComboboxEmpty (Empty-State)                                          |

5.4 muss in den migrierten Views (HeroNewRun, SettingsGeneralView,
LlmRoutingView, StepModelOverrideChip) **dieselben IDs** vergeben.
Sollte 5.4 weitere Selektoren brauchen, bitte hier ergaenzen — kein
String-Drift zwischen Komponente und Spec.

## data-testid-Anpassungen an `AiModelPicker.vue`

Klein, sauber, additiv. Keine Logik-Aenderung, keine CSS-Anpassung.
Component-Unit-Tests (AiModelPicker.spec.ts + AiModelPicker.discovery.spec.ts)
bleiben gruen (14/14). `vue-tsc` und `eslint` ohne Befund.

- `providerGroups`-Computed: Typ um `provider_connection_id: string`
  erweitert (wird als `data-provider-connection-id` auf der Group
  gerendert). Filter- und Sort-Logik unveraendert.
- `data-testid` an: root `<div>`, Trigger-`<ComboboxInput>`, Such-
  `<ComboboxInput>`, `<ComboboxEmpty>`, `<ComboboxGroup>`, `<ComboboxItem>`.
- Group erhaelt zusaetzlich `:data-provider-connection-id="group.provider_connection_id"`.
- Item erhaelt zusaetzlich `:data-provider-connection-id` und
  `:data-model-id`.

Damit kann eine E2E-Spec gezielt auf eine Provider-Gruppe oder ein
Modell zugreifen, ohne sich auf den (i18n-lokalisierbaren) Display-
Namen verlassen zu muessen.

## Spec-Struktur (Skeletons)

`frontend/tests/e2e/ai-model-picker.spec.ts` (neu) — `test.describe.skip()`,
damit CI gruen bleibt bis 5.4 die Komponente in den Ziel-Views mountet.

Drei Test-Gruppen (jeweils mit `// 5.4: aktiveren sobald ...` Kommentar):

1. **Tastatur-Navigation** (2 Tests)
   - `↓↓↑Enter` oeffnet Combobox, wandert Auswahl, committed.
   - Suche filtert Optionen, Pfeile wandern ueber Treffer.

2. **Provider offline** (2 Tests)
   - Modell mit `status=unavailable` hat `data-disabled` /
     `aria-disabled` UND sichtbares Error-Badge
     (`.ai-model-picker__badge--err`).
   - Provider-Group rendert Status-Label im Group-Header.

3. **Run-Snapshot** (1 Test)
   - GET `/api/runs/<run_id>/llm-routing` liefert
     `ai_route.provider_connection_id` und `ai_route.model_id` passend
     zur Picker-Auswahl; `ai_route.source === 'stage-override'`.
   - Setzt voraus, dass 5.3 (PR #700, gemergt in main) das `ai_route`-
     Feld liefert und 5.4 die Stage-Override-UI auf AiModelPicker
     umgestellt hat.

`frontend/tests/e2e/helpers/aiModelPicker.ts` (neu) — Locator- und
Action-Funktionen ausschliesslich auf `data-testid`-Basis:

- `login(page|context, token?)` — Wrapper fuer `injectAuthToken`
  (Single-User-Token-Mode).
- `getPicker`, `getPickerInput`, `getPickerSearch`,
  `getGroupByConnectionId`, `getOption` — Locator-Builder.
- `openPicker`, `selectOptionByClick`, `drillKeyboard`,
  `readSelectedLabel` — Action-Helfer.

Kein Klassen- oder ARIA-Selector — die Helper sind immun gegen
CSS-Refactors und i18n-Aenderungen.

## Verifikation (lokal)

- `bash scripts/pre-push-gate.sh` — grun (Backend + Frontend + Schemas).
  Spec-File alleine bricht das Gate nicht.
- `vitest run src/components/v4/forms/__tests__/AiModelPicker` —
  14/14 Tests pass (Component-Aenderungen sind additiv).
- `vue-tsc --noEmit` — sauber.
- `tsc --noEmit -p tsconfig.playwright.json` — nur der pre-existing
  Fehler in `tests/e2e/minimal-report.spec.ts:69` (`import.meta` mit
  `module: CommonJS`), nicht von diesen Aenderungen verursacht.
- `playwright test --list tests/e2e/ai-model-picker.spec.ts` —
  5 Tests gelistet, alle als skip markiert.

## Out of Scope (bewusst)

- Echte Migrations-Schritte → Sub-Slice 5.4.
- Store-Konsolidierung → Sub-Slice 5.5.
- 5.6 final: `test.describe.skip()` entfernen, Seed-Daten aus
  5.4 ableiten (konkrete `provider_connection_id` + `model_id`),
  ggf. Save-Button-`data-testid` in der Stage-Override-View ergaenzen,
  grun laufen lassen.

---

# Handover — Onboarding/Provider-Unification Slice 5.6 (final)

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-6`
- Branch: `codex/onboarding-model-picker-slice-5-6`
- Basis: `origin/main` @ `499d1bd0` (Slice 5.5, PR #705, gemergt)
- PR: [#707](https://github.com/arn0ld87/agora/pull/707), Merge-Commit
  `eab4a67e`
- Slice: **5.6 final** — echte Playwright-E2E für den `AiModelPicker`

## Fertig (Slice 5.6 final)

`frontend/tests/e2e/ai-model-picker.spec.ts` enthält fünf aktive Tests:

1. Tastatur-Navigation durch die Modelloptionen und Auswahl per `Enter`.
2. Suche mit gefilterter Trefferliste und Tastaturauswahl.
3. Die Online-Option besitzt `data-status="available"` und ist aktiviert.
4. Das Modell der Offline-Connection fehlt vollständig in der Optionsliste.
5. Der Run-Snapshot wird über die `PATCH`-Response geprüft:
   `provider_connection_id` und `model_id` entsprechen der Stage-Auswahl,
   `source === 'stage_override'`.

Die Skeleton-Annotation `test.describe.skip()` ist entfernt. Die Tests
verwenden ausschließlich die zentralen `data-testid`-Verträge und stabile
Connection-/Modell-IDs.

## Mock-Models-Service und Provider-Seed

Der E2E-Compose-Override startet `mock-models` als deterministischen,
OpenAI-kompatiblen `/models`-Dienst. Damit hängt die Discovery nicht von
externen Providern oder wechselnden Modellkatalogen ab.

`global-setup` erzeugt zwei dedizierte Provider-Connections:

- eine erreichbare `openai_compatible`-Connection für das verfügbare Modell;
- eine nicht erreichbare `openai`-Connection für den Offline-Fall.

Der Test prüft den Offline-Zustand als Abwesenheit der Option. Ein
deaktivierter Eintrag wird nicht vorgetäuscht, wenn Discovery das Modell gar
nicht liefert.

## TestId-SSoT und Capability-Relaxation

`frontend/src/contracts/testIds.ts` enthält zusätzlich
`LlmRoutingTestId.stageRow` und `LlmRoutingTestId.stageSave`. Die Run-ID wird
über `llm-routing-run-id` adressiert. Komponente, Routing-View und E2E-Helper
teilen damit dieselben Selektoren.

Im `chat`-Mode gilt ein Modell bei unbekannter Capability-Lage als geeignet.
Ausgefiltert wird nur, wenn `unsupported_capabilities` die benötigte
Capability explizit nennt. Das verhindert False Negatives bei Providern ohne
vollständige Capability-Metadaten.

## Secrets-Store im E2E-Setup

`scripts/e2e-up.sh` ergänzt `AGORA_SECRET_KEY` in der erzeugten E2E-Umgebung.
Der Provider-Seed kann dadurch Credentials über den regulären Secrets-Store
persistieren, statt einen Test-Sonderpfad einzuführen.

## Verifikation

Die lokale Docker-Installation war defekt. Echte Playwright-Läufe und das
vollständige `scripts/pre-push-gate.sh` wurden deshalb für PR #707 bewusst
suspendiert. Der armserver läuft auf Merge-Commit `eab4a67e`; die beiden
Verifikationsläufe dort stehen weiterhin aus.

## Bewusst offen

- echte Playwright-Ausführung auf dem armserver;
- vollständiges Pre-Push-Gate auf dem armserver.

## Doc-Impact-Matrix

| Datei | Status | Begründung |
| --- | --- | --- |
| `README.md` | geprüft, nicht betroffen | keine neue User-Facing-Funktion; E2E-Infrastruktur bleibt intern |
| `AGENTS.md` | geprüft, nicht betroffen | Stack-Map und verbindliche Projektregeln bleiben unverändert |
| `CLAUDE.md` | geprüft, nicht betroffen | keine neue Claude-spezifische Arbeitsregel |
| `PLAN.md` | geprüft, nicht betroffen | Slice-Reihenfolge und operativer Stand werden durch den Merge nicht neu geschnitten |
| `docs/STATUS.md` | aktualisiert | Slice 5.6 final und bewusst offene armserver-Verifikation dokumentiert |
| `CHANGELOG.md` | aktualisiert | neuer `Added`-Block für E2E, Mock-Discovery und Capability-Relaxation |
| `HANDOVER.md` | aktualisiert | dieser Abschnitt |

## Naechste Schritte (5.6 final)

1. PR mergen (Prep-Skeleton ist grun, 5.4 unabhaengig).
2. Sobald 5.4 den Picker in einer View gemountet hat: `beforeEach`-
   `goto` in `ai-model-picker.spec.ts` an die echte Route anpassen.
3. Skip-Annotation entfernen, Seed-Daten fest verdrahten
   (Empfehlung: dedizierter Test-Provider mit `status=unavailable` im
   global-setup oder im ProviderConnectionStore-Seed).
4. `bash scripts/pre-push-gate.sh` final grun halten.

## Relevante Dateien (Diff zu `origin/main`)

- `frontend/src/components/v4/forms/AiModelPicker.vue` (data-testid +
  provider_connection_id in providerGroups-Type)
- `frontend/src/contracts/testIds.ts` (neu)
- `frontend/tests/e2e/helpers/testIds.ts` (neu, Re-Export)
- `frontend/tests/e2e/helpers/aiModelPicker.ts` (neu)
- `frontend/tests/e2e/ai-model-picker.spec.ts` (neu)
- `docs/epics/onboarding-provider-unification/HANDOVER.md` (dieser Abschnitt)

---

# Handover — Onboarding/Provider-Unification Slice 7.0

## Stand

- Datum: 2026-07-13
- Worktree: `/Volumes/T7/Worktrees/agora/onboarding-slice-7-prep`
- Branch: `codex/onboarding-slice-7-prep`
- Basis: `origin/main` @ `686a53352820816fde0c45da428abc31f5f96036`
- Scope: Docs-only-Subplan für Golden-Gate-System und Informationsarchitektur; kein Produktcode

## Ergebnis

Der atomare Implementierungsplan liegt in
[`slice-7-subplan.md`](./slice-7-subplan.md). Er trennt Foundations,
Accessibility-Harness, Shell/IA, Settings, Onboarding, Picker-Migrationen,
Dead-Code-Cleanup und die bestehende `agora-2026`-Runtime-Exploration in eigene
PRs und enthält:

- verifizierten Design-v4-, Token-, Shell-, Settings-, Onboarding- und
  Model-Picker-Bestand;
- Import-/Impact-Nachweise für `/settings-classic`, Legacy-Picker,
  Mock-Routing, Design-v4-Komponenten, `tokens-v3.css` und `states.css`;
- eine Sidebar-IA-Matrix mit `wire | implement MVP | hide | defer`;
- exklusive Slice-6-Dateigrenzen;
- neun nummerierte, einzeln mergefähige Implementierungs-Sub-Slices mit TDD-,
  Accessibility-, Migrations-, Rollback- und Akzeptanz-Gates.

Graphify und klassische Import-Suchen bestätigen:

- `AiModelPicker.vue` ist der kanonische connection-basierte Picker;
- `components/ui/ModelPicker.vue` besitzt keinen Produktionsimporter;
- `components/v4/forms/ModelPicker.vue` hat noch drei Produktionsimporter;
- Mock-Routing-Daten werden nur von drei selbst unverdrahteten Karten genutzt;
- `/settings-classic` besitzt nur die Lazy-Route als Produktionseinstieg;
- `tokens-v3.css` und `states.css` sind globale, breit konsumierte Sources of
  Truth;
- `tokens-2026.css` und `/agora-2026` bilden bereits eine parallele
  `--a26-*`-Exploration und werden in Slice 7 nicht erweitert.

## Graphify-Nachweis

Im sauberen Haupt-Worktree wurde am Basis-Commit ein frischer code-only Graph
mit 17.951 Nodes und 33.528 Kanten erstellt. CSS-Imports werden im AST-Graphen
nicht abgebildet; die globalen Imports in `frontend/src/main.ts` wurden deshalb
zusätzlich statisch nachgewiesen.

## Zentrale Entscheidungen

1. Erster Implementierungs-PR ist 7.1 (additive Token-/State-Erweiterung).
2. `AiModelPicker.vue` bleibt der einzige Ziel-Picker. Der v4- und der
   profilbasierte Legacy-Picker haben noch produktive Consumer und werden nicht
   voreilig gelöscht.
3. Der Mock-Routing-Unterbaum ist verwaist und erhält einen eigenen Cleanup-PR.
4. `/settings-classic` wird erst nach Feature-Parität per Redirect deprecatet.
5. 7.5b und 7.9c warten auf Slice 6, weil `HeroNewRun`/Step 2/i18n gemeinsame
   Hotspots sind.

## Konfliktgrenze zu Slice 6

Slice 6 besitzt Persona-Count, Run-Vertrag, Step-2-Budgetlogik und deren
E2E-Werte. Insbesondere `HeroNewRun.vue`, `pendingUpload.ts`,
`Step2EnvSetup.vue`, `AgentCapControl.vue`, `usePersonaQuota.ts`,
`personaQuotaContract.ts`, `api/simulation.ts` sowie die Backend-Prepare-/
Simulation-Pfade bleiben außerhalb früher Slice-7-PRs. Der erste empfohlene
Implementierungs-PR 7.1 berührt ausschließlich `tokens-v3.css`, `states.css`
und einen neuen Contract-Test.

## Empfohlene nächste Schritte

1. 7.1 additive Token-/State-Foundation umsetzen.
2. 7.2 Accessibility- und 320-px-Harness ergänzen.
3. 7.7 verwaisten v3-Picker und Mock-Routing löschen.
4. Danach Shell/IA, Settings, Onboarding und die drei Picker-Migrations-PRs in
   der im Subplan festgelegten Reihenfolge bearbeiten.
5. `/agora-2026` erst nach Übernahme relevanter visueller Motive retiren.

## Bewusst offen

- Implementierung sämtlicher 7.x-Sub-Slices;
- Automatisierte Settings-Parität vor Entfernung von `/settings-classic`;
- Vertragstreue Abbildung von `ProviderConnection` auf den bestehenden
  `LlmProfile` im letzten Picker-Migrations-PR;
- Entscheidung über die Dauer des `/settings-classic`-Redirect-Zyklus;
- Reale Accessibility-Befunde aus dem in 7.2 geplanten Axe-/Playwright-Gate;
- echter Browser-/axe-Run für die späteren sichtbaren UI-PRs;
- Auflösung der veralteten Design-v4-Referenz auf die nicht vorhandene Datei
  `docs/2026-05-11-design-v4-app-shell-epic.md` in einem separaten Doku-Cleanup;
- Slice-6-Merge vor 7.5b und 7.9c.
