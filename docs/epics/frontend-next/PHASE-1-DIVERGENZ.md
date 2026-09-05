# Phase 1 — Divergenz-Tabelle Modellauswahl (verifiziert)

Erstellt in der Opus-Phase-1+2-Session via CRG + gezieltem Read. Belegt die
gemeldete „inkonsistente Modellauswahl“ als Divergenz über **fünf unabhängige,
nicht gespiegelte Quellen**.

## Kernbefund

Der `AiModelPicker.vue` ist **bereits kanonisch** verdrahtet (`useAvailableModels`
→ Provider-Connections-Discovery, emittiert `AiModelRef`). Die These „Picker auf
Mock-Daten" aus dem Plan ist **obsolet**. Die Divergenz sitzt **nicht im Picker**,
sondern in den **Eltern-Flächen**, die jede in eine andere Senke schreiben/lesen.

## Quellen-Inventar (Writer / Reader)

| # | Quelle | Persistenz | Writer | Reader (Runtime) |
|---|---|---|---|---|
| 1 | `active-config` (`/api/llm/active-config`) | `instance/active_llm_config.json` (eigen) | `SettingsView.vue`, `SettingsGeneralView.vue` | **`llm/client.py:72`** (`use_active_config=True`), `json_mode.py:203` |
| 2 | `routing/defaults` global+stages | Workspace-Routing-Store (eigen) | `SettingsGeneralView.vue`, `LlmProvidersView.vue`, `StepModelOverrideChip.vue` | **`stage_model_router.py:116`** (`global_default`), `llm_routing_seed.py` |
| 3 | `localStorage['agora.hero.aiModelRef']` | Client-only | `HeroNewRun.vue` (Run-Start) | HeroNewRun (init aus localStorage) |
| 4 | `localStorage['agora.home.aiModelRef']` | Client-only | `Home.vue` | Home |
| 5 | `localStorage['agora.report.aiModelRef']` | Client-only | `Step4Report.vue` | Step4Report |
| L | Legacy `llm_profiles` | Server | `EnvSetupModelPanel`/`LlmProfilePicker`, `LlmProfileManager` | Profil-Auflösung |
| R | SSE `model-stream` | — (read-only) | — | `ActiveModelBadge` (nur Anzeige, benign) |

## Warum es divergiert

- **Zwei Server-Wahrheiten (#1 vs #2):** server-seitig nicht synchron. Nur
  `SettingsGeneralView` schreibt beide (Doppelschreib). `SettingsView` schreibt
  **nur** #1, `LlmProvidersView` schreibt **nur** #2 → je nach Screen driftet es.
- **Zwei Runtime-Pfade lesen verschiedene Quellen:** stage-geroutete Simulation →
  #2; generische/Fallback-LLM-Calls → #1. Beide müssen übereinstimmen, nichts
  erzwingt das.
- **Drei client-seitige localStorage-Keys (#3/#4/#5):** Run-Start/Home/Report
  halten je eine eigene Auswahl, komplett vom Server entkoppelt. HeroNewRun liest
  beim Init **nie** den Server-Default → „gleiche Auswahl überall“ bricht hier.
- **Legacy-Profil-Pfad (L):** parallele sechste Selektionswelt in step2.

## Kanonische-Quelle-Frage (offen, Entscheidung erforderlich)

`active-config` (flaches Single-Model, Runtime-Fallback) vs
`routing/defaults.global_default` (reich, per-stage, hat `AiModelRef`-Adapter,
AGENTS.md-Kanon). Beide backend-relevant. Siehe Entscheidungs-Vorlage an Alex.
