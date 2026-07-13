# Sub-Plan: Slice 5 — Einheitlicher Model-Picker und Routing

Stand: 2026-07-13 · Status: In Umsetzung (5.0/5.1 gemergt, 5.2 PR ausstehend) · Vorgeschlagener Branch: `codex/onboarding-model-picker`

## Ziel

**Eine** `AiModelPicker.vue`-Komponente, die **alle** Modellauswahl-Stellen im
Frontend (v3 + v4) ersetzt. Backed by eine **kanonische Datenquelle** aus
Provider-Connections (Slice 3) + Capabilities (Slice 1). Klare
Routing-Hierarchie mit sichtbarer Quelle, Run-Snapshot und Audit-Trail.

`/Volumes/T7/Projekte/agora/docs/STATUS.md` und `04-implementation-plan.md`
verweisen auf dieses Dokument für Slice 5.

## Inventur (verifiziert, Stand 2026-07-13)

### Frontend — Modellauswahl-Infrastruktur

**v3 (Legacy, in Home / MainView / Step-Views aktiv):**

- `frontend/src/components/ui/ModelPicker.vue`
- `frontend/src/components/llm/LlmProfilePicker.vue`
- `frontend/src/components/LlmRouting/LlmRoutingView.vue`
- `frontend/src/components/ActiveModelBadge.vue`
- `frontend/src/components/Step2EnvSetup.vue`
- `frontend/src/components/Step3Simulation.vue`
- `frontend/src/components/step4/ReportModelControls.vue`
- `frontend/src/api/profile.ts`

**v4 (aktiv, in Onboarding / Settings aktiv):**

- `frontend/src/components/v4/forms/ModelPicker.vue`
- `frontend/src/components/v4/forms/LlmProfileManager.vue`
- `frontend/src/components/v4/forms/LlmProviderCard.vue`
- `frontend/src/components/v4/forms/StepModelOverrideChip.vue`
- `frontend/src/components/v4/dashboard/HeroNewRun.vue`
- `frontend/src/views/Settings/LlmProvidersView.vue`
- `frontend/src/views/Settings/LlmRoutingView.vue` (4 Sub-Cards:
  `StageOverridesCard`, `GlobalDefaultCard`, `CustomModelCard`,
  `ActiveSnapshotsCard`)

### Frontend — Stores und Composables

- `frontend/src/store/llmProviders.ts`
- `frontend/src/store/llmProfiles.ts`
- `frontend/src/store/llmRoutingDefaults.ts`
- `frontend/src/store/useActiveModelStore.ts`
- `frontend/src/composables/useRuntimeLlmOptions.ts`
- `frontend/src/composables/useAvailableModels.ts`

### Backend — Verträge und Endpoints

- `backend/app/contracts/ai_provider_contract.py` (481 Z. — umfangreichster)
- `backend/app/contracts/llm_profile_contract.py` (47 Z.)
- `backend/app/contracts/llm_routing_contract.py` (110 Z.)
- `backend/app/contracts/workspace_routing_contract.py` (32 Z.)
- `backend/app/api/llm_providers.py`, `llm_profiles.py`, `llm_active.py`,
  `llm_routing.py`, `settings.py`

### Konflikte mit Master-Prompt §5.3 / §6.1

> Es darf nur eine fachliche Quelle für Provider-Metadaten geben.
> Eine Komponente, eine Semantik.

Aktueller Stand: 4 Stores + 2 Composables + v3 + v4 = **6+ Duplikat-Quellen**
für "welches Modell nimmt der Run?". Master-Prompt §5.3 + §6.1 sind explizit
nicht erfüllt.

## Sub-Slice-Aufteilung (6 Stück, je 1 PR)

Reihenfolge ist verbindlich; jeder Sub-Slice endet mit grünem
`scripts/pre-push-gate.sh`, Docs-Sync und atomarem Commit.

### 5.0 — Discovery + Spec-Doc (dieser PR)

- **Ziel:** Doku-SSoT für Slice 5.
- **Scope:** Nur Doku.
- **Lieferung:** dieses Dokument + ADR-0009 (Proposed) + Update
  `04-implementation-plan.md` Slice 5 Verweis.
- **Akzeptanz:** ADR-0009 akzeptiert (User-Sign-off) oder explizit als
  Proposed für Folge-Sub-Slices.
- **Risiko:** niedrig.

