# EPIC: Design Language v3 — Apple Enterprise Reskin

**Status:** Phase 1 in Arbeit · Phase 2–6 geplant
**Owner:** Alexander Schneider (`arn0ld87`)
**Quelle:** `Agora.zip` (extrahiert nach `/tmp/agora-zip-extract/`) — Files
`agora-v3.css`, `ab3-foundations.jsx`, `ab3-controls.jsx`, `ab3-screens.jsx`,
`ab3-mobile.jsx`, `app-v3.jsx`, `Agora Design Language v3.html`.

## Motivation

`Agora Design Language v3.html` definiert einen Marken-Pivot:

| Achse | v2 (aktuell) | v3 (Ziel) |
|---|---|---|
| Theme | Dual (light + dark) | **Light only** |
| Akzent | Aurora coral `oklch(72% 0.20 38)` | **Apple Blue `#0066cc`** |
| Sans | Inter Tight | **SF Pro / Geist Sans** |
| Serif | Instrument Serif (Headlines) | **keine Serif** — alles Sans |
| Mono | JetBrains Mono | **SF Mono / Geist Mono** (nur Numerik/Code) |
| Farbsystem | `oklch` + `color-mix` | **rgba/Hex** (klassischer Apple Pfad) |
| Buttons | flat tinted, `--r-3` | **Pills `--r-pill`**, `font-weight: 590` |
| Listen | Cards, generous padding | **Apple Settings groups** (44 px row, hairlines) |
| Kontrolle | Radio/Select | **Segmented Controls** + iOS-Toggles |
| Glass | Liquid-Glass dominant | **sparingly** (`--surface-translucent` nur Header/Sidebar) |

**Inspirationen v3 (laut `agora-v3.css` Header):** macOS Sequoia Settings ·
App Store Connect · Apple Business Manager · Apple Vision Pro.

## Blast-Radius (Code-Review-Graph + ripgrep, 2026-05-09)

| Metrik | Wert |
|---|---|
| Vue/CSS-Files mit `var(--…)` | 57 |
| Distinct v2-Token-Namen in Verwendung | 130 |
| Frontend-Specs | 45 |
| Vue-Files ≥ 300 LOC | 15 (8 davon ≥ 600 LOC) |
| Top-Token-Hits | `--ff-mono` 209 · `--rule` 177 · `--accent` 175 · `--fg` 160 · `--s-3` 144 · `--ff-serif` 55 |

## Phasen

| # | Titel | Branch | Inhalt | Aufwand | Tests | Reversibel |
|---|---|---|---|---|---|---|
| **1** | **Foundation** | `feat/design-v3-epic-phase1-foundation` | `tokens-v3.css` parallel zu v2 mit v2→v3 Alias-Layer · Geist-Fonts via `@font-face` · Showcase unter `/design/v3/` · Feature-Flag `VITE_DESIGN_V3` im `main.ts` (default `false`) | ~3 h | grün ohne Änderung | trivial (Flag flip) |
| **2** | Layouts & Shell | `feat/design-v3-epic-phase2-shell` | `WorkspaceLayout`, `WorkspaceHeader`, `WorkspaceSplit`, `WorkspaceModeSwitch`, `WorkspaceStepStatus`, `WorkspaceBrandLink` an v3-Tokens · Apple-Settings-Sidebar · Header `glass`-translucent | ~1 d | Snapshot-Refresh | per Revert |
| **3** | UI Kit | `feat/design-v3-epic-phase3-uikit` | `components/ui/*` (`Btn`, `Badge`, `Field`, `Card`, `Select`, `SectionHead`) auf Pill-Buttons + Apple-Lists + Segmented Controls | ~1 d | Snapshot-Refresh | per Revert |
| **4** | Pipeline Step1–3 | `feat/design-v3-epic-phase4-steps123` | `Step1GraphBuild`, `Step2EnvSetup` (+`step2/*`), `Step3Simulation` an v3 | ~1.5 d | mehrere Specs anzupassen | per Revert |
| **5** | Pipeline Step4–5 + Graph + Compare | `feat/design-v3-epic-phase5-steps45graph` | `Step4Report` (1301 LOC), `Step5Interaction`, `GraphPanel`/`graph/*`, `compare/BranchComparePanel` | ~2 d | Snapshot + Visual | per Revert |
| **6** | Cleanup | `feat/design-v3-epic-phase6-cleanup` | v2-Tokens raus · Alias-Layer raus · `data-theme="dark"`-Pfad raus · Theme-Toggle entfernen · Feature-Flag `VITE_DESIGN_V3` als Default `true` und später entfernen · Google-Fonts-`<link>` raus | ~0.5 d | grün | nur Vorwärts |

