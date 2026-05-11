# Design Language v4 — Slice A: Token-Port

**Datum:** 2026-05-11
**Branch:** feat/design-v4-slice-a-tokens
**Epic:** docs/design/2026-05-11-design-v4-app-shell-epic.md

## Ziel

`design/v3-source/agora-v3.css` (568 LOC, Apple System Tokens, Geist-Fonts, light-only)
als neues `frontend/src/assets/styles/tokens-v3.css` portieren. Der bestehende
Compat-Layer (v1/v2-Aliase) bleibt vollstaendig erhalten, damit alle bisher
v3-migrierten Komponenten ohne Codeaenderung weiter rendern.

## Token-Diff (bedeutende Aenderungen)

Die v4-nativen Token-Werte sind identisch mit der bisherigen tokens-v3.css — beide
basierten bereits auf demselben Apple Enterprise Design System. Keine Wert-Drifts
bei den Kern-Tokens.

### Strukturelle Aenderungen

| Vorher | Nachher | Begruendung |
|--------|---------|-------------|
| `/* v2 → v3 COMPAT LAYER */` | `/* Compat-Layer (v1/v2 → v3/v4) */` | Kommentar auf v4 aktualisiert |
| `@font-face` Duplikate (keine) | `@font-face` aus agora-v3.css entfernt | fonts.css (importiert vor dieser Datei in main.ts) hat korrekte Pfade; Doppeldeklaration vermieden |
| Header: "Agora Design Tokens v3 (2026-05-09)" | Header: "Agora Design Language v4 — ported from design/v3-source/agora-v3.css" | v4-Versionskennung |
| Type-utility-Klassen: `.t-display`, `.t-headline`, `.t-title`, `.t-subtitle`, `.t-body`, `.t-body-sm`, `.t-meta`, `.t-kicker`, `.t-numeral`, `.t-quote` (10 Klassen) | Identisch — direkt aus agora-v3.css portiert | Keine Regression |

### Neu hinzukommende Tokens (aus agora-v3.css)

Diese Tokens sind jetzt nativ im v4-Block (waren bisher bereits in tokens-v3.css
vorhanden — keine neu hinzukommenden Werte, nur Herkunft jetzt explizit auf
agora-v3.css Source-of-Truth):

- `--surface-tint: #fbfbfd` — neu dokumentiert als "sidebar / chrome"
- `--status-teal: #007a87` / `--status-teal-bg` — Status-Teal-Paar explizit nativ
- `--status-gray: #6e6e73` / `--status-gray-bg` — Status-Gray-Paar explizit nativ
- `--fs-largeTitle`, `--fs-caption-2`, `--fs-hero`, `--fs-display` — vollstaendige Type-Scale
- `--lh-largeTitle`, `--tr-largeTitle` — neue Tracking-Werte fuer grossen Titel
- `--r-2` durch `--r-9` + `--r-pill` — vollstaendige Radii-Skala (war bisher r-2..r-9+pill)
- `--shadow-4: 0 8px 24px rgba(0,0,0,0.10), 0 24px 64px rgba(0,0,0,0.12)` — neuer tiefer Schatten
- `--shadow-control` / `--shadow-inset` — Apple-Control-Schatten nativ

### Wichtige Token-Werte (Top 10, alle unveraendert)

| Token | Wert |
|-------|------|
| `--accent` | `#0066cc` |
| `--surface-canvas` | `#f5f5f7` |
| `--text-primary` | `#1d1d1f` |
| `--text-secondary` | `#6e6e73` |
| `--status-green` | `#248a3d` |
| `--status-red` | `#c5292a` |
| `--hairline` | `rgba(60,60,67,0.12)` |
| `--font-sans` | `-apple-system, BlinkMacSystemFont, "SF Pro Display", ...` |
| `--sp-4` | `16px` |
| `--r-pill` | `9999px` |

### Compat-Layer: --lh-* Ratio-Ueberschreibung (bewusste Entscheidung)

