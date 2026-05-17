# Design v4 — Slice B: App Shell (Worklog 2026-05-11)

Branch: `feat/design-v4-slice-b-shell`
Worktree: `/private/tmp/agora-v4-shell`
Basis: `feat/design-v4-slice-a-tokens`

## Komponenten-Map (JSX → Vue)

| ds-shell.jsx | Vue-Komponente | Pfad |
|---|---|---|
| `DSAppShell` | `AppShell.vue` | `components/v4/shell/AppShell.vue` |
| `DSSidebar` | `Sidebar.vue` | `components/v4/shell/Sidebar.vue` |
| — (Item-Render) | `SidebarItem.vue` | `components/v4/shell/SidebarItem.vue` |
| — (Settings-Block) | `SidebarGroup.vue` | `components/v4/shell/SidebarGroup.vue` |
| `DSHeader` | `Topbar.vue` | `components/v4/shell/Topbar.vue` |
| — (Crumbs-Fragment) | `Breadcrumbs.vue` | `components/v4/shell/Breadcrumbs.vue` |
| `DSPageHeader` | `PageHeader.vue` | `components/v4/shell/PageHeader.vue` |
| `Icon` (inline) | `Icon.vue` + `icons/*.vue` | `components/v4/shell/Icon.vue` |

## Routes-Mapping (Sidebar-Items → Agora-Routen)

| Sidebar-ID | Label | Route |
|---|---|---|
| `dashboard` | Dashboard | `{ name: 'Home' }` |
| `runs` | Runs | `{ name: 'Runs' }` |
| `projects` | Projects | `{ path: '#projects' }` — Stub, noch keine Route |
| `datasets` | Datasets | `{ path: '#datasets' }` — Stub |
| `templates` | Templates | `{ path: '#templates' }` — Stub |
| `monitoring` | Monitoring | `{ path: '#monitoring' }` — Stub |
| `general` | General | `{ name: 'Settings', query: { tab: 'general' } }` |
| `integrations` | Integrations | `{ name: 'Settings', query: { tab: 'integrations' } }` |
| `users-teams` | Users & Teams | `{ name: 'Settings', query: { tab: 'users' } }` |
| `api-keys` | API Keys | `{ name: 'Settings', query: { tab: 'api-keys' } }` |
| `llm-routing` | LLM Routing | `{ name: 'Settings', query: { tab: 'llm-routing' } }` |
| `audit` | Audit Logs | `{ name: 'Settings', query: { tab: 'audit' } }` |

## Icons-Liste

12 Icons als Mini-SVG-Komponenten in `components/v4/shell/icons/`.
ViewBox: `0 0 20 20`, stroke-width 1.6, stroke-linecap round.

| Name | Datei | Mappt auf |
|---|---|---|
| `home` | `IconHome.vue` | Home-Icon (Haus) |
| `bolt` | `IconBolt.vue` | Blitz / Runs |
| `folder` | `IconFolder.vue` | Ordner |
| `layers` | `IconLayers.vue` | Ebenen / Datasets |
| `doc` | `IconDoc.vue` | Dokument / Templates |
| `spark` | `IconSpark.vue` | Stern / Monitoring |
| `settings` | `IconSettings.vue` | Zahnrad (Sonne-Stil) |
| `chevron` | `IconChevron.vue` | Pfeil-unten (collapsed) |
| `chevronD` | `IconChevronD.vue` | Pfeil-unten (open) — identisch mit chevron, Slice F kann animieren |
| `arrowL` | `IconArrowL.vue` | Pfeil-links (Collapse-Footer) |
| `search` | `IconSearch.vue` | Lupe |
| `plus` | `IconPlus.vue` | Plus |
| `branch` | — | Alias auf `bolt` (DS_NAV-Compat) |

Nicht-registrierte Icons (kein Crash, Dev-Warnung): Bell ist inline in `Topbar.vue` verbaut.

## Token-Verbrauch (v3-Tokens)

Alle genutzten Tokens aus `tokens-v3.css` (Slice A):

| Token | Verwendung |
|---|---|
| `--surface-canvas` | AppShell-Hintergrund |
| `--surface-base` | Sidebar, Topbar, Inspector-Hintergrund |
| `--surface-hover` | SidebarItem/SidebarGroup hover |
| `--hairline` | Sidebar border-right, Topbar border-bottom, Inspector border-left |
| `--separator` | Sidebar Footer border-top |
| `--accent` | Active-Color in Items, Notification-Badge, Avatar-Color, Group-Active-Border |
| `--accent-tint-bg` | Active-Background in Items, Avatar-Background |
| `--text-primary` | Labels, Wordmark, PageHeader h1 |
| `--text-secondary` | Sidebar Footer, Topbar Icons, Breadcrumbs non-last, Subtitle |
| `--text-quaternary` | Breadcrumbs-Separator |
| `--font-sans` | Wordmark, PageHeader h1 |

## Test-Counts

