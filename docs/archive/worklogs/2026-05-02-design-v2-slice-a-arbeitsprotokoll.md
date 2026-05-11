# Arbeitsprotokoll · 2026-05-02 · Design v2 Slice A — Foundation

**Slice:** A · Foundation (Tokens + Fonts + Theme-Toggle + Aurora-Background)
**Issue:** [#148](https://github.com/arn0ld87/agora/issues/148) (Refs [#147](https://github.com/arn0ld87/agora/issues/147))
**Branch:** `claude/design-v2-slice-a` → merge nach `main`
**Quelle:** Handoff-Bundle aus claude.ai/design (`Agora Design Language v2.html`, `agora-tokens-v2.css`)

## Ziel

Frontend von der bestehenden „Cartographic Notebook" (Dark-only, Fraunces, Mono+Neon-Orange+Plasma-Cyan) auf die 2026-Design-Language v2 umstellen — Foundation-Layer:

1. **Light + Dark Theme** (Light = Default), persistiert via `localStorage`, `data-theme` auf `<html>`, kein FOUC.
2. **oklch-Farbsystem** mit Aurora coral als primärer Akzent + Iris/Violet/Mint-Achse.
3. **Type-Stack** Instrument Serif / Inter Tight / JetBrains Mono.
4. **Aurora-Mesh-Background** + dezenter Filmkorn-Overlay.
5. **Legacy-Aliase erhalten**, damit Slice B/C kontrolliert nachziehen können (kein Big-Bang).

## Änderungen (Sub-Slice A1 — Tokens + Fonts)

### `frontend/src/assets/styles/tokens.css` (komplett ersetzt)

- Light-Theme als Default (`:root, [data-theme="light"]`), Dark-Theme als Override (`[data-theme="dark"]`).
- v2-Brand-Achse: `--brand-aurora`, `--brand-iris`, `--brand-mint`, `--brand-violet` in `oklch()`.
- Neutral-Skala `--ink-0..1000` per Theme separat definiert (Light = warm-cream Paper, Dark = blue-tinted Ink).
- Surfaces: `--bg`, `--bg-elevated`, `--bg-sunken`, `--bg-glass`, `--bg-glass-hi`, `--bg-panel`, `--bg-panel-2`, `--bg-inverse`.
- Mesh-Tokens: `--mesh-1..4` aus den Brand-Farben, `--mesh-alpha` themed (0.20 light / 0.28 dark).
- Akzent: `--accent` = Aurora coral, `--accent-soft`, `--accent-glow`, `--accent-ink` themed (light = white-on-aurora, dark = dark-on-aurora).
- Status: `--ok`/`--warn`/`--err` per Theme tonal angepasst (light: dunkler/saturierter, dark: heller).
- Shadow-Stack neu: `--shadow-1/2/3` mit Inset-Highlights, `--shadow-glass` als signature, `--shadow-popover`, `--shadow-modal`, `--shadow-editorial`, `--shadow-hairline`.
- Glow: `--glow-accent`, `--glow-info`, `--glow-plasma` (Alias auf `--glow-info` für Legacy-Compat).
- Type-Stack: `--ff-serif: 'Instrument Serif', …`; `--ff-sans: 'Inter Tight', …`; `--ff-mono: 'JetBrains Mono', …`.
- Type-Scale erweitert: `--fs-11..120` (zusätzlich zur bestehenden Skala) für die v2-Display-Sizes.
- Letter-Spacing: `--ls-tight`, `--ls-display`, `--ls-mono`, `--ls-mono-tight`, `--ls-mono-wide`, `--ls-caps`.
- Radien generös: `--r-1: 6px` … `--r-5: 28px` plus `--r-pill: 999px` (alt: `--r-1: 2px` — Slice B/C werden Komponenten an die größeren Radien führen).
- Controls: `--ctl-h-sm/md/lg` 30/38/48 px (alt: 28/36/44).
- **Legacy-Aliase erhalten** (Mapping → v2): `--mono-*` → `--ink-*` (Light invertiert!), `--neon-orange*` → `--accent`/`--accent-soft`/`--accent-ink`, `--plasma-*` → `--brand-iris` + Mischfarben, `--paper-*` → Surfaces, `--status-*` → `--ok/--warn/--err`, `--bg-page` → Aurora-tönender Background-Composite, `--bg-grid` → token-driven Grid-Lines.
- Base-Reset (`*, *::before, *::after`, `body`, `::selection`) mit v2-Family/-Smoothing/-Feature-Settings.
- Type-Roles `.t-display/.t-headline/.t-title/.t-subtitle/.t-body/.t-body-sm/.t-meta/.t-kicker/.t-numeral/.t-quote/.t-num` an v2 angepasst (Instrument Serif für Display, Inter Tight für Sans, JetBrains Mono für Kicker mit `--ls-mono-wide`).

### `frontend/index.html`

- Google-Fonts-`<link>` von **Fraunces + IBM Plex Sans + IBM Plex Mono** auf **Instrument Serif + Inter Tight + JetBrains Mono** umgestellt (Italic-Variante für Instrument Serif für `.t-quote` mitgeladen).
- Neues Pre-Paint-Inline-Script setzt `data-theme` aus `localStorage` (`agora-theme`) vor dem ersten Stylesheet-Apply — kein FOUC. Default-Fallback: `light`. Robustes `try/catch` falls `localStorage` blockiert ist.

### `frontend/src/assets/styles/fonts.css`

- Geist-`@font-face`-Blöcke entfernt (Geist-Variable-Files in `assets/fonts/` werden im aktuellen Stack nicht mehr referenziert; lokale Datei bleibt im Repo, kein Cleanup-Slice nötig).
- Datei bleibt als Import-Slot in `main.js` bestehen (Inhalt: Hinweiskommentar).

## Änderungen (Sub-Slice A2 — Theme-System + Aurora)

### `frontend/src/composables/useTheme.js` (neu)

- Singleton-`ref('light' | 'dark')`, einmaliger `watch` setzt `data-theme` und persistiert in `localStorage`.
- `useTheme()` gibt `{ theme, setTheme, toggle, options }` zurück.
- `readInitial()` priorisiert das aktuell gesetzte `data-theme`-Attribut (vom Pre-Paint-Script) vor `localStorage` — so bleibt SSR/Pre-Paint und Composable konsistent.
- Defensive `try/catch` um `localStorage`, fällt auf `'light'` zurück.

### `frontend/src/components/ui/ThemeToggle.vue` (neu)

- Pill-Switch mit zwei `<button>`s (Light/Dark), `role="group"`, `aria-pressed`, JetBrains-Mono-Caps-Labels.
- Eigene SVG-Icons (Sonne/Mond) — keine externen Icon-Pakete.
- Glass-Treatment per `var(--bg-glass)` + `backdrop-filter: blur(12px) saturate(160%)`, aktive Pille mit `--shadow-1`-Tactile-Hint.

### `frontend/src/components/ui/AuroraBackground.vue` (neu)

- Vier `<span>`-Blobs mit `radial-gradient`, `filter: blur(90px)`, `opacity: var(--mesh-alpha)`.
- Animation `aurora-float` 22s `ease-in-out infinite` mit gestaggerten `animation-delay`s (-9s/-4s/-13s) — Blob 1 mit 18s schneller.
- `pointer-events: none`, `z-index: 0` (Aurora) / `1` (Grain), beide `position: fixed; inset: 0`.
- `.grain` als SVG-`feTurbulence`-Data-URL mit `mix-blend-mode: multiply` (light) / `overlay` (dark, via `:global([data-theme="dark"])`).
- `prefers-reduced-motion: reduce` schaltet Float-Animation aus (Mesh bleibt sichtbar, aber statisch).

### `frontend/src/App.vue`

- `useTheme()` einmalig beim App-Setup aufgerufen → installiert den `watch` und apply-applied das Theme.
- `<AuroraBackground />` als erstes Element im Template, **vor** dem `<router-view>`.
- `#app { position: relative; z-index: 2 }` neu — Content-Layer steht garantiert über `.aurora` (z-0) und `.grain` (z-1).
- Scrollbar-Thumb bekommt `--r-pill` und nutzt `--fg-muted` statt `--fg` für den Hover (sanfter, oklch-konform).

## Validierung

```
npm run lint:backend    # ruff: All checks passed
npm run test:backend    # pytest: 744 passed, 9 skipped (Redis/Compose-Env wie üblich)
npm run lint:frontend   # eslint: 0 errors, 1 vorbestehender Warning (Step4Report.vue:2:49)
npm run test:frontend   # vitest: 9 files, 69 tests passed
npm run build:frontend  # vite build: 746 modules, 109 KB CSS / 523 KB JS gz, in 2.67s
```

`npm run check` als Aggregat = grün. Vorbestehender Lint-Warning unverändert (nicht in Slice-A-Scope).

## Akzeptanzkriterien (Issue #148)

- [x] `npm run check` grün
- [x] Theme persistiert in `localStorage` (`agora-theme`), Pre-Paint-Script verhindert FOUC
- [x] Bestehende Views rendern weiter (Legacy-Aliase wirken: alle `--mono-*`/`--neon-orange-*`/`--plasma-*`/`--paper-*`/`--status-*`/`--bg-page`/`--bg-grid` zeigen jetzt v2-Farben, ohne dass Komponentencode geändert werden musste)
- [x] Slice schließt Issue #148 ab (Closes-Trailer im PR)

## Risiken / Out-of-Scope

- **Visuelle Komponentenpolitur** (Buttons, Badges, Inputs, Stepper, Persona, Tables) ist bewusst **nicht** in Slice A — kommt in Slice B/C. Komponenten zeigen jetzt v2-Farben aber alte Geometrien (2-px-Radien, alte Shadows).
- **`StickyScrollBanner`/`Step4Report.vue`/`Step3Simulation.vue`** lesen Tokens via Klassen — keine direkten Hex-Werte. Visueller Regress unwahrscheinlich; manuelle Sichtkontrolle in Slice B beim Komponenten-Update.
- **Geist-Font-Files** (`frontend/src/assets/fonts/GeistSans-Variable.woff2`, `GeistMono-Variable.woff2`) liegen ungenutzt im Repo. Nicht entfernt, weil kein zwingender Grund (Disk-Cost minimal); kann ein eigener Cleanup-Slice werden.
- **`AGORA_THEME`-Env oder Server-Render** wurde nicht eingebaut. Theme ist client-only.

## Nächster Slice

[#149](https://github.com/arn0ld87/agora/issues/149) — Slice B: UI-Primitives (Btn/Badge/Card/Field/Select/Hairline/StickyScrollBanner) und WorkspaceHeader mit ThemeToggle.
