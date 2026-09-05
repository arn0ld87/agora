# Übergabe — Frontend-Next Phase 1+2 an MiniMax M3 / GLM 5.2

**Datum:** 2026-07-17 · **Branch:** `feat/frontend-next-phase12` (von `feat/frontend-next`)
**Vorgänger-Opus-Session:** siehe `PHASE-1-2-OPUS-HANDOVER.md` und `PHASE-1-DIVERGENZ.md`
**Auftrag:** Phase 1 (Root-Cause-Fix der Modellwahl) ist **implementiert, uncommittet, ungetestet**. Phase 2 (Onboarding-Port) ist **nicht begonnen**. Diese Übergabe listet den verifizierten Ist-Stand und die nächsten Schritte.

---

## 1. Verifizierter Ist-Stand (Stand 2026-07-17, 23:11)

### Git
```
Branch: feat/frontend-next-phase12  (2 Commits ahead von feat/frontend-next: a11y + gitignore)
Modified (uncommitted):
  .claude/settings.json                            (37 Zeilen — auto-Mode + bun/gh/docker-Allows, BEWUSST von Alex)
  frontend/src/components/Step4Report.vue          (40 Zeilen)
  frontend/src/components/v4/dashboard/HeroNewRun.vue (47 Zeilen)
  frontend/src/views/Home.vue                      (57 Zeilen)
  frontend/src/views/Settings/LlmProvidersView.vue (7 Zeilen)
  frontend/src/views/Settings/SettingsGeneralView.vue (290 Zeilen — Komplettumschreibung)
  frontend/src/views/SettingsView.vue               (14 Zeilen)
Untracked:
  frontend/src/composables/useEffectiveModelSelection.ts        (97 Zeilen — architektonisches Herzstück, von Opus)
  frontend/src/composables/__tests__/useEffectiveModelSelection.spec.ts (202 Zeilen, 12/12 grün)
  docs/epics/frontend-next/HANDOVER.md
  docs/epics/frontend-next/PHASE-1-2-OPUS-HANDOVER.md
  docs/epics/frontend-next/PHASE-1-DIVERGENZ.md
  docs/epics/frontend-next/PHASE-5-VERIFICATION-HANDOVER.md
  (diese Datei)
Diff-Stat: 7 Dateien, 117 insertions, 375 deletions
```

### settings.json
Alex hat `.claude/settings.json` bewusst geändert (defaultMode→"auto", leeres ask[], plus bun/npm/gh/docker-compose-Allows). **Nicht revertieren.** Siehe Diff in `PHASE-1-2-OPUS-HANDOVER.md` §9.

---

## 2. Architekturentscheidung (Phase-1-Root-Cause)

**Problem:** Mehrere Frontend-Flächen schrieben in unabhängige, server-seitig NICHT synchrone Senken. Zwei Backend-Runtime-Pfade lasen verschiedene Quellen:
- `backend/app/llm/client.py:72` → `use_active_config` → `active-config`-Store
- `backend/app/services/stage_model_router.py:116` → `routing/defaults.global_default`
- `backend/app/services/json_mode.py:203` → `active-config`

`llm_active.py` und `llm_routing.py` sind serverseitig **unabhängig persistiert** — nichts synchronisiert sie außer FE-Doppelschreib.

**Kanon-Entscheidung (AGENTS.md-konform):**
- **Kanon = `routing/defaults.global_default`**, repräsentiert als `AiModelRef` via `useAiModelRefAdapter`.
- `active-config` wird beim Schreiben **im Gleichschritt mitgezogen** (KEIN Backend-Touch, reiner FE-Sync).
- Die reinere SSoT (Backend delegiert active-config serverseitig an den Routing-Store) ist ein **bewusst separates Folge-Slice** — nicht in Phase 1 machen.

**Umgesetzt via Composable** `frontend/src/composables/useEffectiveModelSelection.ts`:
```typescript
export interface EffectiveModelSelection {
  effectiveRef: ComputedRef<AiModelRef | null>   // aus global_default via Adapter
  effectiveRoute: ComputedRef<LlmRoute>          // global_default direkt
  loading: Ref<boolean>
  error: Ref<string | null>
  ensureLoaded: () => Promise<void>              // lädt routing-defaults + connections idempotent (hasLoadedOnce-Guard)
  setGlobalSelection: (ref: AiModelRef) => Promise<void>  // routing/defaults.global UND active-config im Gleichschritt
}
```
`setGlobalSelection` schreibt **Kanon zuerst** (`defaultsStore.setGlobalDefault(route)`), dann `setActiveLlmConfig({provider_id, model})` für den Gleichschritt.

