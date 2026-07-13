# ADR-0009: Einheitlicher Model-Picker und Routing-Hierarchie

- Status: **Accepted**
- Datum: 2026-07-13 (Proposed + Accepted via User-Sign-off)
- Branch: `codex/onboarding-model-picker`
- Bezug: Master-Prompt §5.3, §5.4, §6.1-6.3
- Sub-Plan: `docs/epics/onboarding-provider-unification/slice-5-subplan.md`

## Kontext

Modellauswahl ist im aktuellen Code an **mindestens sechs Stellen** dupliziert:
v3 (`ModelPicker.vue` + `LlmProfilePicker.vue` + `ActiveModelBadge.vue`),
v4 (`v4/forms/ModelPicker.vue` + `StepModelOverrideChip.vue` +
`LlmProviderCard.vue`), vier Stores (`llmProviders`, `llmProfiles`,
`llmRoutingDefaults`, `useActiveModelStore`) und zwei Composables
(`useRuntimeLlmOptions`, `useAvailableModels`). Backend-seitig gibt es vier
LLM-Contracts (`ai_provider_contract`, `llm_profile_contract`,
`llm_routing_contract`, `workspace_routing_contract`) mit teils
überlappender Semantik.

Das verletzt Master-Prompt §5.3 ("nur eine fachliche Quelle für
Provider-Metadaten") und §6.1 ("eine Komponente, eine Semantik").
Konsequenz: Profil-Konflikte zwischen Settings, Dashboard und Run-Stage,
stille Fallbacks auf "Workspace-Default", keine sichtbare Quelle der
tatsächlich genutzten Auswahl, kein einheitlicher Audit-Trail.

## Entscheidung

1. **Eine** `AiModelPicker.vue` ersetzt alle bestehenden Modell-Picker in v4
   (und über Shim/Adapter in v3, bis v3 abgelöst ist).
2. **Eine** kanonische Datenquelle: `useAvailableModels()` liest aus
   `ProviderConnection`-Discovery (Slice 3) + Capability-Metadaten (Slice 1)
   + Active-Model-Store. Andere Stores (`llmProviders`, `llmProfiles`,
   `llmRoutingDefaults`) werden zu Read-Adaptern und nach v4-Migration
   entfernt.
3. **Routing-Hierarchie** (Master-Prompt §6.3) wird server-seitig
   aufgelöst und im Run-Snapshot + Audit-Trail festgehalten:
   `Stage-Override > Run-Override > Project > Workspace > Provider-Fallback`.
4. **Embedding- und Chat-Modelle** nutzen denselben Picker mit `mode`-Prop
   (semantisch identische UX: Suche, Gruppe, Badges, Status).
5. **Stille Fallbacks sind verboten.** Jede effektive Auswahl trägt
   `source` und `fallback_reason` (sofern Fallback).

## Konkrete Umsetzung (geplant über 6 Sub-Slices)

Siehe `docs/epics/onboarding-provider-unification/slice-5-subplan.md` für
verbindliche Sub-Slice-Reihenfolge und Akzeptanzkriterien.

- **5.0 Discovery + Spec-Doc**: Sub-Plan + ADR Accepted (PR #696).
- **5.1 `AiModelPicker.vue` isoliert:** Mock-Daten, Combobox-Pattern,
  ARIA, Tastatur, keine Live-API.
- **5.2 Discovery-getriebene Daten:** Anbindung an `ProviderConnectionStore`
  via `useAvailableModels()`. Pilot-Einsatz in `SettingsGeneralView.vue`.
- **5.3 Backend-Routing-Hierarchie:** `AiRoute`-Resolver, `ai_route_contract`,
  Snapshot + Audit.
- **5.4 Auswahlstellen migrieren:** `HeroNewRun.vue`, `LlmProvidersView.vue`,
  `LlmRoutingView.vue`, `StepModelOverrideChip.vue`, `SettingsGeneralView.vue`
  + i18n-Keys.
- **5.5 Alte Komponenten und Stores deprecaten:** v3-Picker + v3-Stores →
  `@deprecated`, später entfernt.
- **5.6 Playwright-E2E:** Tastatur, Provider offline, Run-Snapshot.

## Folgen

- eine UI-Komponente pro Auswahl-Stelle → konsistente UX;
- kanonische Datenquelle → keine Duplikat-Konflikte;
- sichtbare Quelle + Fallback-Begründung → ehrliche Routing-Transparenz;
- Run-Snapshot speichert `AiRoute` → reproduzierbare Runs;
- Migrations-Aufwand: 4 Stores + 2 Composables + 7 v3-Komponenten
  werden über 6 Sub-Slices abgelöst (kein Big-Bang);
- v3-Code bleibt während 5.1-5.4 lesbar, wird in 5.5 deprecated und
  in einem Folge-Slice entfernt;
- neuer ADR-Supersedes-Trigger: sobald ein Multi-Workspace-Modus kommt,
  muss die Hierarchie um `Workspace`-Override erweitert werden (analog
  ADR-0008 für Single-User).

## Alternativen (verworfen)

- **Status quo beibehalten:** verworfen, weil Master-Prompt §5.3 + §6.1
  explizit verletzt sind und Profil-Konflikte in der Praxis entstehen.
- **Sofortiger Big-Bang-Rewrite:** verworfen, weil v3-Code noch aktiv
  ist (Home.vue, MainView.vue) und ein nicht-inkrementeller Umbau das
  Risiko einer Regression im laufenden Betrieb zu hoch macht.
- **Separater Embedding-Picker:** verworfen, weil UI-Verhalten identisch
  ist (Suche, Gruppe, Badges, Status) und eine zweite Komponente die
  Fragmentierung zementieren würde.
