# Phase-2-Übergabe — Onboarding React→Vue

**Datum:** 2026-07-17 · **Phase-1-Stand:** PR #752 offen, gemerged noch nicht
**Vorgänger-Phase:** Phase 1 = Root-Cause-Fix Modellwahl (`bf4c81a7`, Composable `useEffectiveModelSelection`, 6 Flächen migriert). PR: https://github.com/arn0ld87/agora/pull/752
**Verwandte Docs:** `PHASE-1-2-OPUS-HANDOVER.md`, `PHASE-1-DIVERGENZ.md`, `SLICE-5.2-ENVSETUP-KANON-MIGRATION.md`, `HANDOVER-GLM-MMX.md`

---

## 1. Ausgangslage — Vue-Onboarding existiert bereits

`frontend/src/views/onboarding/OnboardingView.vue` ist bereits eine Vue-3-Implementierung mit `vue-i18n`, `vue-router`, `userProfileStore` und `onboardingGuard.ts`. **Es ist NICHT von Grund auf zu portieren.**

**Architektur (bereits da):**
- 7 Steps laut `ONBOARDING_STEP_ORDER`: `welcome`, `profile`, `providers`, `chat_model`, `embeddings`, `privacy`, `summary`
- Steps `providers` / `chat_model` / `embeddings` sind **ehrliche Statusschritte**: zeigen `store.onboarding.requirements?.chat_model_configured` und verlinken via `RouterLink` auf die bestehenden Settings-Routen (`SettingsLlmProviders`, `SettingsEmbedding`). Keine eigene Konfigurationslogik im Onboarding.
- Welcome wählt Operating-Mode (`local`/`hybrid`/`server`); Profile nutzt `ProfileForm`; Embedding-Step hat Legacy-Hint wenn `embedding_source === 'legacy'`.
- Spec: `frontend/src/views/onboarding/__tests__/OnboardingView.spec.ts`.

**Design-Entscheidung (bewusst):**
> *"providers/chat_model/embeddings sind bewusst ehrliche Statusschritte: sie zeigen den realen `requirements`-Status und verlinken auf die bestehenden Settings-Routen. Die geführte Einrichtung folgt in einem späteren Update — hier gibt es keine Attrappen."* — Doc-Kommentar im File.

Diese Entscheidung widerspricht dem React-Original (das einen Inline-Wizard hatte). Der Inline-Pattern wurde **bewusst NICHT** portiert — Phase 1 hat die Settings-Flächen stattdessen kanonisch gemacht.

---

## 2. Was Phase 1 für das Onboarding bedeutet

**Kurz: nichts direkt — aber alles indirekt.**

- Die 3 Onboarding-Statusschritte (`providers`, `chat_model`, `embeddings`) verlinken auf `SettingsLlmProviders` und `SettingsEmbedding`. **Diese Flächen wurden in Phase 1 auf den kanonischen Composable umgestellt.** → Der User sieht und schreibt nun konsistent `routing/defaults.global_default` + `active-config` (die beiden Frontend-facing-Senken).
- `store.onboarding.requirements.chat_model_configured` wird jedoch **weiterhin** in `compute_onboarding_requirements()` aus `settings.llm_model_name` berechnet (Zeile 232–234 in `onboarding_state_store.py`). Phase-1-Schreibpfade (`PUT /api/llm/routing/defaults/global`, `PUT /api/llm/active-config`) ändern `settings.llm_model_name` nicht — dieser Pydantic-Settings-Wert stammt aus Env-Variablen und ist zur Laufzeit effektiv immutabel.
- **Integration-Gap:** `chat_model_configured` reflektiert die Phase-1-Modellwahl nur, wenn `settings.llm_model_name` unabhängig gesetzt wurde (z. B. via `.env`), oder beim nächsten `/api/onboarding`-Reload nachdem `settings.llm_model_name` extern geändert wurde. Ein Phase-1-Write allein führt nicht zu einem synchronen `chat_model_configured = true`. Phase 2 (oder ein Folge-Slice) muss klären, ob `compute_onboarding_requirements()` stattdessen `routing/defaults.global_default` oder `active-config` prüfen soll.

---

## 3. Verbleibende Phase-2-Arbeit — Klärung mit Alex erforderlich

