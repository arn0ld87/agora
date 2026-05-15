# Agora Design Language v4 — Real State (Stand 2026-05-15)

Diese Doku beschreibt die **tatsächlich im Code vorhandene** Design Language v4, nicht den
aspirational Zustand aus älteren Specs. Quelle: `frontend/src/` auf `origin/main` @ `de933b9`.

Ergänzt das laufende Design-v4-Epic-Dokument [`docu/2026-05-11-design-v4-app-shell-epic.md`](../2026-05-11-design-v4-app-shell-epic.md).

## Ziel

Agora ist ein technisches Analyse- und Simulations-Frontend. UI-Ziel: ruhig, klar,
datenorientiert. Optisch orientiert an Apple-System-Tokens (Light-Mode-Primary,
Dark-Mode vorbereitet via `[data-theme]`).

## Grundprinzipien

- **Keine Fremd-Component-Bibliothek**. Agora baut eigene Komponenten direkt auf
  Vue 3 + Composition API + scoped `<style>` + CSS-Custom-Properties.
- **Tokens-first**: Layout, Farbe, Typo, Radius, Shadow kommen über CSS-Variablen
  aus `assets/styles/tokens-v3.css`. Keine Tailwind-Utility-Klassen,
  kein Sass, kein CSS-in-JS.
- **TypeScript-Generics für Datenkomponenten**: `DataTable<TRow>` ist generisch
  typisiert, Slot-Props sind typesafe.
- **Slot-driven Composition**: Komponenten wie `AppShell`, `DataTable`,
  `EmptyState` nutzen named Slots statt verschachtelter Props.
- **Compat-Layer**: `tokens-v3.css` exportiert v1/v2-Aliase parallel zu den
  v4-Tokens, damit Legacy-Komponenten in `components/ui/` weiter funktionieren,
  bis Cleanup-Slice J (Design-v4-Epic) sie ersetzt.

## Stack-Realität

| Schicht | Technologie | Version |
|---|---|---|
| Runtime | Bun | 1.3.14 |
| Framework | Vue 3 | 3.5.34 |
| Build | Vite | 8.0.13 |
| State | Pinia | 3.0.4 |
| Router | Vue Router | 5.0.6 |
| Validation | Zod | 4.4.3 |
| HTTP | Axios | 1.16.0 |
| Charts | D3 | 7.9.0 |
| Markdown | marked + DOMPurify | 18 / 3.4.2 |
| i18n | vue-i18n | 11.4.2 |
| Tests | Vitest | 4.1.5 |
| E2E | Playwright | 1.49 |
| Lint | ESLint | 10.3.0 |
| Typecheck | vue-tsc | 3.2.8 |

**Nicht installiert** (bewusst): Tailwind CSS, shadcn-vue, daisyUI, TanStack Table,
Unovis, lucide-vue. Begründung siehe [`shadcn-vue-evaluation.md`](./shadcn-vue-evaluation.md).

## Layout-Architektur

`AppShell` ist CSS-Grid-basiert:

```
┌──────────┬────────────────────────────┬─────────────┐
│          │ Topbar (64px)              │             │
│ Sidebar  ├────────────────────────────┤  Inspector  │
│ (auto)   │                            │  (360px,    │
│          │ Main (padding 28×36)       │   optional) │
│          │                            │             │
└──────────┴────────────────────────────┴─────────────┘
```

Datei: [`frontend/src/components/v4/shell/AppShell.vue`](../../frontend/src/components/v4/shell/AppShell.vue)

- Grid mit `grid-template-columns: auto 1fr` (Inspector hängt 360px rechts an).
- Sidebar überspannt beide Zeilen, Topbar nur Zeile 1, Main scrollt unabhängig.
- Sidebar-Collapse, Inspector-Toggle und Settings-Group-Open werden in
  `useShellStore()` (Pinia) gehalten — globaler UI-State statt Prop-Drilling.
- Route-Highlighting in der Sidebar wird via `useRoute()` + `computed` abgeleitet.

## Komponenten-Namespaces

```
frontend/src/components/
├── ui/           ← Legacy v3/early-v4 Bausteine (11 Komponenten)
├── v4/           ← Aktuelles Design Language v4 (27 Komponenten)
│   ├── shell/    ← AppShell, Sidebar, Topbar, Breadcrumbs, PageHeader, Icon
│   ├── forms/    ← Field, Input, Select, Pill, SegmentedControl, ProviderCard, …
│   ├── data/     ← DataTable, EmptyState, Tabs
│   ├── dashboard/← StatsRow, HeroNewRun, ActiveRunsCard, RecentReportsCard, …
│   └── steps/    ← PipelineStepper
├── compare/      ← Run-Compare-Spezialkomponenten
├── graph/        ← Neo4j-Graph-Visualisierung (D3)
├── icons/        ← SVG-Icon-Registry
├── step2/, step4/← Step-spezifische Sub-Komponenten
├── LlmRouting/   ← LLM-Routing-Settings-Panel
└── (Top-Level: ActiveModelBadge, AppFooter, GraphPanel, HistoryDatabase,
               LogDrawer, RunsDashboard, Step1…5*.vue)
```

