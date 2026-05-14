# Slice G1 — Settings real (Design v4)

**Branch:** `feat/design-v4-slice-g1-settings-real`
**Datum:** 2026-05-14
**Scope:** Frontend-only. Backend bleibt unverändert.

## Ziel

Die fünf v4-Settings-Subviews waren 35-LOC-Stubs mit "Inhalt folgt in Slice G". Slice G1 macht zwei davon real und gibt den anderen drei einen markenkonformen Empty-State.

## Sektions-Mapping

Der dynamische `.env`-Sektions-Editor aus dem klassischen [SettingsView.vue](../frontend/src/views/SettingsView.vue) wird in zwei thematische Subviews gesplittet. Mapping (verbindlich für G1):

| Subview | `.env`-Sektionen |
|---|---|
| **General** | `llm`, `logging`, `locale`, `ui`, `event_bus`, `security` |
| **Integrations** | `neo4j`, `embedding`, `ontology`, `hybrid_search`, `agent_tools`, `webtools`, `oasis` |

Rationale:
- *General* = Laufzeit-Verhalten der Agora-App selbst (Modellwahl, Logging, UI-Defaults, Secrets).
- *Integrations* = externe Systeme + ihre Treiber.

Save/Discard sind atomar — sektionsübergreifend dirty Keys werden auf beiden Views gemeinsam gespeichert (gemeinsamer `settingsStore`).

## Neue Komponenten

- [SettingsSectionPanel.vue](../frontend/src/components/v4/forms/SettingsSectionPanel.vue) — extrahiert die Field-Tabelle, Tab-Leiste, Save/Discard-Footer und das Secret-Bestätigungs-Modal aus dem klassischen View. Filtert per `allowedSections`-Prop. Reusable für jede thematische Settings-Subview.
- [ComingSoonCard.vue](../frontend/src/components/v4/forms/ComingSoonCard.vue) — markenkonformer Empty-State (Spark-Icon, Titel, Beschreibung, optionaler Fallback-Link) statt nackter "Slice G folgt"-Hinweise.

## Geänderte Views

| View | Vorher | Nachher |
|---|---|---|
| [SettingsGeneralView.vue](../frontend/src/views/Settings/SettingsGeneralView.vue) | Stub | `SettingsSectionPanel` mit 6 General-Sektionen |
| [SettingsIntegrationsView.vue](../frontend/src/views/Settings/SettingsIntegrationsView.vue) | Stub | `SettingsSectionPanel` mit 7 Integrations-Sektionen |
| [SettingsApiKeysView.vue](../frontend/src/views/Settings/SettingsApiKeysView.vue) | Stub | `ComingSoonCard` ("API-Schlüssel-Verwaltung folgt") |
| [SettingsUsersTeamsView.vue](../frontend/src/views/Settings/SettingsUsersTeamsView.vue) | Stub | `ComingSoonCard` ("Multi-User-Verwaltung folgt") |
| [SettingsAuditLogsView.vue](../frontend/src/views/Settings/SettingsAuditLogsView.vue) | Stub | `ComingSoonCard` ("Audit-Trail folgt") |

## i18n

Neuer Block `settings.v4.*` in [de.json](../frontend/src/i18n/locales/de.json) und [en.json](../frontend/src/i18n/locales/en.json) mit Titel/Untertitel für die fünf Subviews + die drei Empty-States + `noSections`-Fallback. Keine hartkodierten UI-Strings.

## Tests

- [SettingsSectionPanel.spec.ts](../frontend/src/components/v4/forms/__tests__/SettingsSectionPanel.spec.ts) — 4 Smokes: Tab-Filterung, versteckte Sektionen, Field-Render, Empty-Banner.
- [ComingSoonCard.spec.ts](../frontend/src/components/v4/forms/__tests__/ComingSoonCard.spec.ts) — 3 Smokes: Titel+Beschreibung, optionaler Fallback-Link an/aus.
- [SettingsSubViews.spec.ts](../frontend/src/views/__tests__/SettingsSubViews.spec.ts) — umgeschrieben auf G1-Realität. Prüft `allowedSections`-Prop für die zwei realen Views, `ComingSoonCard`-Mount für die drei Stubs. Stellt sicher, dass "Slice G" nicht mehr im UI auftaucht.

## Lokale Gates

```
npm run typecheck   # vue-tsc --noEmit: 0 errors
npm run test --run  # 678/678 passed (82 files)
npm run build       # ok, +6.55 kB für SettingsSectionPanel-Chunk
npm run lint        # eslint: clean
```

## Out of Scope (für G2/G3 vorgemerkt)

- Echte Backend-Endpoints für API-Keys / Users & Teams / Audit-Log (Pydantic-Contracts + In-Memory-Stores + Blueprints).
- Pinia-Stores `apiKeys` / `usersTeams` / `auditLog` mit Zod-Schema-Validation.
- LLM-Routing-Subview-Spiegel im AppShell-Style.
