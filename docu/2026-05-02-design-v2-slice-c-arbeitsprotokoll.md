# Arbeitsprotokoll · 2026-05-02 · Design v2 Slice C — Surfaces

**Slice:** C · Stepper, Persona, Tabellen, Log, KPI, Toast, Popover, Kbd, Marketing-Nav
**Issue:** [#150](https://github.com/arn0ld87/agora/issues/150) (Refs [#147](https://github.com/arn0ld87/agora/issues/147), Folge zu [#148](https://github.com/arn0ld87/agora/issues/148)/[#149](https://github.com/arn0ld87/agora/issues/149))
**Branch:** `claude/design-v2-slice-c` → merge nach `main`

## Ziel

Surface-Polish, sodass die noch nicht v2-konformen Surfaces mit dem in Slice A/B etablierten Vokabular gleichziehen — Stepper, Persona-Cards, Tabellen, Log-Block, KPI, Toast/Popover/Tooltip/Kbd und Marketing-Nav.

## Änderungen

Alle Änderungen in [`frontend/src/assets/styles/global.css`](../frontend/src/assets/styles/global.css):

### Stepper (`.stepper` / `.ws-stepper`)
- Container-Background von `var(--mono-950)` auf `var(--bg-glass)` + `backdrop-filter: blur(12px) saturate(160%)` gehoben.
- Step-Padding 14 → 16 px.
- Active-State: `var(--accent-soft)` (vorher `--mono-900`), Hover auf `var(--bg-glass-hi)`.
- Active-Bottom-Bar: 2-px-`--accent` *ohne* `--glow-accent`-Outer-Glow (war zu laut, das v2-HTML nutzt nur die flache Bar).
- `.head` und `.head .n` auf `--ls-mono-wide`/`--ls-display` gemäß v2-Type-Roles; `.head .n` von `font-weight: 300` auf `400` (Instrument Serif hat keinen 300-Cut).
- `is-done` Status auf `--ok` (vorher `--status-success`-Alias).
- Legacy `.stepper .step.active`-Klassen ebenfalls migriert (alte Konsumenten).

### Persona-Cards (`.persona`)
- Hover-Background auf `var(--bg-glass)`, sanfte `transition` (200 ms cubic-bezier).
- Avatar: 56×56 mit `border-radius: 50%` (vorher quadratisch), `linear-gradient(135deg, var(--brand-iris), var(--brand-violet))` als Default, Inset-Highlight + Shadow-Drop.
- Avatar-Varianten: `is-aurora` (Aurora→Violet), `is-mint` (Mint→Iris mit dunklem Text), `is-violet` (Violet→Aurora).
- Active-Ring: `border: 2px solid var(--accent)` + `box-shadow: 0 0 0 4px var(--accent-soft)` (vorher 1-px-Ring ohne Glow).
- `.meta-line`: `text-transform: uppercase` + `--ls-mono-wide` für die v2-Caps-Optik.
- Neue `.traits .tag`: pill-shaped, glass-backed.
- `is-approved`/`is-flagged`: `linear-gradient(180deg, var(--ok-soft|--warn-soft), transparent 30%)` als Background plus `color-mix`-Border-Color für die Outer-Hairline.
- **Neu**: `.stance-bar` / `.stance-track` / `.stance-fill` (3-Spalten-Grid mit Iris→Aurora-Gradient-Fill) für Polarization-Indikatoren — wartet auf Konsumenten in Step3-Persona-Review.

### Tabellen (`.table`)
- TH-Padding 10 → 12 px, TD-Padding 12 → 14 px.
- TH `font-weight: 500`, `--ls-mono-wide`.
- TR-Hover: `var(--bg-glass)` + 160-ms-Transition.
- TR-Selected: `var(--accent-soft)` (statt `--plasma-soft`), 2-px-Inset-Border-Left mit `--accent`.

### Log-Viewer (`.log` / `.log-block`)
- `border-radius: --r-3` (vorher `--r-1`).
- Default-Text-Farbe von `--mono-200` auf `--fg-body` (themed).
- Level-Farben: `--info` / `--warn` / `--err` / `--ok` / `--accent` (Agent) — direkt auf die oklch-Tokens, statt `--plasma-400`/`--status-*`.

### KPI (`.kpi` neu)
- 3-Zeilen-Stack: Mono-Caps-Label (`--ls-mono-wide`) + Serif-Numerale (40 px, `--ls-display`, `tabular-nums`) + Mono-Delta.
- `.delta` default `--ok`, `.delta.is-down` auf `--err`.

### Toast (`.toast` / `.toast--*`)
- Glass-Surface (`var(--bg-glass-hi)` + `backdrop-filter: blur(20px) saturate(160%)`).
- Border-Left 3 px (vorher 2 px), Radius `--r-3` (vorher `--r-1`).
- Status-Border-Colors auf `--ok`/`--warn`/`--err`/`--info` gemappt; `--toast--plasma` und `--toast--info` sind jetzt synonym.

### Popover / Tooltip / Kbd
- `.popover`: Glass-Surface mit `--r-3`.
- `.tooltip`: `bg-inverse` / `fg-on-inverse` (themed), `--r-2`.
- `.tooltip--dark`: nutzt `--bg-elevated` + `--fg` mit Border (statt mono-Hardcoded).
- `.kbd-key`: 20×20 (vorher 18×18), `--r-2`, `--shadow-1` für die typische Tastenkappe.

### Marketing-Nav (`.nav`)
- Bekommt `var(--bg-glass)` + `backdrop-filter: blur(12px)`. Aurora-Mesh aus Slice A scheint jetzt auch unter dem Marketing-Header durch.

## Validierung

```
npm run lint:backend    # ruff: All checks passed
npm run test:backend    # pytest: 756 passed, 9 skipped
npm run lint:frontend   # eslint: 0 errors, 1 vorbestehender Warning (Step4Report.vue:2:49)
npm run test:frontend   # vitest: 9 files, 69 tests passed
npm run build:frontend  # vite build: 119 KB CSS / 528 KB JS gz, in 2.68s
```

`npm run check`-Aggregat = grün.

## Akzeptanzkriterien (Issue #150)

- [x] `npm run check` grün
- [x] Stepper / Persona / Tabellen / Log-Block / KPI / Toast / Popover sichtbar v2-konform in Light + Dark
- [x] Closes #150 (Tracking-Issue #147 wird durch diesen Slice geschlossen, weil C der letzte ist)

## Risiken / Out-of-Scope

- **Step3-Component-spezifische Persona-Markup**: nutzt aktuell `.persona`-Klasse aus `global.css`. Avatar-Gradient-Variant (`is-aurora`/`is-mint`/`is-violet`) wird automatisch nicht gesetzt — Default-Iris/Violet-Gradient gilt überall. Wer Variation will, kann die Modifier-Klasse pro Persona setzen (kleine Folge-Aufgabe).
- **Stance-Bar-Konsumenten**: Markup ist bereitgestellt, wird aber noch nicht von einer existierenden Vue-Komponente gerendert. Step3Simulation kann das als nächstes adoptieren (separate Story aus dem v0.9.0-Backlog: Polarization-Indikatoren).
- **Brand-Glyph** (`AgoraGlyph.vue`) bleibt unverändert — der v2-Mock zeigt einen Aurora-→-Violet-Gradient-Block-Glyph; das ist ein Markenentscheid und außerhalb des Design-Refresh-Slice-Sets.
- **Bestehender Lint-Warning** in `Step4Report.vue:2:49` ist nicht in Slice-C-Scope.

## Abschluss der Design-v2-Migration

Slice A (Foundation) + B (Visual Language) + C (Surfaces) bringen das Frontend vollständig auf das **2026-Design-Language-v2-Vokabular**:

| Slice | PR | Themen |
|-------|----|--------|
| A | [#152](https://github.com/arn0ld87/agora/pull/152) | Tokens, Fonts, ThemeToggle, Aurora-Mesh, Light-Default |
| B | [#153](https://github.com/arn0ld87/agora/pull/153) | Buttons, Badges, Inputs, Tabs, Panel, Card, Field, Select, StickyBanner, WorkspaceHeader |
| C | (dieser PR) | Stepper, Persona, Tabellen, Log, KPI, Toast, Popover, Kbd, Marketing-Nav |