**5 frühere Persistenz-Senken (alle entfernt/umgeleitet):**
1. `active-config` (eigene Provider/Modell-Dropdowns in SettingsGeneralView) → **entfernt**, jetzt via Composable
2. `routing/defaults.global_default` → **Kanon**, via Composable
3. `STORAGE_HOME_AI_REF` (localStorage `agora.home.aiModelRef`) → **entfernt**
4. `STORAGE_HERO_AI_REF` → **entfernt** (HeroNewRun: nur noch transienter Run-Override + STORAGE_MODEL-Spiegel für MainView)
5. `STORAGE_REPORT_AI_REF` → **entfernt**

---

## 3. Geänderte Flächen (Kanon-First-Init Pattern)

Alle Per-Run-Flächen folgen jetzt demselben Muster:
```typescript
const effectiveModel = useEffectiveModelSelection()
onMounted(async () => {
  await effectiveModel.ensureLoaded()
  if (!selectedModel.value) selectedModel.value = effectiveModel.effectiveRef.value
})
```

| Datei | Änderung |
|---|---|
| `SettingsGeneralView.vue` | Komplettumschreibung. Entfernte separate "Active LLM Config"-Sektion. Ein `AiModelPicker` via Composable. |
| `SettingsView.vue` (classic) | `saveLlmActive` → `effectiveModel.setGlobalSelection(...)`. |
| `LlmProvidersView.vue` | `setDefault` → `effectiveModel.setGlobalSelection(aiRef)`. |
| `HeroNewRun.vue` | `onPickModel` = transienter Run-Override (nur STORAGE_MODEL-Spiegel). Kanon-First-Init onMounted. |
| `Home.vue` | **WICHTIG:** führte `modelOverridden`-Flag ein. Home nutzte `selectedModel !== null` als Proxy für „User hat explizit gewählt“ im Ollama-Reachability-Gate. Kanon-Vorbelegung würde das brechen → `servicesReady` nutzt jetzt `modelOverridden.value`. Template-Hinweise `!selectedModel` → `!modelOverridden`. |
| `Step4Report.vue` | Kanon-First-Init. Entfernte STORAGE_REPORT_AI_REF, resolveInitialReportRoute, reportRoute-watch-Persistenz. `llmProfileId`/STORAGE_REPORT_PROFILE_ID (Preset) bleibt. |

### Bewusst NICHT geändert
- `LlmRoutingView.vue` — Run-Scoped (`props.runId`, getRunLlmRouting/updateRunLlmRouting), berührt weder active-config noch Workspace-Defaults → keine Divergenzquelle.
- `EnvSetupModelPanel.vue` — reine Präsentationskomponente (nur Props+Emits, kein eigener State, keine Senke). Echte Konsolidierung erfordert Eltern-Container-Bau (useEnvForm/STORAGE_MODEL/Parent) → siehe §5 offener Punkt.
- `ActiveModelBadge.vue`, `LlmProfilePicker.vue` — unkritisch.

---

## 4. Tests — Status

**Grün:**
- `useEffectiveModelSelection.spec.ts` — 12/12 (vom Sonnet-Subagent geschrieben; testet Spiegelung, setGlobalSelection ruft setGlobalDefault + setActiveLlmConfig, Kanon-VOR-active-config-Reihenfolge, ensureLoaded-Idempotenz, Fehler-Propagation).

**NOCH NICHT GELAUFEN (Pflicht vor Commit):**
- `cd frontend && bun run check` (typecheck) — die 6 geänderten Flächen-Dateien sind nicht typecheck-geprüft.
- `cd frontend && bun run test -- --run` — **existierende Specs müssen auf Kanon-First-Verhalten umgeschrieben werden**, weil sie das entfernte localStorage-Verhalten spiegeln:
  - `SettingsGeneralView.spec.ts`
  - `LlmProvidersView.spec.ts`
  - `HeroNewRun.spec.ts`
  - Home-Specs
  - `ReportModelControls.spec.ts` (bzw. Step4Report-zugehörige)
