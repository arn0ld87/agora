# Design-v4 Slice F — Views + AppShell-Wrapping

**Datum:** 2026-05-11
**Branch:** feat/design-v4-epic
**Scope:** F1 Settings-Routing, F2 AppShell-Wrapper, F3 Gap-Fixes

---

## Route-Map (alt → neu)

| Alt | Neu | Komponente |
|---|---|---|
| `/` | `/` | `Home.vue` (Landing, unveraendert) |
| — | `/dashboard` | `views/v4/DashboardView.vue` (AppShell-Wrapper, Stub) |
| `/runs` | `/runs` | `views/v4/RunsAppShellView.vue` (Wrapper um RunsView) |
| `/runs/:id` | `/runs/:id` | `views/v4/RunDetailAppShellView.vue` (Wrapper um RunDetailView) |
| `/settings` | `/settings` | Redirect → `/settings/general` |
| `/settings?tab=general` | `/settings/general` | `SettingsGeneralView.vue` |
| `/settings?tab=integrations` | `/settings/integrations` | `SettingsIntegrationsView.vue` |
| `/settings?tab=users` | `/settings/users-teams` | `SettingsUsersTeamsView.vue` |
| `/settings?tab=api-keys` | `/settings/api-keys` | `SettingsApiKeysView.vue` |
| `/settings?tab=audit` | `/settings/audit-logs` | `SettingsAuditLogsView.vue` |
| `/settings/llm-routing` | `/settings/llm-routing` | `LlmRoutingView.vue` (unveraendert) |
| — | `/settings-classic` | `SettingsView.vue` (Fallback waehrend Slice-G-Migration) |

---

## AppShell-Wrapper-Architektur

```
RunsAppShellView.vue
  └── <AppShell breadcrumbs=["Runs"]>
        └── <RunsView />        ← unveraendert, eigener Brand-Header bleibt (Slice H)

RunDetailAppShellView.vue
  └── <AppShell breadcrumbs=["Runs", runId]>
        └── <RunDetailView />   ← unveraendert, kein Inhalt-Refactor

DashboardView.vue
  └── <AppShell breadcrumbs=["Dashboard"]>
        └── Placeholder-Card    ← Slice H extrahiert Home.vue-Inhalt
```

**Hinweis RunsAppShellView:** `RunsView.vue` enthaelt einen eigenen `header.brand` + `AppFooter`. In Slice F ist das bewusst akzeptiert (doppelter Header sichtbar). Slice H extrahiert `RunsView` in Unterkomponenten ohne Shell-eigene Struktur.

---

## F1: Settings-Sub-Views

Alle 5 neuen Views unter `frontend/src/views/Settings/`:

| View | Route | Breadcrumbs |
|---|---|---|
| `SettingsGeneralView.vue` | `/settings/general` | Settings / General |
| `SettingsIntegrationsView.vue` | `/settings/integrations` | Settings / Integrations |
| `SettingsUsersTeamsView.vue` | `/settings/users-teams` | Settings / Users & Teams |
| `SettingsApiKeysView.vue` | `/settings/api-keys` | Settings / API Keys |
| `SettingsAuditLogsView.vue` | `/settings/audit-logs` | Settings / Audit Logs |

Jede View: AppShell + PageHeader + 1 Card-Stub mit Slice-G-Hinweis + RouterLink zur klassischen SettingsView.

Sidebar: Alle 5 Sub-Items verwenden jetzt `{ name: 'SettingsXxx' }` statt `{ query: { tab: ... } }`.

---

## F3: Gap-Fixes

### Gap 4 (LOW) — Test-Router-Helper

`frontend/src/components/v4/shell/__tests__/testRouter.ts` mit `makeTestRouter(extraRoutes?)`:
- Enthaelt alle BASIS_ROUTES inkl. der 6 Settings-Sub-Routes
- AppShell.spec.ts und Sidebar.spec.ts migriert

### Gap 5 (MEDIUM) — Icon-Registry bolt

Bereits in Slice E geschlossen: `IconBolt.vue` existiert, in `Icon.vue` als `bolt` und `branch`-Alias registriert. `ActiveSnapshotsCard.vue` nutzt einen Warning-Dreieck-Inline-SVG (kein Bolt) — kein Ersatz noetig.

---

## Test-Counts Delta