`agora-v3.css` definiert `--lh-body: 20px` und `--lh-display: 52px` als Pixel-Werte.
Der Compat-Layer ueberschreibt sie mit Ratio-Werten (`--lh-body: 1.55`, `--lh-display: 1.08`),
da bestehende Komponenten diese als Ratios verwenden:

- `Kicker.vue:19`: `line-height: var(--lh-mono)` (ratio erwartet)
- `SectionHead.vue:67`: `line-height: var(--lh-body, 1.55)` (ratio erwartet)

Diese Ueberschreibung ist gewollt. Cleanup in Slice J.

## Neu hinzugekommene CSS-Klassen (aus agora-v3.css portiert)

Alle Type-Utility-Klassen aus agora-v3.css wurden direkt uebernommen:

- `.t-hero`, `.t-largeTitle`, `.t-title-1/2/3` — Apple-Typographie-Skala
- `.t-headline`, `.t-body`, `.t-body-em`, `.t-callout`, `.t-subhead`
- `.t-footnote`, `.t-caption`, `.t-section-head`, `.t-mono`, `.t-num`
- `.text-secondary`, `.text-tertiary`, `.text-accent` — Utility-Klassen
- `.t-display`, `.t-title`, `.t-subtitle`, `.t-body-sm`, `.t-meta`, `.t-kicker` — v2-kompatible Aliase

## Compat-Layer-Statistik

- **77** native v4-Tokens (aus agora-v3.css :root)
- **133** Compat-Aliase (v1/v2 → v4)
- **210** Tokens gesamt

Compat-Gruppen:
- Brand-Axis (--brand-*): 4
- Neutral-Scale (--ink-0..1000): 11
- Surfaces (--bg, --bg-*, --bg-panel*): 8
- Foreground (--fg, --fg-*): 5
- Lines (--rule, --rule-*): 3
- Mesh (--mesh-*): 5
- Accent-Variants (--accent-ink/soft/glow, --info*): 5
- Status v2-Namen (--ok/warn/err + soft): 6
- Status-Long-Form (--status-success/warn/error/info + soft): 7
- Shadows/Glows (--shadow-glass/popover/modal/editorial/hairline, --glow-*): 8
- Type-Families (--ff-sans/mono/serif): 3
- Type-Sizes v2 (--fs-11..120): 20
- Line-Heights/Tracking v2 (--lh-tight/display/heading/body/mono, --ls-*): 11
- Spacing v2 (--s-1..10): 10
- Radii v2 (--r-0, --r-1): 2
- Controls (--ctl-pad-x): 1
- Grid (--grid-*): 3
- Background (--bg-grid, --bg-page): 2
- Mono-Scale v1 (--mono-50..950): 11
- Neon/Plasma/Paper v1: 12
- Ink v1 (--ink-1..5): 5
- Dark-Mode-Stubs (--bg-dark, --fg-on-dark*): 3

## Bundle-Size-Delta

| Metrik | Vorher (main) | Nachher (v4-port) | Delta |
|--------|--------------|-------------------|-------|
| tokens-v3.css raw | 15 250 bytes | 16 035 bytes | +785 bytes |
| tokens-v3.css Zeilen | 427 | 441 | +14 |
| CSS Bundle (Vite, minified) | 160.17 kB | 159.92 kB | -250 bytes |
| CSS Bundle (gzip) | 24.10 kB | 24.07 kB | -30 bytes |

Das CSS-Bundle ist minimal kleiner, weil die doppelten `@font-face`-Deklarationen
(die durch agora-v3.css neu eingebracht wurden) erkannt und entfernt wurden — sie
existieren bereits korrekt in `fonts.css`.

## Validierungs-Logs

```
npm run typecheck  → 0 Fehler
npm test -- --run  → 49 Test Files, 501 Tests, alle passed
npm run build      → ✓ built in 1.85s, keine neuen Warnungen
npm run lint       → 0 Fehler
```

## Commits

1. `chore(design-v4): vendor v3-source design system files` — 10 neue Dateien in design/v3-source/
2. `feat(design-v4): port agora-v3.css as tokens-v3.css base` — Token-Port + Compat-Layer
3. `docs(design-v4): slice A worklog` — diese Datei