- `bash scripts/pre-push-gate.sh frontend` — finales Gate.

**Memory-Regel beachten:** „Subagent pre-existing failures verifizieren“ — Refactor-induzierte Test-Brüche tarnen sich gerne als Pre-Existing. Wenn Specs rot sind: prüfen, ob der Bruch durch den Phase-1-Refactor kam oder schon vorher rot war (`git stash` + Spec-Run auf HEAD zur Unterscheidung).

---

## 5. Offene Punkte (Reihenfolge = Priorität)

### 5.1 Verifikation + Gates (Pflicht, vor Commit)
1. `cd frontend && bun run check` — typecheck
2. Bestehende Specs auf Kanon-First umschreiben (siehe §4 Liste). RED → GREEN.
3. `cd frontend && bun run test -- --run`
4. `bash scripts/pre-push-gate.sh frontend`

### 5.2 EnvSetupModelPanel / step2-Legacy-Profil-Pfad konsolidieren
Q3-Entscheidung (Alex): „Auf AiModelRef umstellen.“ EnvSetupModelPanel ist reine Präsentationskomponente — Eltern-Container (useEnvForm/STORAGE_MODEL/Parent) muss gefunden und migriert werden. Profile → optionale Presets, keine eigene aktive Selektionsquelle. **Größter verbleibender Schritt.** CRG nutzen, um Parent zu finden: `query_graph pattern="callers_of" target="EnvSetupModelPanel"`.

### 5.3 PR erstellen (nach Gates)
PR + 90 s warten + Gemini-Findings sichten, dann mergen (Memory: `feedback_pr_gemini_workflow`). Niemals direkt FF-pushen.

### 5.4 Phase 2 — Onboarding React→Vue portieren
**Design-Konflikt klären mit Alex, NICHT autonom portieren:** Vue-Onboarding nutzt bewusst „Statusschritte“ (verlinken in Settings) statt React-Inline-Flow. Ein Port würde diese Designentscheidung überschreiben. Jede Modellwahl im Onboarding muss den Phase-1-Composable nutzen. Siehe `PHASE-1-2-OPUS-HANDOVER.md` für Details.

---

## 6. Hard Constraints (gelten weiter)

- **NIE** API-Keys/Secrets in Code, Logs, Fixtures, Doku.
- **NIE** `--no-verify`, `--force`, `--no-gpg-sign` ohne explizite User-Anweisung.
- **NIE** Edits auf `main`. PR-Workflow ist Default. Branch: `feat/frontend-next-phase12`.
- **NIE** `curl`/`wget` in Bash (Hook geblockt) — `ctx_fetch_and_index`/`WebFetch`.
- **NIE** `cat`/`head`/`tail`/`sed`/`echo` für Dateioperationen — `Read`/`Edit`/`Write`.
- context-mode Hook-Decisions sind bindend.
- Evidence-Gating-Hartanker (ADR-0002) NIE ohne `docs/decisions/0002-supersedes.md` + User-Sign-off schwächen. **Phase 1+2 berührt diese nicht** — keine Backend-Prompt-/Validator-Änderungen.
- Pre-Push-Gate Pflicht: `bash scripts/pre-push-gate.sh frontend`.
- Frontend-Toolchain: **`bun` ist Canon** (`bun run <script>`), NICHT pnpm/npm (Memory: `agora-frontend-toolchain`).
- **Keine Anthropic-Subagents** (Memory: `feedback_no_anthropic_subagents`) — Workflow/Agent: `model`/`agentType` weglassen → Session-Modell erben; keine Claude-Varianten.
- `.claude/settings.json`-Änderung war beabsichtigt von Alex — nicht revertieren.

---

## 7. Erster Schritt der Folge-Session

1. `cd /Volumes/T7/Projekte/agora && git status` verifizieren (sollte §1 entsprechen).
2. `cd frontend && bun run check` laufen lassen — typecheck-Brüche in den 6 Flächen fixen.
3. Bestehende Specs umschreiben (§4) — RED → GREEN.
4. Dann §5.2 (EnvSetupModelPanel-Parent) via CRG angehen.
5. Gates + PR (§5.1/§5.3).
6. Phase 2 nur nach Alex-Klärung (§5.4).