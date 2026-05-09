# Arbeitsprotokoll — Design v3 EPIC, Phase 1: Foundation

**Datum:** 2026-05-09
**Branch:** `feat/design-v3-epic-phase1-foundation`
**EPIC:** [docu/2026-05-09-design-v3-epic.md](2026-05-09-design-v3-epic.md)

## Ziel

Foundation für den v3-Reskin legen, ohne v2 zu brechen:

1. v3-Showcase-Canvas unter `frontend/public/design/v3/` zum lokalen Browsen
2. `tokens-v3.css` parallel zu `tokens.css` mit v2→v3-Alias-Layer
3. Geist-Fonts via `@font-face` einbinden (lagen schon im Repo)
4. Feature-Flag `VITE_DESIGN_V3` im `main.ts` zum Umschalten — Default `false`
5. `npm run check` muss grün bleiben

## Vorgehen

### Schritt 1 — Showcase ablegen

Quelle: `Agora.zip` extrahiert nach `/tmp/agora-zip-extract/`.
Ziel: `frontend/public/design/v3/`.

Reinkopieren:
- `Agora Design Language v3.html` → `index.html`
- `agora-v3.css`, `app-v3.jsx`, `design-canvas.jsx`, `tweaks-panel.jsx`
- `ab3-foundations.jsx`, `ab3-controls.jsx`, `ab3-screens.jsx`, `ab3-mobile.jsx`
- `fonts/GeistSans-Variable.woff2`, `fonts/GeistMono-Variable.woff2`

Vite serviert `public/` 1:1 unter `/` → URL `http://localhost:5173/design/v3/`.

### Schritt 2 — Geist-Fonts global registrieren

`frontend/src/assets/styles/fonts.css` aktuell leer. Ergänze `@font-face`-Regeln
für Geist Sans/Mono aus `assets/fonts/`.

Impact: keiner — solange v2 läuft, referenziert v2 weiterhin Inter/JetBrains/
Instrument Serif via Google-Fonts-`<link>`. Geist ist nur „verfügbar".

### Schritt 3 — `tokens-v3.css` erstellen

Komplettes v3-Tokenset aus `agora-v3.css` (Apple Enterprise Light) plus
**v2-Alias-Layer**: Jeder von 130 v2-Token-Namen wird auf das nächste
v3-Pendant gemappt. Dadurch kann der Flag `VITE_DESIGN_V3=true` gesetzt werden,
ohne dass eine einzige Komponente umgeschrieben werden muss — bestehende
`var(--fg)`, `var(--bg-elevated)`, `var(--ff-mono)` … rendern alle gegen
v3-Werte.

Alias-Mapping wie in EPIC-Tabelle definiert.

### Schritt 4 — `main.ts` Feature-Flag

```ts
import './assets/styles/fonts.css'
if (import.meta.env.VITE_DESIGN_V3 === 'true') {
  import('./assets/styles/tokens-v3.css')
} else {
  import('./assets/styles/tokens.css')
}
import './assets/styles/global.css'
```

Default: `VITE_DESIGN_V3=false` → v2 läuft wie bisher.
Toggle für lokales Testen: `VITE_DESIGN_V3=true npm run dev`.

### Schritt 5 — Check + PR

```
cd frontend && npm run check
git add ...
git commit -m "feat(design): v3 EPIC Phase 1 — Foundation (tokens, fonts, showcase, flag)"
git push -u origin feat/design-v3-epic-phase1-foundation
gh pr create ...
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews ...
```

## Risiken / Mitigation

| Risiko | Mitigation |
|---|---|
| v3-Token-Werte (z. B. `--rule` als rgba statt oklch) brechen `color-mix()`-Aufrufe in v2-CSS | Alias-Layer setzt v2-Tokens nur dann auf v3, wenn der Flag gesetzt ist. Default-Pfad bleibt unangetastet. |
| Showcase-jsx referenziert react@18 via UNPKG (CSP-Issue im Prod-Stack) | Showcase liegt nur unter `public/design/v3/` und ist Dev-Tool. Production-CSP wird in Phase 6 oder via Robots-Block geregelt. |
| Geist-Fonts-`@font-face` triggert FOUC | `font-display: swap` aus v3-CSS übernehmen. v2 nutzt Geist nicht — kein Conflict. |
| Showcase nutzt `<style>`-Block mit `--surface-canvas` global | Showcase ist iframe-isoliert via eigener `agora-v3.css`-Linkung. Bleibt scoped, weil eigenes HTML. |

## Status

- [x] Branch `feat/design-v3-epic-phase1-foundation` angelegt
- [x] Showcase abgelegt unter `frontend/public/design/v3/` (Index + 4 jsx + 4 ab3-jsx + 2 woff2 + agora-v3.css + design-canvas.jsx + tweaks-panel.jsx)
- [x] Geist-Fonts via `@font-face` in `frontend/src/assets/styles/fonts.css` registriert (relativer Pfad nach `assets/fonts/`)
- [x] `tokens-v3.css` (9.17 kB, gz 2.52 kB) mit komplettem v3-Tokenset + v2-Alias-Layer (130 Token-Aliasse) + light-only `data-theme`-Override + v3-kompatible `.t-*`-Type-Klassen
- [x] `main.ts` Feature-Flag — Default `false`, dynamic import nur wenn `VITE_DESIGN_V3=true`
- [x] `npm run check` grün:
  - `vue-tsc --noEmit` → 0 Errors
  - `eslint .` → 0 Errors
  - `vitest run` → **45 Files / 461 Tests passed**
  - `vite build` → 911 Module, 1.68 s, kein Drift im Default-Bundle
  - `VITE_DESIGN_V3=true vite build` → emittiert `tokens-v3.css` zusätzlich (9.17 kB)
- [ ] Commit + Push
- [ ] PR + Gemini-Review

## Verifikation lokal

```bash
# v2 (Default)
cd frontend && npm run dev
# → http://localhost:5173/  (Aurora-Coral / Instrument Serif unverändert)

# v3 aktivieren
VITE_DESIGN_V3=true npm run dev
# → http://localhost:5173/  (Apple-Blue, Geist Sans, light-only)

# Showcase (immer verfügbar, auch ohne Flag)
# → http://localhost:5173/design/v3/
#   → 14 Artboards: Brand & Foundations · UI Kit · Workspace Desktop · Mobile
```

## Was Phase 2 anpackt

`WorkspaceLayout`, `WorkspaceHeader`, `WorkspaceSplit`, `WorkspaceModeSwitch`,
`WorkspaceStepStatus`, `WorkspaceBrandLink` an v3-Tokens migrieren — Sidebar
nach Apple-Settings-Pattern, Header `glass`-translucent, Mode-Switch als
Segmented Control. Ziel: alle Layout-Files brauchen unter `VITE_DESIGN_V3=true`
keine Alias-Layer-Shortcuts mehr, sondern referenzieren v3-Tokens nativ.
