# Frontend-Redesign — shadcn-Feel auf v4-Tokens

**Datum:** 2026-05-15
**Branch-Konvention:** `feat/fe-redesign-<slice>`
**Integration-Branch:** `feat/fe-redesign-epic` (analog Design-v4-Epic)
**Status:** Spec — implementation pending User-Sign-off

## Problemzusammenfassung

Drei zusammenhängende Schmerzpunkte am Frontend:

1. **Inkonsistente Menüs.** v4-Komponenten sind portiert, aber Sidebar/Topbar/Dropdown haben kein einheitliches State-Vokabular (Hover/Focus/Active/Disabled-Behandlung uneinheitlich, keine Token-Coverage-Garantie).
2. **Multi-Level-Navigation hält Kontext nicht.** `Sidebar.vue` rendert Groups, aber kein persistenter Expand/Collapse-State, keine `$route.matched`-Active-Trail-Detection, kein Breadcrumb-Auto-Aus-Route. User verliert beim Tieftauchen (z. B. `/settings/llm-routing` oder `/v4/simulation/:id`) den Pfad nach oben.
3. **Simulation fühlt sich nicht "lebendig" an.** `SimulationView`/`StepSimulationView` zeigen eine Single-Column-Pipeline-Ansicht. Die OASIS-Diskussion läuft real auf zwei unterschiedlichen Kanal-Mustern (threaded vs. flat), wird aber als monolithischer Log gerendert. Der "Feel"-Effekt fehlt.

## Nicht-Ziele

- **Kein** Wechsel zu Tailwind oder shadcn-vue als Build-Time-Dependency. Das laufende Design-v4-Epic bleibt Single Source of Truth für Visual-Layer und Token-System.
- **Kein** Backend-Touch. Daten kommen aus existierenden SSE-Streams (`useEventStream`), Persona-Quoten-API, Report-Endpoint.
- **Keine** vollständige Migration aller Legacy-Step-Views. Legacy `SimulationView.vue` und `Step2EnvSetup.vue` bleiben unter `/simulation/:id` und `/process/:projectId` erreichbar; v4-Pfade unter `/v4/*` werden Standard.

## Architektur-Entscheidung

**reka-ui** (headless, ARIA-vollständig, ~30 kB gz) wird als Primitives-Layer eingezogen. v4-Komponenten wrappen reka-ui-Primitives und liefern Visual-Layer aus `tokens-v3.css`. Damit erbt v4 die a11y-Härte von shadcn-vue **ohne** Tailwind oder Component-Copy-Maintenance.

Reka-ui-Primitives in Scope:

- `NavigationMenu` → Topbar Section-Switcher
- `DropdownMenu` → existierendes `v4/forms/DropdownMenu.vue` upgraden (aktuell Eigenbau, fehlende Roving-Tabindex/Escape-Handling)
- `Collapsible` → Sidebar-Groups expand/collapse
- `Tabs` → `v4/data/Tabs.vue` upgraden
- `Dialog` → `v4/data/Dialog.vue` upgraden (Focus-Trap, Escape, Scroll-Lock)
- `Tooltip` → neu
- `Command` (combobox-basiert) → Cmd+K-Spotlight

Visual-Layer: bestehende `tokens-v3.css`. **Kein** zweites Token-System.

## Slices

Sechs Slices, parallel-fähig auf disjunkten Pfaden, einer Integration-PR am Ende.

### Slice 1 — Reka-UI-Fundament + DropdownMenu-Upgrade

**Scope:** `frontend/package.json`, `frontend/src/components/v4/forms/DropdownMenu.vue`, `DropdownMenuItem.vue`, `__tests__/DropdownMenu.spec.ts`.

- `reka-ui` als dependency installieren (~30 kB gz).
- `DropdownMenu.vue` als Wrapper um reka-ui `DropdownMenuRoot/Trigger/Content/Item` neu schreiben. Public API (`open`, `placement`, slot `trigger`/default) bleibt erhalten — Drop-in-Replacement.
- Token-Coverage-Test: alle Visual-States (rest/hover/focus-visible/active/disabled) via `getComputedStyle` gegen v4-Tokens prüfen.