### 3.1 Design-Konflikt: Inline-Flow oder Statusschritt?
Das React-Original hatte einen geführten Inline-Wizard (Form-Felder direkt im Onboarding-Step). Das aktuelle Vue-Onboarding hat **bewusst** Statusschritte. Zwei mögliche Wege:

| Option | Was | Trade-off |
|---|---|---|
| **A (aktuell)** | Statusschritt beibehalten, nur Settings-Link | Ehrlich, keine Duplikat-Wahrheit, weniger FE-Code. Aber User muss Onboarding verlassen → zurück → weiter. UX-Reibung. |
| **B (React-Stil)** | Inline-Wizard nachportieren | Besserer UX-Flow, aber **AiModelPicker müsste zweimal existieren** (im Onboarding und in Settings). Divergenz-Risiko — genau das, was Phase 1 gerade behoben hat. **Vermutlich nicht der richtige Weg.** |
| **C (Hybrid)** | Statusschritt bleibt, aber Inline-Mini-Picker pro Step mit Kanon-Composable | Mittelweg. Erfordert neue Spec/Architektur. |

**Frage an Alex:** Soll Phase 2 das Onboarding bei Statusschritten belassen, oder doch auf Inline umstellen? Ich empfehle **A** (Status quo) oder **C** (Hybrid), **nicht B**.

### 3.2 Optionale Verfeinerungen (unabhängig vom Design-Konflikt)
Falls bei A geblieben wird, sind diese Verbesserungen denkbar:
1. **`Step-Status-Granularität verbessern`** — Aktuell nur `chat_model_configured` ja/nein. Wäre `providers` (alle konfiguriert) vs. `chat_model` (genau eins gewählt) vs. `embeddings` getrennt aussagekräftiger? Aktuell sind `providers` und `chat_model` redundant (beide prüfen `chat_model_configured`).
2. **Embedding-Legacy-Hint bereinigen** — sobald `embedding_service.py` final Gemini-Re-Embedding unterstützt (Phase-F-Restpunkt).
3. **Wizard-Progress-Bar mit echten Prozenten** statt nur 7-Step-Liste.
4. **„Skip"-Button** auf Statusschritten ausblenden, wenn der Step noch nicht `configured` ist (sonst irreführend).

### 3.3 Phase-1-Berührung im Onboarding (optional)
Wenn gewünscht, könnte der Welcome-Step den aktuellen Default via `useEffectiveModelSelection().effectiveRef` anzeigen (rein informativ, kein Write). Mini-Migration, isoliert.

---

## 4. Hard Constraints (gelten weiter)

- **KEIN** zweiter `AiModelPicker` im Onboarding (Divergenz-Risiko). Wenn überhaupt, dann `<AiModelPicker :model-value="effectiveModel.effectiveRef.value" :readonly="true" />` als reinen Status.
- **KEINE** zusätzlichen localStorage-Senken für Modellwahl (Phase-1-Bann).
- **i18n** via `vue-i18n` (keine hartkodierten Texte).
- **Composable `useEffectiveModelSelection`** ist die einzige Quelle für Modell-Schreibzugriffe.
- Profile → optionale Presets, **kein** eigener aktiver State.
- Keine Anthropic-Subagents (Memory).
- bun-Toolchain (`bun run check`, `bun run test`).
- Pre-Push-Gate frontend.

---

## 5. Erster Schritt der Folge-Session (Phase 2)

1. **Design-Konflikt klären** (siehe §3.1). Frage an Alex direkt, nicht autonom entscheiden.
2. Bei A (Status quo): Spec erweitern → §3.2 Verfeinerungen priorisieren.
3. Bei B/C: Neuer Sub-Slice-Brief analog zu `SLICE-5.2-ENVSETUP-KANON-MIGRATION.md` schreiben.
4. Branch von `feat/frontend-next-phase12` (oder direkt von `main`, falls Phase 1 gemerged ist).
5. Wie immer: typecheck → specs → lint → pre-push-gate → PR + 90s Gemini-Sichtung → Merge.

---

## 6. PR #752 — Phase-1-Merge abwarten

PR #752 ist **offen, nicht gemerged**. Vor Phase-2-Beginn:
- Gemini-/CodeRabbit-Findings sichten (Memory: `feedback_pr_gemini_workflow` — 90s warten).
- Findings adressieren oder bewusst zurückstellen.
- Dann mergen.
- Erst danach Phase-2-Branch von `main` (oder von `feat/frontend-next-phase12`, falls Alex das so will) starten.