| Kategorie | Vorher | Nachher | Delta |
|---|---|---|---|
| Test-Files | 65 | 68 | +3 |
| Tests gesamt | 598 | 626 | +28 |

Neue Specs:
- `SettingsSubViews.spec.ts`: 15 Tests (3 × 5 Views)
- `AppShellWrappers.spec.ts`: 13 Tests (DashboardView 4, RunsAppShellView 4, RunDetailAppShellView 4, +1 extra)
- `testRouter.ts`: Helper (kein Test-Count)
- AppShell.spec.ts / Sidebar.spec.ts: migriert, gleiche Test-Anzahl

---

## Bundle-Delta (Lazy-Chunks)

Neue Lazy-Chunks im Build:

| Chunk | JS | CSS |
|---|---|---|
| `SettingsGeneralView` | 0.86 kB | 0.10 kB |
| `SettingsIntegrationsView` | 0.90 kB | 0.10 kB |
| `SettingsUsersTeamsView` | 0.89 kB | 0.10 kB |
| `SettingsApiKeysView` | 0.88 kB | 0.10 kB |
| `SettingsAuditLogsView` | 0.87 kB | 0.10 kB |
| `DashboardView` | 0.88 kB | 0.10 kB |
| `RunsAppShellView` | 5.41 kB | 5.05 kB |
| `RunDetailAppShellView` | 7.84 kB | 3.41 kB |

Settings-Stubs sind minimal (~0.9 kB). Runs-Wrapper gross, weil RunsView/RunDetailView inline eingebettet sind.

---

## Commits Slice F

| Hash | Beschreibung |
|---|---|
| `07303d8` | test(design-v4): extract makeTestRouter helper + migrate AppShell/Sidebar specs |
| `9d70260` | feat(design-v4): scaffold 5 dedicated Settings sub-views |
| `15dc585` | feat(design-v4): wire Settings sub-routes in router + fix LlmRouting breadcrumb |
| `cf55013` | feat(design-v4): update Sidebar links to dedicated Settings routes + Dashboard |
| `5e4f13a` | feat(design-v4): wrap Runs + RunDetail + Dashboard in AppShell |

---

## Visual-Verification (welche Views zeigen Inhalt, welche Stub)

| Route | Inhalt |
|---|---|
| `/dashboard` | Stub mit Slice-H-Hinweis |
| `/runs` | Voller RunsView-Inhalt (doppelter Header in Slice F noch sichtbar) |
| `/runs/:id` | Voller RunDetailView-Inhalt im AppShell-Frame |
| `/settings/general` | Stub mit Link zu /settings-classic?tab=general |
| `/settings/integrations` | Stub mit Link zu /settings-classic?tab=integrations |
| `/settings/users-teams` | Stub mit Link zu /settings-classic?tab=users |
| `/settings/api-keys` | Stub mit Link zu /settings-classic?tab=api-keys |
| `/settings/audit-logs` | Stub mit Link zu /settings-classic?tab=audit |
| `/settings/llm-routing` | Vollstaendiger LLM-Routing-Editor (Slice E) |
| `/settings-classic` | Klassische SettingsView.vue (Tab-basiert, Fallback) |

---

## Folge-Schritte

### Slice G — Settings-Content-Migration

- Inhalte aus `SettingsView.vue` (583 LOC) in die 5 neuen Stub-Views extrahieren
- `SettingsView.vue` + `/settings-classic`-Route entfernen
- Jede View: echte Cards statt Stubs (Formulare, Listen, Tabellen)
- `/settings` redirect bleibt auf `SettingsGeneral`

### Slice H — Step1-5 + Home-Refactor

- `Home.vue` (922 LOC) in Unterkomponenten aufteilen: `HeroSection`, `FeatureGrid`, `CTASection` etc.
- `RunsView.vue` eigenen Brand-Header entfernen, `RunsDashboard`-Komponente direkt im AppShell-`<main>` rendern
- `RunDetailView.vue` Brand/Back-Button entfernen, Breadcrumbs im AppShell uebernehmen
- Step1–5-Views in AppShell-Wrapper einbetten (analog zu Slice F)

### Slice I — Compare/History/Graph-Diff

- CompareView, GraphDiffView in AppShell wrappen
- Sidebar-Item "Projects" mit echter Route verdrahten
