# Slice 5.2 — EnvSetupModelPanel/Step2EnvSetup auf Kanon-AiModelRef (Folge-PR)

**Status:** nicht begonnen · **Vorgänger:** Phase 1 (PR feat/frontend-next-phase12) ·
**Datum:** 2026-07-17 · **Quelle:** Scout-Workflow `frontend-next-scout` (CRG + Spec-Gap-Analyse) + Alex-Entscheidung 2026-07-17.

> Dieser Slice ist aus Phase 1 ausgegliedert (Alex-Entscheidung: Atomic Slicing, separates
> PR). Phase 1 (Kanon-First-Root-Cause-Fix der Modellwahl) ist ohne EnvSetupModelPanel
> gemergt. Dieser Slice konsolidiert die letzte verbleibende Persistenz-Senke im
> Onboarding-Step2 auf den Kanon.

---

## 1. Alex-Entscheidungen (2026-07-17)

- **Q1 — Scope:** Phase 1 + Specs werden **zuvor** als eigener PR gemergt. **§5.2 ist ein
  separates Folge-PR/Issue.** Begründung: Atomic Slicing, sauberer Review, der
  Backend-Payload-Vertrag (`triggerPrepare`) bekommt eigenen Fokus.
- **Q2 — Backend-Payload:** `triggerPrepare.llm_model` **und** `llm_profile_id` **entfallen**
  (kein Backend-Touch). Reiner FE-Sync via `useEffectiveModelSelection.setGlobalSelection`
  (schreibt `routing/defaults.global` + `active-config` im Gleichschritt).
  Profile → optionale Presets (schlagen dem `AiModelPicker` nur einen Wert vor, kein
  Override, kein eigenes Payload-Feld).

---

## 2. Verifizierter Ist-Stand (Scout)

- **Eltern-Container:** `frontend/src/components/Step2EnvSetup.vue` (561 LOC).
- **Präsentationskomponente:** `frontend/src/components/step2/EnvSetupModelPanel.vue` (235 LOC).
- **Composable:** `frontend/src/composables/useEnvForm.ts` (312 LOC).
- **Kanon-Composable:** `frontend/src/composables/useEffectiveModelSelection.ts` (97 LOC, aus Phase 1).

### Doppelselektionsquellen in Step2EnvSetup (genau diese werden konsolidiert)
1. **localStorage-Modell** via `useEnvForm`: `modelOption` (`'default'|preset|'custom'`) +
   `customModel` + `effectiveModel()`, persistiert via `STORAGE_MODEL='agora.lastModel'` +
   `STORAGE_CUSTOM_MODEL='agora.lastCustomModel'`.
2. **v3-Profil** via `llmProfileId`-Ref (init aus `props.projectData.llm_profile_id`, watch
   mit `userPickedProfile`-Guard) → `v-model:llm-profile-id` an `EnvSetupModelPanel` →
   `LlmProfilePicker` (deprecated v3, `useLlmProfilesStore`). Profil überschreibt Model
   visuell (`is-overridden-by-profile`, `step2.llmProfile.modelIgnored`).

### useEnvForm — was bleibt, was entfällt
- **BLEIBT** (Metadaten-Loader via `getAvailableModels()`): `ollamaModels`,
  `presetModels`, `defaultModel`, `defaultProvider`, `serverDefaultRequiresOllama`,
  `ollamaReachable`, `agentToolsEnabled`, `maxToolCallsPerAction`, `loadingModels`,
  `language` (+ `STORAGE_LANG='agora.agentLanguage'`), `loadModels()`. Die
  `runtimeProvider`-Override-Logik (OASIS-Runtime-Provider) muss erhalten oder
  sauber auf `AiModelRef`-Ebene abgebildet werden — **Pflicht-Verifikation vor Edit**
  (siehe §4 Risiko C).
- **ENTFÄLLT** (Modell-Selektions-Senke): `modelOption`, `customModel`, `modelOptions`,
  `effectiveModel`, `STORAGE_MODEL`/`STORAGE_CUSTOM_MODEL`-Persistenz,
  `storedEffectiveModel`. `useEnvForm` reduziert sich auf einen reinen Metadaten-Loader.

---

## 3. Migrationsplan (7 Schritte, kein Backend-Touch, reiner FE-Sync)

### (a) `Step2EnvSetup.vue` — useEnvForm ersetzen für MODELL-Auswahl
- `const { effectiveRef, effectiveRoute, ensureLoaded, setGlobalSelection, loading } = useEffectiveModelSelection()`
- `onMounted`: `ensureLoaded()` statt `loadModels()` für die Selektion.
  `loadModels()` bleibt für Metadaten (Ollama-Reachability, Agent-Tools, Default-Display).
- `llmProfileId`-Ref + `watch`/`userPickedProfile`-Guard entfallen als **aktive
  Selektionsquelle**; `effectiveRef` wird einzige Wahrheit.
- `serverDefaultRequiresOllama`/`ollamaReachable`/`defaultProvider`/`agentToolsFlags`
  bleiben aus `useEnvForm` (reine Read-only-Flags).

### (b) `EnvSetupModelPanel.vue` — kanonischen `AiModelPicker` einbauen
- Props `modelOption`/`customModel`/`modelOptions`/`loadingModels` entfallen; stattdessen
  `:model-value="effectiveRef" @update:model-value="setGlobalSelection"`.
- `is-overridden-by-profile`-Logik + `step2.llmProfile.modelIgnored`-Hint entfallen.
- `LlmProfilePicker` (deprecated v3) wird **ENTFERNT**. Profile → optionale Presets: ein
  Preset schlägt dem `AiModelPicker` nur einen Wert vor (via `setGlobalSelection` mit
  `source='explicit'` o.ä.), keine eigene aktive Senke.