**Verifikation:** Bestehende Consumer (`Topbar.vue`, `LlmProfileManager.vue`, `ModelPicker.vue`) typecheck/build/test grün ohne Anpassung.

### Slice 2 — Multi-Level-Sidebar mit Persistenz

**Scope:** `v4/shell/Sidebar.vue`, `SidebarGroup.vue`, `SidebarItem.vue`, neue `composables/useSidebarState.ts`, `Breadcrumbs.vue`.

- `SidebarGroup` rendert reka-ui `Collapsible` mit `defaultOpen`-Heuristik: offen, wenn ein Child in `$route.matched`.
- `useSidebarState` persistiert Expand/Collapse pro Group-Key in `localStorage` (Key `agora.sidebar.v1`).
- Active-Trail: `SidebarItem` setzt `aria-current="page"` wenn `$route.matched.some(r => r.name === item.routeName)`.
- `Breadcrumbs.vue` leitet Trail aus `$route.matched` ab statt Props (Fallback auf explizite Props bleibt). Trail-Items mit i18n-Key-Konvention `nav.<routeName>`.
- Optional: Sidebar collapsed-Modus (Icon-only) mit Tooltip-Hover (Slice 4-Vorgriff, behind `enableCollapsedSidebar` Feature-Flag).

**Verifikation:** Smoke-Test navigiert `/dashboard → /settings/llm-routing → /v4/simulation/:id`, prüft dass:
- erwartete Groups expanded sind
- aktiver Item `aria-current="page"` trägt
- Breadcrumbs Pfad widerspiegeln

### Slice 3 — Komponenten-Konsistenz-Audit + State-Vokabular

**Scope:** `v4/forms/*`, `v4/data/*`, neue `frontend/src/assets/styles/states.css`.

- Audit aller v4-Komponenten gegen einheitliches State-Vokabular:
  - `--v4-state-rest-bg/border/fg`
  - `--v4-state-hover-bg/border/fg`
  - `--v4-state-focus-ring`
  - `--v4-state-active-bg/border/fg`
  - `--v4-state-disabled-bg/border/fg/opacity`
- `states.css` definiert Mixin-Klassen `.v4-state-interactive`, `.v4-state-selectable`. Bestehende Komponenten konsumieren statt eigene Hover/Focus-Regeln zu schreiben.
- Focus-Ring uniformisieren: 2 px Solid in `--v4-color-accent`, 2 px Offset, `prefers-reduced-motion`-aware.
- Audit-Report als `docs/2026-05-15-v4-state-audit.md` (Diff-Liste, welcher Component welchen Token-Pfad nutzte).

**Verifikation:** Vitest-Snapshot pro Component-Family — alle interaktiven States renderbar, computed-styles matchen Token-Werte.

### Slice 4 — Command-Palette (Cmd+K)

**Scope:** neue `v4/shell/CommandPalette.vue`, `composables/useCommandPalette.ts`, Integration in `AppShell.vue`.

- reka-ui `DialogRoot` + `Command` (combobox-basiert).
- Datenquelle: Pinia-Store `useCommandsStore` mit statischen Nav-Commands (jede Route) + dynamische Commands (offene Simulationen aus `useRunsStore`, kürzliche Reports).
- Trigger: `Cmd+K` / `Ctrl+K` (Mac/Win), Topbar-Search-Icon-Click.
- Recent-Commands in localStorage (`agora.cmdk.recent`).

**Verifikation:** Keyboard-only-Flow: `Cmd+K → "rep" → ↓↓ → Enter` navigiert zu Report. a11y-Smoke: Focus-Trap, ARIA-combobox-Rolle, Escape schließt.

### Slice 5 — Simulation Dual-Feed-View (Reddit + Twitter)

**Scope:** neue `views/v4/steps/StepSimulationFeedView.vue`, neue Komponenten unter `v4/sim-feed/`:

- `FeedColumn.vue` — generischer Column-Container mit Header (Channel-Name, Live-Indicator, Filter)
- `RedditPost.vue` — threaded, mit Voting-Visualisierung, Comment-Tree
- `RedditThread.vue` — rekursiver Reply-Tree (max-depth 4 visuell, deeper als "show more")
- `TwitterPost.vue` — flat, Avatar+Handle+Body+Reactions
- `PersonaAvatar.vue` — Initialen-Avatar mit voice_register-Badge (formal/casual/jugendsprache)
- `SimulationPulseBar.vue` — Sentiment-Heatbar (last-N-window) + Activity-Counter
- Router-Eintrag `/v4/simulation/:simulationId/feed` zusätzlich zu existierendem `/v4/simulation/:simulationId`. Tab-Switch im StepSimulation-Header zwischen "Pipeline" und "Feed".

**Datenquelle:**
- Existierender SSE-Stream über `useEventStream`.
- Mapping: Events mit `channel === "reddit"` → linke Column, `channel === "twitter"` → rechte Column. Threading aus `parent_post_id` (Reddit) bzw. flacher Append (Twitter).
- Neue Posts: `<TransitionGroup>` mit slide-down + fade-in (200 ms), `prefers-reduced-motion` respektiert.
- Auto-Scroll: per Default an, sichtbarer "Pause"-Pin bei manuellem Scroll (Pattern aus Slack/Discord).
- Sim-Badge bei `is_simulated: true` (Wording-Glossar v1 — kein "prediction").

**Pulse-Bar:**
- Letzte 30 Posts Sentiment-Avg als horizontale Heatbar (rot→grau→grün).
- Activity-Counter (Posts/min, exponential moving average).

**Verifikation:**
- Vitest mit Mock-SSE-Stream: 50 Posts, Threading prüfen, Sortierung, Sim-Badge.
- Playwright-Smoke (M11.4-Erweiterung): Feed-View lädt, SSE-Mock liefert Posts, beide Columns füllen sich, Cmd+K findet "Simulation Feed".
- a11y: `role="feed"` pro Column, `aria-busy` während Loading, jeder Post `role="article"`.

### Slice 6 — Density-Toggle + Polish

**Scope:** `tokens-v3.css` (Density-Custom-Properties), `AppShell.vue` (Toggle in Topbar), `useDensity.ts`.

- Density-Modi: `comfortable` (Default), `compact` (–25 % vertical padding, –1 px font-size für Body-Text).
- Implementierung via CSS-Custom-Property-Override auf `<html data-density="compact">`.
- Persistenz in localStorage (`agora.density`).
- Affects: Sidebar-Items, Topbar, Data-Tables, Step-Headers. Nicht: Buttons (touch-target bleibt 40 px).

**Verifikation:** Vitest snapshot in beiden Density-Modi für Sidebar+Topbar+DataTable.

## Rollout-Strategie

Analog Design-v4-Epic:

1. Lokale Slices 1–6 auf `feat/fe-redesign-<n>` in `/private/tmp/agora-fe-redesign-<n>` Worktrees.
2. Disjunkte Verzeichnis-Scopes — parallel-fähig:
   - Slice 1: `v4/forms/Dropdown*`
   - Slice 2: `v4/shell/Sidebar*` + `Breadcrumbs.vue` + `composables/useSidebarState.ts`
   - Slice 3: `v4/forms/*` + `v4/data/*` + `assets/styles/states.css`
   - Slice 4: `v4/shell/CommandPalette*` + Cmd-Store
   - Slice 5: neuer Namespace `v4/sim-feed/` + neuer View
   - Slice 6: `tokens-v3.css` + Density-Composable
3. Integration-Branch `feat/fe-redesign-epic` mergt mit `--no-ff`.
4. Lokale Gates pro Slice + auf Integration: `bun run typecheck && bun run test:coverage && bun run build && bun run lint`.
5. EIN PR (`feat/fe-redesign-epic` → main) mit allen Slices.
6. Gemini-Findings-Sichtung nach 90 s (Pflicht-Workflow).