### 5.1 — `AiModelPicker.vue` (isolierte Komponente, Mock-Daten)

- **Ziel:** Wiederverwendbare Komponente, **noch** ohne Store-Anbindung.
- **Scope:**
  - `frontend/src/components/v4/forms/AiModelPicker.vue` (neu)
  - Props: `modelValue`, `mode` (`chat` | `embedding`), `placeholder`,
    `disabled`, `allowWorkspaceDefault`, `capabilityFilter`
  - Emits: `update:modelValue` mit `AiModelRef
    { provider_connection_id, model_id, source }`
  - Mock-Daten via `<script setup>` const, durch Tests überschreibbar
  - Provider-Gruppierung, Such-Input, Capability-Badges, Default-Anzeige,
    Status-Indicator
  - Combobox-Pattern (Tastatur ↑↓ Enter Esc Tab)
  - ARIA `role="combobox"`, `aria-expanded`, `aria-activedescendant`,
    Screenreader-Text
  - **Keine** Live-API-Calls, **keine** Store-Anbindung
- **Tests:** 5+ Spec-Tests (Props, Emits, Suche, Tastatur, ARIA, Empty-State)
- **Migration:** keine — Komponente existiert parallel.
- **Risiko:** niedrig.

### 5.2 — Discovery-getriebene Daten

- **Status:** implementiert, lokales Pre-Push-Gate und PR stehen aus.
- **Ziel:** `AiModelPicker.vue` an `ProviderConnectionStore` anbinden.
- **Scope:**
  - `useAvailableModels.ts` erweitern: `provider_connection_id`,
    `capabilities`, `status`, `local_or_cloud`
  - `useActiveModelStore.ts` als zentraler Active-State
  - `llmProviders` + `llmProfiles` Stores: `@deprecated`-Marker,
    Read-Adapter für Migration
  - `AiModelPicker.vue`: liest via `useAvailableModels()`, gruppiert nach
    Provider-Connection-Status, zeigt `unsupported`/`unavailable` getrennt
- **Tests:** 8+ Spec-Tests (Capability-Filter, Status-Anzeige,
  Provider offline, Refresh)
- **Migration:** Pilot-Einsatz in **einer** v4-View (z. B. `SettingsGeneral`)
  als Beweis, dass Store-Anbindung funktioniert.
- **Risiko:** mittel — Touchpoint mit v3-Code.

### 5.3 — Backend-Routing-Hierarchie

- **Ziel:** Server-seitige `AiRoute`-Resolution mit Snapshot + Audit.
- **Scope:**
  - `backend/app/services/ai_route_resolver.py` (neu): Hierarchie
    `Stage-Override > Run-Override > Project > Workspace > Provider-Fallback`
  - `backend/app/contracts/ai_route_contract.py` (neu): `AiRoute
    { source, provider_id, model_id, capabilities, resolved_at,
    fallback_reason }`
  - `backend/app/services/run_snapshot.py` (erweitert): speichert `AiRoute`
    pro Stage
  - `backend/app/services/audit_trail.py` (erweitert): `routing_resolved`
    Event mit allen Quellen + Begründung
  - Bestehende `llm_routing_seed.py` / `stage_model_router.py` als
    Read-Adapter
- **Tests:** 10+ Contract- und Service-Tests (Hierarchie, Fallback,
  Snapshot, Audit)
- **Migration:** bestehende `llm_routing_*`-Endpoints geben jetzt `ai_route`
  zurück; Alt-Felder `@deprecated`.
- **Risiko:** hoch — Kernlogik.

### 5.4 — Auswahlstellen migrieren

- **Ziel:** Alle v3 + v4 Auswahlstellen auf `AiModelPicker.vue` umstellen.
- **Scope:**
  - `HeroNewRun.vue` (Dashboard)
  - `LlmProvidersView.vue` (Provider-Auswahl)
  - `LlmRoutingView.vue` Stage-Overrides
  - `StepModelOverrideChip.vue` (Run-Stages)
  - `SettingsGeneralView.vue` (Workspace-Default)
  - i18n-Keys für neue Stellen (analog i18n-Mini-PR für Embedding)
- **Tests:** 12+ Spec-Tests pro migrierter Stelle
- **Migration:** v3-Views bekommen Shim oder behalten ihren Picker
  (kein Big-Bang); v4 ist die primäre Migrations-Zone.
