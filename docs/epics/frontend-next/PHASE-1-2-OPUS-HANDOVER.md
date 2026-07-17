# Übergabe-Brief — Agora Frontend-Next, Phase 1+2 (Opus-Session)

Diesen Brief in eine **neue Claude-Code-Session mit Opus als Lead-Modell** pasten
(effort=**high**, nicht xhigh — ausdrückliche Vorgabe Alex'). Arbeitsverzeichnis:
`/Volumes/T7/Projekte/agora`, Repo `arn0ld87/agora`.

Vollständiger Plan liegt unter
`~/.claude/plans/sieh-dir-volumes-t7-projekte-agora-runs-swift-spark.md`
(same machine). Dieser Brief ist die **verifizierte, korrigierte Eingangsinformation** für
Phase 1+2 — er ersetzt nicht den Plan, er verifiziert/korrigiert seine Annahmen.

---

## Entschluss vorab (richtet alle folgenden Schritte aus)

Das React-Lovable-Dashboard (`agora-runs-dashboard`) wird **nicht weiterverfolgt** —
das produktive Vue-3-Frontend (`agora/frontend/`) deckt die 5 „Weiter sinnvoll"-Punkte
der alten Übergabe bereits ab. Das React-Repo dient **nur noch als Vorlage** für zwei
Dinge: (a) die Onboarding-Step-Struktur, (b) das Provider-Connection-Modell für die
Modellwahl. Portiert wird **nach Vue**, gegen dieselben, bereits verifizierten
Flask-Endpunkte. Die alte `docs/epics/frontend-next/HANDOVER.md` beschreibt die
verworfenen React-Slices — **nicht** weiterverfolgen; `frontend-next/`-Scaffold wurde
bereits gelöscht.

Alex' tatsächlicher Schmerzpunkt: **inkonsistente Modellauswahl** im Vue-Frontend
(mehrere parallel existierende State-Quellen, die nicht dieselbe Quelle spiegeln).
Phase 1+2 ist der Kernschmerz und reasoning-intensiv — deshalb Opus-Lead.

---

## Modell- & Session-Strategie (Alex' Vorgabe)

- **Lead: Opus, effort=high** (NICHT xhigh).
- **Subagents: Sonnet** via Workflow-Tool (`agent()` mit `model: "sonnet"`).
  Workflows halten den Hauptkontext sauber — Subagents machen die mechanische
  Implementierung, Opus-Lead macht die State-Konsolidierungs-Entscheidungen und
  verifiziert.
- **Pro Phase eigenes Fenster.** Diese Opus-Session führt **nur Phase 1+2** aus.
  Phase 3 (Kill-Switch), Phase 4 (Graph-Lücken), Phase 5 (Verifikation) werden in
  jeweils eigenen Sessions gemacht — nicht hier.

---

## Verifizierte Fakten aus der glm-Discovery (Korrekturen zum Plan)

### 1. Branch `feat/frontend-next` ist 2 ahead, 0 behind `main`

`git log main..feat/frontend-next` →
`674f698a docs(frontend-next): Frontend-Next-Brief`, `67ad63da feat(registry):
detect MiniMax provider via api.minimax.io base URL`. Strikt voran, kein Merge
nötig. Plan-Option „von main" vs „von feat/frontend-next (WIP mitnehmen)" —

### 2. Uncommitteter WIP ist Accessibility-Polish, NICHT Modellwahl

`git diff` zeigt 4 Dateien, 11 insertions / 6 deletions:

| Datei | Änderung | Natur |
|---|---|---|
| `components/v4/forms/AiModelPicker.vue` | +1 Zeile `:aria-label="placeholderText"` | a11y |
| `components/v4/forms/Field.vue` | `div`→`label`/`span` Wrapping | a11y (Label-Assoziation) |
| `components/v4/forms/SettingsSectionPanel.vue` | 4× `:aria-label="field.key"` | a11y |
| `tests/e2e/golden-gate-accessibility.spec.ts` | 2 Zeilen | a11y-Test |

Der Plan interpretierte dies als „unfertiger Modellwahl-WIP" — **falsch**. Es ist ein
a11y-Fix. Alt-`HANDOVER.md` Zeile 100–104 bestätigt: WIP stammt aus *anderer* laufender
Arbeit, nicht anfassen/committen.

**Empfehlung:** diesen WIP als **eigenen kleinen a11y-Commit** sichern (z. B.
`fix(a11y): aria-label für v4 Forms`), **bevor** der Phase-1+2-Branch entsteht. Nicht
mit Phase-1-Code vermischen. `frontend/test-results/` und `graphify-out/` gehören in
`.gitignore` (Build-/Test-Artefakte), nicht committen.

### 3. Vue hat bereits einen Onboarding-Flow — Port muss migrieren, nicht ersetzen

- `frontend/src/views/onboarding/OnboardingView.vue` (+ Test)
- `frontend/src/router/onboardingGuard.ts` (+ Test)
- `frontend/src/api/` hat `llmProfiles.ts`, und Backend hat `onboarding.py`,
  `llm_active.py`, `llm_providers.py`, `llm_routing.py`, `llm_profiles.py`,
  `user_profile.py`.

Plan sagte „Vue hat vermutlich älteren/anderen Flow — Ist-Stand gegenchecken". Ist
bestätigt: der Port **darf nicht blind ersetzen**. Erst `OnboardingView.vue` lesen,
vergleichen mit React-`contracts/onboarding.ts`-Step-Reihenfolge
(`welcome→profile→providers→chat_model→embeddings→privacy→summary`), dann
migrieren/erweitern. Risiko-Quelle laut Plan: Onboarding-Fortschritt ist bereits
serverseitig persistiert — nicht regressen.

### 4. AiModelPicker.vue hat schon Logik — Mock-These verifizieren

`query_graph file_summary` auf `AiModelPicker.vue` (686 Zeilen) liefert Funktionen:
`refresh`, `deriveSource`, `fallbackReason`, `onUpdate`, `providerStatusLabel`,
`statusTone`, `isDisabled`. `deriveSource`/`onUpdate` deuten auf **bereits
begonnene** Store-/Quellen-Anbindung — der Plan-Claim „noch Mock-Daten, keine
Store-Anbindung (Slice 5.0/5.1)" ist vermutlich **teilweise obsolet**. Der Kopf-Kommentar
der Datei sagt selbst, 5.2 bringe `useAvailableModels()`-Anbindung. **Erster
Schritt der Opus-Session:** Datei lesen, Ist-Stand der Anbindung feststellen, dann
entscheiden was wirklich fehlt (nicht vom Plan-Claim ausgehen).

### 5. CRG deckt das Frontend vollständig — richtig nutzen

`list_graph_stats`: 992 Dateien, 9643 Knoten, 82320 Kanten, Sprachen
`python, javascript, typescript, vue, bash`, Graph zuletzt 2026-07-17 22:33
aktualisiert, **7768 Knoten mit Embeddings** (semantic search verfügbar).

**Stolperfalle:** `semantic_search_nodes` mit *langen* Phrasen („AiModelPicker
model selection") lieferte 0 Treffer. Funktioniert mit **kurzen, präzisen**
Queries. `query_graph` mit Pattern `file_summary` / `callers_of` / `callees_of` /
`tests_for` funktioniert zuverlässig.

**Discovery-Pfad für Phase 1+2 (CRG zuerst, dann gezieltes Read):**

- `query_graph pattern="file_summary" target="frontend/src/components/v4/forms/AiModelPicker.vue"`
- `query_graph pattern="callers_of" target="useAiModelRefAdapter"` und
  `target="useAvailableModels"` → wer konsumiert die Adapter?
- `query_graph pattern="tests_for" target="AiModelPicker"` / `"useAiModelRefAdapter"`
  → bestehende Coverage
- `get_impact_radius` für die Dateien, die geändert werden sollen
- `semantic_search_nodes query="AiModelRef"` / `"active-config"` / `"routing defaults"`
  (kurze Queries) → kanonische Quelle identifizieren

### 6. Vollständiges Inventar der Modellwahl-Konsumenten (Frontend)

Contracts: `contracts/aiModelRef.ts`, `contracts/modelActiveContract.ts`,
`contracts/llmProfileContract.ts`.
Stores: `store/aiModels.ts`, `store/useActiveModelStore.ts`.
Composables/Adapter: `composables/useAiModelRefAdapter.ts`,
`composables/useAvailableModels.ts`.
API: `api/llmProfiles.ts`.
Komponenten: `components/v4/forms/AiModelPicker.vue`,
`components/v4/forms/LlmProfileManager.vue`,
`components/v4/forms/StepModelOverrideChip.vue`,
`components/llm/LlmProfilePicker.vue`, `components/ActiveModelBadge.vue`,
`components/step4/ReportModelControls.vue`, `components/step2/EnvSetupModelPanel.vue`
(Plan nannte fälschlich `Step2EnvSetup.vue`), `views/agora2026/components/ModelPill.vue`.

**Tests (jede Konsument-Datei hat einen Spec):** `useAiModelRefAdapter.spec.ts`,
`useAvailableModels.connection.spec.ts`, `aiModels.spec.ts`,
`useActiveModelStore.spec.ts`, `ActiveModelBadge.spec.ts`,
`LlmProfilePicker.spec.ts`, `ReportModelControls.spec.ts`, `AiModelPicker.spec.ts`,
`AiModelPicker.discovery.spec.ts`, `LlmProfileManager.spec.ts`,
`StepModelOverrideChip.spec.ts`. Die Opus-Session **musst** diese Specs als
Regressionsschutz laufen lassen.

**Divergenz-Tabelle** (welche Quelle liest/schreibt jeder Konsument) ist der erste
Deliverable von Phase 1 — aus den oben verifizierten Dateien per CRG + gezieltem Read
aufzubauen. Kannonische Quelle klären: `GET /api/llm/active-config` vs
`GET /api/llm/routing/defaults` (Plan lässt das Schritt 1 klären).

### 7. Backend-Endpunkte (Referenz, keine Änderung nötig)

`backend/app/api/`: `onboarding.py`, `llm_active.py`, `llm_providers.py`,
`llm_routing.py`, `llm_profiles.py`, `user_profile.py`, `llm.py`. Alle vorhanden
(Plan-Annahme bestätigt). **Kein neues Backend** — nur Vue-Schicht gegen bestehende
Endpunkte.

**Zu klärendes Backend-Konzept:** `llm_profiles.py` (Profile) vs React's reinem
Provider-Connection-Modell. Plan-Risiko: klären ob Profile obsolet werden oder
koexistieren — sonst entsteht die *nächste* Parallel-Quelle (genau das zu behebende
Problem). Provider-Detection-SSoT: `backend/app/llm/providers/registry.py::detect_provider`
(laut CLAUDE.md) — keine neue Heuristik pflegen.

---

## Branch-Strategie

1. WIP als a11y-Commit sichern (s. o.).
2. Phase-1+2-Branch von `feat/frontend-next` (nimmt die 2 Commits + sauberen a11y-Stand
   mit) ODER von `main` (sauberer, aber verliert Frontend-Next-Brief-Commit — nicht
   kritisch da `docs/`). **Empfehlung:** von `feat/frontend-next` nach a11y-Commit —
   der Frontend-Next-Brief (`674f698a`) ist der Kontext für diesen Slice und sollte im
   Branch bleiben.
3. PR-Workflow Pflicht (AGENTS.md): kein Direkt-push auf `main`, PR + Gemini-Sichtung
   (90 s warten) vor Merge.

---

## Phasen-1+2 Aufgabe (präzisiert)

### Phase 1 — Modellwahl-Diagnose & Root-Cause-Fix

1. Bestandsaufnahme aller Konsumenten (Inventar s. o.) → Divergenz-Tabelle (liest/schreibt
   jeder `active-config`, `routing/defaults`, `llm_profiles`, oder eigenen State?).
2. Ziel-Modell aus React übernehmen: ein `AiModelRef` (Provider-Connection-ID +
   Modellname), eine kanonische Quelle, Live-Discovery über
   `GET /api/llm/provider-connections/<kind>/models` (Muster `discoverChatModels`).
3. `AiModelPicker.vue` auf kanonische Quelle umstellen — **aber erst Ist-Stand lesen**
   (`deriveSource`/`onUpdate` existieren schon, s. Punkt 4).
4. Parallele/legacy Pfade (`useEnvForm.defaultModel`, `LlmProfilePicker` falls
   redundant) auf Adapter umstellen oder deprecated markieren — kein zweiter Konsument
   mit eigenem State.
5. Test: `useAiModelRefAdapter.spec.ts` + neue/erweiterte Tests dass Picker, Settings
   und Run-Start **dieselbe** Auswahl sehen (Regressionsschutz gegen genau das
   gemeldete Problem).

### Phase 2 — Onboarding aus React nach Vue portieren

1. Step-Struktur wie React `contracts/onboarding.ts`:
   `welcome→profile→providers→chat_model→embeddings→privacy→summary`, serverseitig
   via `GET/PUT /api/onboarding`, `/api/onboarding/step`, `/api/onboarding/complete`.
   **Aber:** `OnboardingView.vue` existiert schon — migrieren/erweitern, nicht ersetzen.
2. Provider-Schritt: pro Provider API-Key + Base-URL →
   `PUT /api/llm/provider-connections/<kind>`.
3. Chat-Model-Schritt: Live-Modell-Discovery via `GET .../models` nach
   Provider-Speicherung, Auswahl setzt `active-config`.
4. Embeddings-Schritt analog, gegen Embedding-Endpunkte (ADR-0007: Embedding-Config
   lebt in Neo4j, Pfade über `embedding_service.py`/`embedding_migration.py`).
5. Onboarding-Fortschritt bleibt serverseitig (nicht regressen).
6. Nach Abschluss: `AiModelPicker`/Onboarding nutzen denselben `AiModelRef`-Adapter
   aus Phase 1 — keine zweite Modell-Auswahl-Implementierung.

---

## Verifikation & Gates (AGENTS.md)

```bash
cd frontend && npm run check          # bzw. bun run check (frontend = bun, s. Memory)
cd frontend && npm test -- --run
bash scripts/pre-push-gate.sh frontend
```

Frontend-Toolchain-Hinweis (Memory): `bun.lock` ist Canon, `bun run <script>`
statt `pnpm`/`npm` (npm-Befehle in AGENTS.md funktionieren, bun ist bevorzugt).

**Manueller Flow (Kernkriterium für den behobenen Bug):** Onboarding komplett
durchlaufen (Provider → Live-Modell-Discovery → Chat-Model → Embeddings) → Modell in
Settings ändern → Run starten → **dieselbe Modellwahl überall sichtbar** (Picker,
Settings, Run-Start, ActiveModelBadge).

## Evidence-Gating-Hartanker (ADR-0002)

Nicht berührt von Phase 1+2 — aber falls irgendwo Modellwahl mit Report-Confidence
kreuzt: die 5 Hartanker in `backend/app/services/report_prompts.py`,
`snapshots/evidence-gating-hedge-words.txt`, `EvidenceSourceKind`,
`cross_stakeholder_for_high`, `reject_inferred_in_high_confidence` dürfen nicht
geschwächt werden.

## Risiken (aus Plan + verifiziert)

- Onboarding-Port bricht bestehenden serverseitig persistierten Vue-Flow, falls
  Struktur stark abweicht — Ist-Stand vor Port genau lesen (Punkt 3).
- `llm_profiles.py` vs Provider-Connection-Modell: Profile obsolet oder koexistieren?
  Sonst nächste Parallel-Quelle.
- AiModelPicker-„Mock"-These evtl. obsolet — Ist-Stand mit `deriveSource`/`onUpdate`
  zuerst lesen (Punkt 4).
- Uncommitteter a11y-WIP nicht mit Phase-1-Code vermischen (Punkt 2).

## Nächster Schritt für die Opus-Session

1. WIP als a11y-Commit sichern (`git add` der 4 Dateien + spec, eigener Commit).
2. Branch von `feat/frontend-next` für Phase 1+2.
3. CRG-Discovery (Punkt 5) — Divergenz-Tabelle der Konsumenten bauen.
4. `AiModelPicker.vue` + `useAiModelRefAdapter.ts` + `store/aiModels.ts`/
   `useActiveModelStore.ts` + `contracts/aiModelRef.ts`/`modelActiveContract.ts`
   lesen — kanonische Quelle festlegen.
5. Workflow mit Sonnet-Subagents für die Umstellung der einzelnen Konsumenten
   fahren; Opus-Lead verifiziert nach jedem Subagent die State-Konsistenz.
6. Tests grün, Pre-Push-Gate frontend, PR.