### (c) `STORAGE_MODEL`/`STORAGE_CUSTOM_MODEL` entfallen
- Selektion lebt in `routing/defaults.global_default` (`useLlmRoutingDefaultsStore`),
  server-seitig persistiert; localStorage-Persistenz entfällt.
- `STORAGE_LANG='agora.agentLanguage'` bleibt unangetastet (Sprache orthogonal zur
  Modell-Auswahl).

### (d) `triggerPrepare` (`Step2EnvSetup.vue:232-264`) — Payload konsolidieren
- `payload.llm_model = effectiveModel()` **ENTFÄLLT** (Q2). Backend
  `stage_model_router.py:116` liest `routing/defaults.global_default` direkt, via
  `setGlobalSelection`-Gleichschritt synchron gehalten → kein doppelter `llm_model`-Payload.
- `payload.llm_profile_id` **ENTFÄLLT** als Override (Q2). Profile sind nur Presets; kein
  eigenes Payload-Feld.
- `runtimePayload()` (Override-Provider) bleibt orthogonal; Override ist kein Profil,
  sondern connection-basiert.

### (e) State/Store-Übersicht
- Ersetzt wird: `modelOption`/`customModel`/`effectiveModel`-Block aus `useEnvForm.ts` +
  `llmProfileId`-Ref-Block aus `Step2EnvSetup.vue`.
- Kanonische Senke ab Migration: `useLlmRoutingDefaultsStore.globalDefault` (`LlmRoute`) +
  `useLlmProvidersStore` (connections), gekapselt in `useEffectiveModelSelection`.
- Vor Entfernen von `useEnvForm`-Code Aufrufer-Prüfung:
  `grep -rn "STORAGE_MODEL\|storedEffectiveModel\|effectiveModel\b" frontend/src`

### (f) Kompatibilität/Hygiene
- `LlmProfilePicker` ist bereits `@deprecated` (Slice 5.5, „keine neuen Importeure");
  Entfernung ist der dokumentierte Folge-Schritt.
- `AiModelPicker` ist der kanonische Picker laut AGENTS.md.
- Zod-Spiegel `AiModelRefSchema` (`frontend/src/contracts/aiModelRef.ts`) validiert
  `effectiveRef` bereits.
- Kein Backend-Touch — `setGlobalSelection` schreibt bereits
  `routing/defaults.global_default` + `active-config` im Gleichschritt, sodass beide
  Runtime-Leser (`llm/client.py::use_active_config`,
  `stage_model_router.py::routing/defaults.global_default`) konsistent bleiben.

### (g) Reihenfolge
1. `useEffectiveModelSelection` in `Step2EnvSetup` verdrahten.
2. `AiModelPicker` in `EnvSetupModelPanel` einbauen.
3. `LlmProfilePicker` + `llmProfileId`-Override entfernen.
4. `useEnvForm` ausdünnen (Metadaten-Loader bleibt).
5. `STORAGE_MODEL`-Keys + `storedEffectiveModel` entfernen (nach grep-Prüfung).
6. Specs anpassen: `frontend/src/composables/__tests__/useEnvForm.spec.ts`,
   `frontend/src/components/__tests__/Step2EnvSetup.spec.ts` (falls vorhanden),
   `useEffectiveModelSelection.spec.ts` erweitern, E2E-Smoke `AiModelPicker` (Issue #739)
   prüfen.

---

## 4. Risiken (Pflicht-Verifikation vor Edit)

- **A — Backend-Payload:** Vor Streichen von `triggerPrepare.llm_model`/`llm_profile_id`
  per CRG/Code-Read verifizieren, dass `stage_model_router.py` und ggf. weitere Consumer
  (`backend/app/api/simulation.py` o.ä.) `routing/defaults.global_default` wirklich
  direkt lesen und `llm_model` im Payload nicht als zwingenden Fallback brauchen.
  Cross-Check mit Backend-Contract (`backend/app/contracts/`).
- **B — OASIS-Runtime-Provider:** `useEnvForm` hat `runtimeProvider`-Override-Logik
  (`defaultRuntimeModelForProvider`, `isRuntimeModelForProvider`,
  `runtimeModelOptionsForProvider` aus `useRuntimeLlmOptions`). Der `AiModelRef`-Kanon ist
  connection-basiert und kennt kein `runtimeProvider`-Konzept direkt. Vor Edit klären, wie
  der Runtime-Provider-Override auf `AiModelRef` abgebildet wird (oder ob er orthogonal als
  Run-Override via `runtimePayload()` erhalten bleibt). **Nicht blind migrieren.**
- **C — LlmProfilePicker-Removal:** `useLlmProfilesStore`-Abhängigkeit prüfen — wenn
  Step2EnvSetup noch andere Profil-Verbraucher hat, Teil-Entfernung statt Komplett-Removal.
- **D — Spec pre-existing failures:** Memory `feedback_subagent_failure_attribution` —
  `useEnvForm.spec.ts`-Brüche sind refactor-induziert, nicht pre-existing; nicht abschwächen.

---

## 5. Hard Constraints (gelten weiter)

- Kein Backend-Touch ohne separaten Slice + User-Sign-off (Q2 bestätigt: kein Backend-Touch).
- Keine Anthropic-Subagents (Workflow/Agent: `model`/`agentType` weglassen).
- Frontend-Toolchain: `bun` (nicht pnpm/npm).
- Kein `--no-verify`, keine Edits auf `main`.
- Pre-Push-Gate: `bash scripts/pre-push-gate.sh frontend`.
- `useEnvForm.spec.ts`-Assertions nicht abschwächen (AGENTS.md Regel 6).