- **Risiko:** mittel — UX-Regressionen möglich, requires Gemini-Review.

### 5.5 — Alte Komponenten und Stores deprecaten

- **Ziel:** 4 Stores + 2 Composables → 2 Stores (oder 1).
- **Scope:**
  - `llmProviders.ts` + `llmProfiles.ts` + `llmRoutingDefaults.ts`
    zusammenführen in `aiModels.ts` (oder konsolidiert in
    `useActiveModelStore.ts`)
  - `useRuntimeLlmOptions.ts` → `@deprecated`, Read-Adapter
  - v3 `ModelPicker.vue`, `LlmProfilePicker.vue`, `ActiveModelBadge.vue`
    → `@deprecated`, Read-Adapter
  - Löschen erst, wenn alle Stellen in v4 migriert sind (Track via
    grep-CI-Check `legacy_model_picker`)
- **Tests:** Snapshot-Tests, dass v3-Wrapper konsistente API haben
- **Risiko:** hoch — Breaking Change für v3-Code.

### 5.6 — Playwright-E2E

- **Ziel:** Vollständige Picker-Tastatur + Run-Snapshot-Test.
- **Scope:**
  - `frontend/tests/e2e/ai-model-picker.spec.ts` (neu)
    - Tastatur-Navigation ↓↓↑Enter
    - Provider offline: Picker zeigt Status, deaktiviert Modelle
    - Run-Snapshot: gewähltes Modell landet im Run-Snapshot
- **Risiko:** niedrig.

## Migrations-Reihenfolge (Begründung)

- **5.0 → 5.1 → 5.2 → 5.3 → 5.4 → 5.5 → 5.6**:
  Komponente isolieren → Daten → Backend → Migration → Deprecation → E2E.
- **5.5 zuletzt**, damit v3-Code während der Migration noch funktioniert.
- **5.6 zuletzt**, damit Komponente + Backend final stehen.

## Bewusst offen (zu entscheiden in 5.1)

- **Combobox-Bibliothek:** `reka-ui` ist im `package.json` (v2.9.9).
  Combobox-Pattern aus `reka-ui` oder eigene Composition API? → 5.1-Discovery
  entscheidet; Empfehlung: `reka-ui` (keine schwere UI-Bibliothek extra, schon da).
- **`mode=embedding`:** aktuell nur Chat-Modelle; Embedding-Modelle separat
  (Slice 4 hat `EmbeddingConfiguration`). Braucht `AiModelPicker` einen
  `mode`-Prop oder zwei Komponenten? → Empfehlung: **ein** Picker mit
  `mode`-Prop, da UI-Verhalten identisch ist (Suche, Gruppe, Badges, Status).
- **Workspace-Default-Anzeige:** "Workspace-Standard verwenden" als Toggle
  oder nur visuell? → Empfehlung: visuell mit explizitem "Inherit"-Eintrag,
  damit der User immer eine bewusste Wahl trifft.
- **Provider offline:** komplett ausblenden oder mit Status-Warnung sichtbar
  lassen? → Empfehlung: sichtbar lassen mit `degraded`/`unavailable`-Badge,
  damit der User den Fehlerzustand sieht.

## Geänderte Dateien pro Sub-Slice

Siehe Sub-Slice-Beschreibungen oben.

## Tests pro Sub-Slice

Siehe Sub-Slice-Beschreibungen oben.

## Verifikation pro Sub-Slice

`bash scripts/pre-push-gate.sh` muss grün sein (Spiegel 1:1 CI).

## Rollback pro Sub-Slice

- **5.1-5.4:** Revert Commit, v3-Code unangetastet.
- **5.5:** v3-Wrapper bleiben, Stores parallel lesbar.
- **5.6:** Spec-Test reverten.

## Bezug zu anderen Dokumenten

- Master-Prompt §5.3 (kanonische Provider-Registry), §5.4 (Capability-Modell),
  §6.1-6.3 (eine Komponente, Routing-Hierarchie, Audit)
- Epic `04-implementation-plan.md` Slice 5 (High-Level)
- ADR-0006 (Provider-Connections) — Slice 3
- ADR-0008 (Single-User-Profile) — Slice 2
- ADR-0009 (dieser Sub-Plan, Proposed)
- Handover des Epics (`docs/epics/onboarding-provider-unification/HANDOVER.md`)
  wird nach jedem Sub-Slice aktualisiert.