| Spec-File | Tests |
|---|---|
| `AppShell.spec.ts` | 7 |
| `Sidebar.spec.ts` | 9 |
| `SidebarItem.spec.ts` | 8 |
| `Topbar.spec.ts` | 6 |
| `useShellStore.spec.ts` | 9 |
| **Slice-B-Delta** | **+16** (39 neu inkl. Icon-Komponenten werden via AppShell/Sidebar mitgetestet) |
| **Gesamt** | **540** (vorher 524) |

## File-Liste (neue Files, LOC)

| Pfad | LOC |
|---|---|
| `frontend/src/components/v4/shell/AppShell.vue` | 130 |
| `frontend/src/components/v4/shell/Sidebar.vue` | 188 |
| `frontend/src/components/v4/shell/SidebarItem.vue` | 81 |
| `frontend/src/components/v4/shell/SidebarGroup.vue` | 115 |
| `frontend/src/components/v4/shell/Topbar.vue` | 146 |
| `frontend/src/components/v4/shell/Breadcrumbs.vue` | 54 |
| `frontend/src/components/v4/shell/PageHeader.vue` | 54 |
| `frontend/src/components/v4/shell/Icon.vue` | 70 |
| `frontend/src/components/v4/shell/icons/IconHome.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconBolt.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconFolder.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconLayers.vue` | 12 |
| `frontend/src/components/v4/shell/icons/IconDoc.vue` | 14 |
| `frontend/src/components/v4/shell/icons/IconSpark.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconSettings.vue` | 11 |
| `frontend/src/components/v4/shell/icons/IconChevron.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconChevronD.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconArrowL.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconSearch.vue` | 10 |
| `frontend/src/components/v4/shell/icons/IconPlus.vue` | 10 |
| `frontend/src/stores/shell.ts` | 67 |
| `frontend/src/views/v4/AppShellDemoView.vue` | 69 |
| `frontend/src/components/v4/shell/__tests__/AppShell.spec.ts` | 120 |
| `frontend/src/components/v4/shell/__tests__/Sidebar.spec.ts` | 127 |
| `frontend/src/components/v4/shell/__tests__/SidebarItem.spec.ts` | 98 |
| `frontend/src/components/v4/shell/__tests__/Topbar.spec.ts` | 80 |
| `frontend/src/components/v4/shell/__tests__/useShellStore.spec.ts` | 100 |
| `frontend/vite.config.js` | +4 (resolve.alias hinzugefuegt) |
| **Gesamt neu** | ca. 1.640 LOC |

## Bekannte Luecken / Offene Punkte fuer Slice F (View-Integration)

1. **4 Stub-Routen** (Projects, Datasets, Templates, Monitoring) haben `{ path: '#...' }` — kein echter Route-Name. In Slice F entweder echte Routen anlegen oder Items als disabled markieren (cursor-not-allowed, opacity 0.4).

2. **chevron vs. chevronD** sind aktuell identische SVG-Pfade. Slice F kann die Rotation per CSS-Transition animieren (transform: rotate(180deg)) statt zwei Icons.

3. **Bell-Icon** ist inline in `Topbar.vue` (keine Registry-Komponente). Sobald der Icon-Set in Slice C/D erweitert wird, sollte `bell` in `Icon.vue` registriert werden.

4. **sidebarCollapsed-UI** ist im Store vorbereitet (`sidebar--collapsed`-Klasse), aber die Collapsed-Darstellung (nur Icons, kein Label) ist in `Sidebar.vue` noch nicht vollstaendig implementiert — Labels werden mit `v-if="!collapsed"` ausgeblendet, Icons bleiben. Slice F prueft ob 56px-Collapsed-Width passt oder ein Overlay-Modus besser ist.

5. **AppShellDemoView** ist nicht im Router. Slice F registriert die Route (z.B. `/v4-demo` als dev-only Route).

6. **useRoute() in AppShell** setzt voraus dass der Router installiert ist. Demo-View liefert den Router via Plugin. Fuer echte Integration muss `App.vue` den Shell nicht doppelt einbinden.

7. **Inspector-Topbar-Span**: Bei `inspector-open` spannt sich die Topbar aktuell nur ueber Spalte 2 (nicht 2/3). Duerfte korrekt sein, aber Slice F soll visuell validieren.

8. **i18n**: Sidebar-Labels (Dashboard, Runs, Settings etc.) und Topbar-Aria-Labels sind Hardcoded-Deutsch/Englisch — kein `t()`-Wrapper. Da es sich um Navigations-Struktur-Labels handelt die aus DS_NAV kommen, wurde bewusst kein i18n-Key angelegt. Slice F entscheidet ob das in `de.json`/`en.json` wandert.

## Commits (Slice B)

```
d6e0dcf test(design-v4): smoke tests for shell components
5fb4963 feat(design-v4): port PageHeader component
20de125 feat(design-v4): add useShellStore for sidebar/inspector state
fb6f838 feat(design-v4): port Sidebar + SidebarItem + SidebarGroup
f5ef2ad feat(design-v4): port AppShell + Topbar + Breadcrumbs
9d2d816 feat(design-v4): vue port Icon component + icon registry
```
