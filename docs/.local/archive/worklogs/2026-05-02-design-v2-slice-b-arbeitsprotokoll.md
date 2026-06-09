# Arbeitsprotokoll · 2026-05-02 · Design v2 Slice B — Visual Language

**Slice:** B · UI-Primitives + Workspace-Header
**Issue:** [#149](https://github.com/arn0ld87/agora/issues/149) (Refs [#147](https://github.com/arn0ld87/agora/issues/147), Folge zu [#148](https://github.com/arn0ld87/agora/issues/148))
**Branch:** `claude/design-v2-slice-b` → merge nach `main`

## Ziel

Die in Slice A eingeführten v2-Tokens, Aurora-Mesh und das Theme-System auf die zentralen UI-Primitives anwenden — Komponenten, die heute noch alte Geometrien (2-px-Radien, harte Borders, kein Backdrop-Blur) zeigten, kriegen das pill-shaped, tactile, glass-getönte v2-Vokabular. Außerdem: ThemeToggle in den Workspace-Header bringen.

## Änderungen

### `frontend/src/assets/styles/global.css` (zentrale Klassen)

**Buttons — `.btn`-Block komplett neu**
- `border-radius: var(--r-pill)` (vorher `--r-1`).
- `cubic-bezier(.2,.8,.2,1)`-Hover mit `translateY(-1px)`/`translateY(0)`-Press.
- `--primary`: solider Foreground-Background (ink-on-paper / paper-on-ink), tactile Shadow-Stack (Inset-Highlight, Drop-Shadow, kleine Subtle-Shadow).
- `--accent`: Aurora-`linear-gradient` mit `--accent-glow` als Drop-Shadow (`0 8px 24px -6px var(--accent-glow)`), Hover stärkt Glow.
- `--info` / `--plasma` (Alias): Iris-`linear-gradient` mit eigenem Glow.
- `--glass`: `var(--bg-glass)` + `backdrop-filter: blur(20px) saturate(160%)`.
- `--secondary`: Outline mit Glass-Backing, sanfter Border-Hover.
- `--ghost`: borderless bis Hover (Glass-Pop).
- `--danger`: Error-Soft als Default, Hover füllt mit Error-Solid.
- `.btn-split`: pill-radius, glass-container.

**Badges — `.badge`-Block neu**
- 24 px statt 22 px Höhe, `letter-spacing: var(--ls-mono)` (statt `--ls-mono-tight`).
- Default: `var(--bg-glass)` + `backdrop-filter: blur(12px)`.
- `--accent`/`--plasma`/`--info`/`--success`/`--warn`/`--error`: oklch-Soft-Backgrounds (`var(--*-soft)`) mit `color-mix`-Borders.
- `.badge--live`: Pulse-Animation 1.4 s `ease-in-out infinite` (Opacity 1↔0.35).
- `.tag`: pill-radius (statt `--r-1`), Glass-Backing.

**Inputs — `.input`/`.select-trigger`/`.textarea`**
- `border-radius: var(--r-pill)` (Textarea bleibt `--r-3` wegen Multi-Line).
- Focus: `border-color: var(--accent)` + `box-shadow: 0 0 0 4px var(--accent-soft)` als Accent-Glow-Ring.
- Hover: `color-mix(in oklch, var(--fg) 30%, transparent)` Border.
- `.input--bare` bleibt Underline (Backwards-Compat für alte Forms, kein `box-shadow`).
- `.input-group`: pill-radius mit `overflow: hidden` für saubere Pfx/Sfx-Kombi.

**Tabs / Segmented — Pill-Segmented**
- `.tabs`: Glass-Container mit `padding: 4px`, pill-radius, `gap: 4px`.
- `.tab`: kein Underline mehr, aktive Tab kriegt `--bg-elevated` + `--shadow-1` (lifted-pill).
- `.segmented`: Glass-Container, `.seg.is-active` ebenfalls lifted-pill.

**Panel**
- `border-radius: var(--r-3)` (statt `--r-1`), `--shadow-1` für tactile Tiefe.
- `.panel--glass`: `var(--bg-glass)` + `backdrop-filter: blur(24px) saturate(160%)`, `--shadow-glass`.

**Switch**
- 44×26 px (statt 36×20), 20×20 px Thumb (statt 14×14), weiß mit Inset-Highlight.
- Cubic-bezier-Bounce (`.2,.9,.3,1.2`) auf `transform`.

### UI-Atome

- [`Card.vue`](../frontend/src/components/ui/Card.vue): neue `glass`-Prop (`Boolean`). `.card` selbst hat jetzt `--r-3` + Border + `--shadow-1`. `.card--glass` schaltet auf `var(--bg-glass)` + Backdrop-Blur + `--shadow-glass`. Card-Label nutzt `--ls-mono-wide` für die v2-Mono-Caps-Optik.
- [`Field.vue`](../frontend/src/components/ui/Field.vue): von Bare-Underline auf v2-Pill-Input migriert. Label-Letter-Spacing auf `--ls-mono-wide`. Accent-Glow-Focus-Ring.
- [`Select.vue`](../frontend/src/components/ui/Select.vue): pill-Select, Caret-Position auf `right: 16px` für die größere Padding-Right-Zone (`padding: 0 36px 0 var(--ctl-pad-x)`).
- [`StickyScrollBanner.vue`](../frontend/src/components/ui/StickyScrollBanner.vue): von flat-accent zu Aurora-`linear-gradient` mit `--accent-glow`-Drop-Shadow und Inset-Highlight; Hover liftet `translateY(-2px)` und stärkt den Glow.

### Workspace-Header

- [`WorkspaceHeader.vue`](../frontend/src/layouts/WorkspaceHeader.vue): importiert und mountet `<ThemeToggle>` rechts neben dem `status`-Slot. Header bekommt `background: var(--bg-glass)` + `backdrop-filter: blur(20px) saturate(160%)` (vorher solider `var(--bg)`), sodass das Aurora-Mesh aus Slice A unter dem Header durchscheint. Padding auf `var(--s-3) var(--s-6)` (vorher `var(--s-4) var(--s-6)`) — passt zur kompakteren v2-Höhe.

## Validierung

```
npm run lint:backend    # ruff: All checks passed
npm run test:backend    # pytest: 756 passed, 9 skipped
npm run lint:frontend   # eslint: 0 errors, 1 vorbestehender Warning (Step4Report.vue:2:49)
npm run test:frontend   # vitest: 9 files, 69 tests passed
npm run build:frontend  # vite build: 116 KB CSS / 528 KB JS gz, in 2.61s
```

`npm run check`-Aggregat = grün.

## Akzeptanzkriterien (Issue #149)

- [x] `npm run check` grün
- [x] Buttons / Badges / Inputs / Tabs / Sticky-Banner sichtbar v2-konform in Light + Dark (zentrale Klassen sind themed-token-driven, kein Hex-Lock)
- [x] ThemeToggle im Workspace-Header funktioniert (mounted via `WorkspaceHeader.vue`)
- [x] Backwards-compat: `.btn--secondary`/`.btn--plasma`/`.btn--danger`/`.input--bare` bleiben für bestehende Konsumenten erhalten

## Risiken / Out-of-Scope

- **Stepper**, **Persona-Cards**, **Tabellen**, **Log-Block**, **KPI** sind bewusst nicht in Slice B — kommen in Slice C.
- **Marketing-Nav** (`.nav` aus `global.css`) bleibt unangetastet (alt-stil); Home-View benutzt sie und ein zweiter Pass auf Marketing-Surfaces ist in Slice C optional.
- **Brand-Glyph** (`AgoraGlyph.vue`) bleibt unverändert; v2-HTML hat einen Gradient-Glyph (Aurora→Violet) — könnte in Slice C kommen, ist aber nicht im Akzeptanz-Set.
- **Step3-/Step4-Component-spezifische Surfaces** (Live-Feed, Console-Pane, Tool-Panel, Persona-Review-Cards) tragen Klassen aus `global.css` und erben automatisch den neuen Look; Custom-Markup wird in Slice C feinjustiert.
- **Bestehender Lint-Warning** in [`Step4Report.vue:2:49`](../frontend/src/components/Step4Report.vue) (`'nextTick' is defined but never used`) ist nicht in Slice-B-Scope.

## Nächster Slice

[#150](https://github.com/arn0ld87/agora/issues/150) — Slice C: Surfaces (Stepper, Persona, Tabellen, Log-Block, KPI).