**Reihenfolge der Slice-Implementierung** (innerhalb des Epics):

```
Slice 1 (Reka-Fundament) ──┬──> Slice 2 (Sidebar)
                            ├──> Slice 3 (State-Vokabular)
                            ├──> Slice 4 (Command-Palette)
                            └──> Slice 5 (Sim-Feed)
                                  └──> Slice 6 (Density)
```

Slice 1 ist Voraussetzung für 2/3/4. Slice 5 ist orthogonal und kann parallel zu 2/3/4 laufen. Slice 6 zum Schluss als Polish.

## Risiken

| Risiko | Wahrscheinlichkeit | Gegenmaßnahme |
|---|---|---|
| reka-ui-API ändert sich (Pre-1.0) | mittel | Wrapper-Pattern isoliert Konsumenten; lockfile-pin auf Minor |
| Bundle-Größe wächst > 50 kB gz | niedrig | reka-ui ist tree-shaken; Bundle-Analyzer-Snapshot pro Slice |
| Sim-Feed-SSE-Mock divergiert von Prod-Stream | hoch | Schema-Contract gemeinsam mit Backend pflegen (siehe Layer-0-Regel im Repo) — Zod-Validation pro Event |
| Multi-Level-Sidebar-Layout bricht auf < 1280 px | mittel | Responsive-Smoke + mobile-Sidebar als Slide-Over (reka-ui Dialog) im Slice 2 mit drin |
| Density-Toggle bricht Step-Wizards | mittel | Density nur auf Shell-Chrome (Sidebar/Topbar/Tables), nicht auf Step-Content |

## Out-of-Scope für dieses Epic

- Backend-Schema-Erweiterungen für Sim-Feed-Metadaten (z. B. `parent_post_id`, `channel` als Pflichtfeld). Wird, falls nötig, separater Pydantic-Contracts-Slice.
- Dark-Mode-Toggle. v4-Tokens unterstützen es bereits — UI-Toggle kommt nach Density.
- Mobile-Sidebar-Slide-Over über die Smoke hinaus. Echtes Mobile-Layout = eigenes Epic.
- Animation-Polish im Sim-Feed über die spezifizierten 200 ms-Fade-In hinaus.

## Erfolgskriterien

- Visual-Akzeptanz: side-by-side Vergleich gegen aktuelles `/v4/dashboard`/`/v4/simulation/:id` zeigt einheitliche State-Behandlung (Slice 3 Audit-Report ist die Belegquelle).
- Funktional: Cmd+K findet jede Route in < 3 Tasten. Sidebar-State überlebt Reload. Sim-Feed zeigt mind. 50 simultane Posts ohne Layout-Sprung.
- a11y: alle interaktiven Komponenten Tastatur-bedienbar, Focus-Ring sichtbar, ARIA-Rollen korrekt (`Lighthouse` ≥ 95 für a11y auf `/dashboard` und `/v4/simulation/:id/feed`).
- Bundle: Δ gz ≤ +50 kB gegen `main`-Baseline.
- Test-Delta: keine Regression in bestehenden 24 %+ Frontend-Coverage; neue Slice-Tests heben Coverage auf ≥ 30 %.

## Offene Fragen für vor Implementierungsstart

1. **Sim-Feed-Daten**: liefert der existierende SSE-Stream bereits `channel`/`parent_post_id`-Felder, oder muss vorgelagert ein Backend-Slice die Felder ergänzen? → vor Slice 5 prüfen via `backend/app/api/simulation.py` + `useEventStream`-Konsumenten.
2. **Cmd+K-Scope**: Reicht statische Route-Liste, oder soll Spotlight auch Persona-Suche + Report-Inhalt durchsuchen? → Empfehlung: Slice 4 nur statisch + Recent, semantische Suche wäre eigener Slice.
3. **Density-Toggle**: User-Setting persistent in localStorage reicht, oder pro-Workspace im Backend speichern? → Empfehlung: localStorage, kein Backend-Touch.
