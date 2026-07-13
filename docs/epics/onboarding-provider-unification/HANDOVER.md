# Handover — Onboarding/Provider-Unification Slice 5.2

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-2`
- Branch: `codex/onboarding-model-picker-slice-5-2` (Basis: `origin/main` @
  `2ce211a2`, PR #697 gemergt)
- Slice: 5.2 — Discovery-getriebene Daten für den einheitlichen Model-Picker
- Arbeitsstand: implementiert; Frontend-Check und zielgerichtete Picker-/
  Discovery-Specs grün. Pre-Push-Gate sowie PR/CI/Merge stehen noch aus.

## Fertig (Sub-Slice 5.2)

- `useAvailableModels()` bezieht Modelle ausschließlich über den kanonischen
  `llmProviders`-Connection-State (`loadConnections()` +
  `fetchConnectionModels()`). Der bisherige v3-kompatible `PickerModel`-Shape
  bleibt als Read-Adapter erhalten.
- Die Discovery normalisiert `provider_connection_id`, bestätigte
  Capabilities, Connection-/Model-Status und `local_or_cloud`. Nicht
  erreichbare Provider bleiben sichtbar und sind `unavailable`; explizit
  nicht unterstützte Connections bleiben getrennt `unsupported`.
- `AiModelPicker.vue` hat keine produktiven Mock-Daten mehr. `options` ist
  ausschließlich ein expliziter Test-Override; `mode` und
  `capabilityFilter` arbeiten auf demselben Discovery-Datenpfad.
- Der Picker zeigt Provider-Status je Gruppe und unterscheidet die Labels für
  `unavailable` und `unsupported`. Deutsche und englische i18n-Keys liegen
  unter `aiModelPicker.status` und `aiModelPicker.badge`.
- `SettingsGeneralView.vue` verwendet den Picker als v4-Pilot.
- Neue Specs decken Discovery-Normalisierung, Capability-Filter, Offline- und
  Unsupported-Zustand sowie erzwungenen Refresh ab.

## Dokumentations-Sync

- `docs/STATUS.md`: mit `bash scripts/sync-status.sh` aktualisiert.
- `docs/epics/onboarding-provider-unification/slice-5-subplan.md`: Scope
  bleibt Referenz; Status erst nach PR-Merge auf abgeschlossen setzen.
- `PLAN.md`, `README.md`, `CHANGELOG.md`, `AGENTS.md`, `CLAUDE.md`: geprüft,
  für diesen isolierten Frontend-Datenpfad nicht betroffen.

## Verifikation

- `cd frontend && bun run check` — grün.
- Picker-/Discovery-Specs: 20 passed.
- `graphify update .` — Graph aktualisiert; anschließende Query enthielt
  `AiModelPicker.vue`, `useAvailableModels.ts`, `llmProviders.ts` und
  `SettingsGeneralView.vue` im selben Kontext.
- Vor Push zwingend: `bash scripts/pre-push-gate.sh`.

## Bewusst offen

- 5.3 — Backend-Routing-Hierarchie (`AiRoute`).
- 5.4 — übrige Auswahlstellen migrieren.
- 5.5 — alte Picker und Stores deprecaten.
- 5.6 — Playwright-E2E.