Faustregel:
- **`components/v4/`** ist die Ziel-Architektur. Alle neuen Komponenten dort.
- **`components/ui/`** wird durch Cleanup-Slice J abgebaut. Keine neuen Komponenten dort.
- **`components/<step>/`** + Top-Level-Step-Files sind die View-Container, die
  v4-Bausteine zusammensetzen.

## CSS-Architektur

Drei Globals, geladen in dieser Reihenfolge in `main.ts`:

1. **`assets/styles/fonts.css`** — `@font-face` für Geist Sans + Geist Mono Variable.
2. **`assets/styles/tokens-v3.css`** (430 LOC) — Design-Tokens als CSS-Variablen,
   Light- + Dark-Theme-Definitionen über `:root, [data-theme="light"]` bzw.
   `[data-theme="dark"]`, plus v1/v2-Aliase im Compat-Layer.
3. **`assets/styles/global.css`** (1180 LOC) — Reset, Typo-Basis, Utility-Klassen.

Theme-Switch passiert via `document.documentElement.setAttribute('data-theme', '…')`.
Pro Komponente: `<style scoped>` mit `var(--token-name, fallback)`.

### Tokens-Kategorien (Auszug aus tokens-v3.css)

- **Surfaces**: `--surface-base`, `--surface-canvas`, `--surface-elevated`,
  `--surface-translucent`, `--surface-tint`, `--surface-inset`,
  `--surface-hover`, `--surface-pressed`.
- **Hairlines**: `--hairline`, `--hairline-strong`, `--separator`, `--focus-ring`.
- **Text**: `--text-primary`, `--text-secondary`, `--text-tertiary`,
  `--text-quaternary`, `--text-on-accent`.
- **Accent**: `--accent` (Apple-Enterprise-Blue `#0066cc`), `--accent-hover`,
  `--accent-pressed`, `--accent-tint-bg`, `--accent-tint-text`.
- **Status**: `--status-green`, `--status-orange`, `--status-red`,
  `--status-purple` plus jeweils `-bg`-Varianten.
- **Spacing**: `--sp-1` … `--sp-12` (4px-Raster).
- **Radius**: `--r-1` … `--r-7`.
- **Shadows**: `--shadow-1` … `--shadow-3`, `--shadow-glass`.
- **Typo**: `--font-sans` (Geist Sans), `--font-mono` (Geist Mono),
  `--fs-caption-1`, `--fs-body`, `--fs-title-1` etc.

## Qualitätsregeln (gelebt, nicht aspirational)

- Jede neue v4-Komponente: scoped Styles, Tokens, kein Inline-CSS.
- Datenkomponenten: TypeScript-Generics (siehe `DataTable<TRow>`).
- Containerkomponenten: named Slots statt verschachtelter Props.
- i18n: alle User-facing Strings in `i18n/de.json` + `i18n/en.json`,
  niemals hartkodiert (siehe Top-Level-CLAUDE.md "Verboten"-Liste).
- A11y: `aria-hidden` für dekorative SVGs, `aria-label` für Icon-Only-Buttons.
- Tests: pro v4-Komponente mindestens ein Smoke-Test in
  `frontend/src/components/v4/<subdir>/__tests__/`.

## Bewusste Nicht-Entscheidungen

- **Kein Tailwind**: würde Tokens-System duplizieren, Build verlängern, Custom-CSS
  unsichtbarer machen. Tokens-CSS deckt 100 % des aktuellen Bedarfs.
- **Kein shadcn-vue**: würde mit existierendem `components/ui/`-Namespace
  kollidieren und Komponenten neu bauen, die in `components/v4/` bereits in
  ähnlicher Qualität existieren (DataTable, EmptyState, ProviderCard, …).
- **Kein Sass/LESS**: CSS-Custom-Properties + scoped Styles reichen.
- **Kein Storybook**: design/v3-Showcase wird per `vite.config.js`-Middleware unter
  `/design/v3/` ausgeliefert (siehe Configure-Server-Plugin in `vite.config.js`).

## Referenzen

- Epic-Doku: [`docu/2026-05-11-design-v4-app-shell-epic.md`](../2026-05-11-design-v4-app-shell-epic.md)
- Source-of-Truth-Designs: [`design/v3-source/`](../../design/v3-source/)
- Showcase live: `bun run dev` → `http://localhost:5173/design/v3/`
- Component-Audit: [`component-audit.md`](./component-audit.md)
- UI-Regeln: [`ui-rules.md`](./ui-rules.md)
- shadcn-vue-Begründung: [`shadcn-vue-evaluation.md`](./shadcn-vue-evaluation.md)