**Summe:** ~6.5 Tage über 6 PRs. Jeder PR durchläuft `CLAUDE.md`-PR-Workflow
(Branch → `gh pr create` → 90 s warten → Gemini-Findings sichten → mergen).

## Ziel-Architektur ab Phase 1

```
frontend/
  index.html                       # behält v2-Google-Fonts-link bis Phase 6
  src/
    main.ts                        # bedingt: tokens.css ODER tokens-v3.css je nach VITE_DESIGN_V3
    assets/
      fonts/
        GeistSans-Variable.woff2   # bereits da
        GeistMono-Variable.woff2   # bereits da
      styles/
        fonts.css                  # @font-face Geist Sans/Mono ergänzt
        tokens.css                 # v2 (default, bleibt)
        tokens-v3.css              # NEU — Apple Enterprise Light + v2-Aliasse
        global.css                 # bleibt
  public/
    design/
      v3/                          # NEU — Showcase aus Agora.zip 1:1
        index.html
        agora-v3.css
        ab3-*.jsx
        app-v3.jsx
        design-canvas.jsx
        tweaks-panel.jsx
        fonts/
```

## Token-Mapping v2 → v3 (Auszug, in `tokens-v3.css` als Alias verdrahtet)

| v2 | v3 |
|---|---|
| `--bg` | `--surface-base` |
| `--bg-elevated` | `--surface-elevated` |
| `--bg-sunken` | `--surface-canvas` |
| `--fg` | `--text-primary` |
| `--fg-body` | `--text-primary` |
| `--fg-muted` | `--text-secondary` |
| `--fg-meta` | `--text-tertiary` |
| `--rule` | `--hairline` |
| `--rule-strong` | `--hairline-strong` |
| `--accent` | `--accent` (Wert wechselt von Coral zu `#0066cc`) |
| `--accent-soft` | `--accent-tint-bg` |
| `--ok` | `--status-green` |
| `--warn` | `--status-orange` |
| `--err` | `--status-red` |
| `--info` | `--accent` (kein eigenes Iris-Blau mehr in v3) |
| `--s-1..s-10` | `--sp-1..sp-10` |
| `--r-1..r-5` | `--r-3..r-9` |
| `--ff-sans` | `--font-sans` (SF Pro / Geist) |
| `--ff-serif` | **fallback auf `--font-sans`** — keine Serif in v3 |
| `--ff-mono` | `--font-mono` (Geist Mono) |
| `--shadow-1..3` | `--shadow-1..3` (Werte wechseln) |
| `--ctl-h-sm/md/lg` | `--ctl-h-sm/md/lg` (28/32/40 statt 30/38/48) |

Tokens, die in v3 **kein direktes Pendant** haben (Alias = Best-Effort):
- `--brand-iris`, `--brand-mint`, `--brand-violet` → fallen auf `--accent`
- `--bg-glass`, `--bg-glass-hi`, `--bg-panel` → fallen auf `--surface-translucent`
- `--mesh-*`, `--bg-page` (Aurora-Mesh) → in v3 deaktiviert
- `--accent-glow`, `--glow-info`, `--glow-plasma` → fallen weg (v3 nutzt klassische Shadows)

## Phase-1-Akzeptanzkriterien

1. Branch `feat/design-v3-epic-phase1-foundation` existiert.
2. `frontend/public/design/v3/index.html` lädt fehlerfrei unter `npm run dev` und zeigt alle 14 Artboards (Brand, Color, Type, Buttons, Inputs, Workspace Hub, Persona Review, Knowledge Graph, Report Viewer, 5× Mobile).
3. `frontend/src/assets/styles/tokens-v3.css` existiert mit komplettem v3-Tokenset + v2-Alias-Layer.
4. `frontend/src/assets/styles/fonts.css` enthält `@font-face`-Regeln für Geist Sans/Mono aus `assets/fonts/`.
5. `frontend/src/main.ts` lädt entweder `tokens.css` (Default) oder `tokens-v3.css` (`VITE_DESIGN_V3=true`).
6. **`npm run check` (lint + tests + build) bleibt grün** — Phase 1 darf keine Tests brechen.
7. Arbeitsprotokoll [`docu/2026-05-09-design-v3-phase1.md`](2026-05-09-design-v3-phase1.md) gepflegt.
8. PR an `main`, Gemini-Review-Findings adressiert.

## Out-of-Scope für Phase 1

- Komponenten umstellen (das ist Phase 2–5)
- v2-Tokens entfernen (Phase 6)
- Dark-Mode-Pfad entfernen (Phase 6)
- Tests neu schreiben (anpassen erst, wenn Komponenten umgestellt sind)
