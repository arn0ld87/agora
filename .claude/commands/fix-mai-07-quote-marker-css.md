---
description: MAI-07 — Simulierte Persona-Quotes bekommen sichtbares SIM-Badge im exportierten Standalone-HTML/PDF.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-07-quote-marker-css — Quote-Marker im Print-PDF sichtbar

## Ziel

Blockquotes mit `**Simulierter Persona-O-Ton**` werden im Browser-Print-Dialog (Step 4 → „Als PDF drucken") mit einem orangefarbenen Akzentbalken und SIM-Badge gerendert. Heute nur im UI-Render sichtbar, im exportierten HTML/PDF fehlt der Hinweis.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-07/`.
- Branch: `feat/mai-07-quote-marker-css`.
- **MAI-09 muss zumindest geplant sein** — wir editieren `markdown.ts` falls schon migriert, sonst `markdown.js`.

## Schritt-für-Schritt

### Schritt 1: markdown-Util prüfen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-07
ls -la frontend/src/utils/markdown.*
# Falls .js → MAI-09 vorher, oder hier mit .js arbeiten
```

### Schritt 2: Marker-Detection in markdown-Util

`frontend/src/utils/markdown.ts` (oder `.js`):

```typescript
// MAI-07: sim-quote-Detection — Blockquotes mit Simulierter-Persona-O-Ton-Header.
// Pattern stammt aus _render_simulated_quote_blocks() in
// backend/app/services/report_agent/manager.py.
const SIM_QUOTE_HEADER_RE = /\*\*Simulierter Persona-O-Ton\*\*/

function tagSimulatedQuotes(html: string): string {
  // Nimmt fertigen <blockquote>…</blockquote>-Block, prüft Inhalt.
  return html.replace(
    /<blockquote>([\s\S]*?)<\/blockquote>/g,
    (match, inner) => {
      if (SIM_QUOTE_HEADER_RE.test(inner)) {
        return `<blockquote class="sim-quote">${inner}</blockquote>`
      }
      return match
    },
  )
}

export function parseMarkdown(input: string): string {
  // ... bestehende DOMPurify-/marked-Pipeline ...
  const sanitized = DOMPurify.sanitize(rawHtml, {
    // ... bestehende Config ...
    ADD_ATTR: ['class'],  // sim-quote-Klasse muss durch
  })
  return tagSimulatedQuotes(sanitized)
}
```

### Schritt 3: Print-CSS im Standalone-HTML

`frontend/src/composables/useReportExports.ts::buildStandaloneHtml()`:

```typescript
export function buildStandaloneHtml(title: string, bodyHtml: string) {
  return `<!doctype html>
<html lang="de"><head><meta charset="utf-8" />
<title>${title}</title>
<style>
  body { font-family: Georgia, 'Iowan Old Style', serif; max-width: 740px; margin: 48px auto; padding: 0 24px; color: #111; line-height: 1.6; font-size: 16px; }
  h1,h2,h3,h4 { font-family: Georgia, serif; line-height: 1.25; margin: 2em 0 0.4em; }
  h1 { font-size: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }
  h2 { font-size: 1.5em; }
  h3 { font-size: 1.2em; }
  p { margin: 0.8em 0; }
  ul, ol { margin: 0.8em 0 0.8em 1.4em; }
  li { margin: 0.3em 0; }

  /* Default-Blockquote (Web-Sources, Original-Zitate) */
  blockquote { border-left: 3px solid #e2681a; margin: 1em 0; padding: 0.2em 1em; color: #555; font-style: italic; }

  /* MAI-07: Simulierte Persona-O-Töne deutlich hervorheben */
  blockquote.sim-quote {
    border-left: 4px solid #e2681a;
    background: #fff8f0;
    padding: 0.6em 1em 0.6em 1.5em;
    margin: 1.2em 0;
    font-style: normal;
    color: #1a1a1a;
    position: relative;
  }
  blockquote.sim-quote::before {
    content: "SIM";
    position: absolute;
    top: -0.6em;
    left: 1em;
    background: #e2681a;
    color: white;
    padding: 2px 8px;
    font-family: system-ui, sans-serif;
    font-size: 0.7em;
    font-weight: 700;
    border-radius: 3px;
    letter-spacing: 0.05em;
  }
  blockquote.sim-quote strong { color: #b85510; }

  code { background: #f3f3f3; padding: 2px 4px; border-radius: 3px; font-size: 0.92em; }
  pre { background: #1a1a1a; color: #eee; padding: 1em; overflow: auto; border-radius: 4px; }
  pre code { background: transparent; color: inherit; padding: 0; }
  table { border-collapse: collapse; margin: 1em 0; table-layout: fixed; }
  th, td { border: 1px solid #ccc; padding: 6px 10px; word-wrap: break-word; }

  .conf-badge { display: inline-block; border-radius: 4px; padding: 1px 6px; font-family: system-ui, sans-serif; font-size: 0.82em; font-weight: 700; line-height: 1.5; }
  .conf-low { background: #fff3cd; color: #7a4b00; border: 1px solid #e7b84f; }
  .conf-medium { background: #e7f0ff; color: #174ea6; border: 1px solid #9bbcff; }
  .conf-high { background: #e6f6ed; color: #17633a; border: 1px solid #90d3aa; }
  hr { border: 0; border-top: 1px solid #ccc; margin: 2em 0; }

  @media print {
    body { margin: 0; padding: 24px; }
    blockquote.sim-quote { break-inside: avoid; }
  }
</style>
</head>
<body>
<h1>${title}</h1>
${bodyHtml}
</body></html>`
}
```

### Schritt 4: UI-Render-Konsistenz

`frontend/src/components/step4/ReportEvidencePanel.vue` (oder wo Markdown gerendert wird) — sicherstellen, dass die `.sim-quote`-Klasse auch im UI gleich styled wird:

```vue
<style scoped>
:deep(blockquote.sim-quote) {
  border-left: 4px solid var(--color-accent-warm, #e2681a);
  background: var(--color-bg-sim-quote, #fff8f0);
  padding: 0.6em 1em 0.6em 1.5em;
  position: relative;
}
:deep(blockquote.sim-quote)::before {
  content: 'SIM';
  position: absolute;
  top: -0.6em;
  left: 1em;
  background: var(--color-accent-warm, #e2681a);
  color: white;
  padding: 2px 8px;
  font-size: 0.7em;
  font-weight: 700;
  border-radius: 3px;
}
</style>
```

### Schritt 5: Tests

`frontend/src/utils/__tests__/markdown.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { parseMarkdown } from '../markdown'

describe('MAI-07 sim-quote tagging', () => {
  it('tags simulated persona quotes with sim-quote class', () => {
    const md = [
      '> **Simulierter Persona-O-Ton** (persona_id: P01, seed_anchor: a1)',
      '> Bei KI-Agenten frage ich sofort: Wo landen die Daten?',
    ].join('\n')
    const html = parseMarkdown(md)
    expect(html).toContain('blockquote class="sim-quote"')
  })

  it('does not tag regular blockquotes', () => {
    const md = '> Das ist ein normales Zitat ohne Sim-Header.'
    const html = parseMarkdown(md)
    expect(html).not.toContain('sim-quote')
    expect(html).toContain('<blockquote>')
  })

  it('preserves DOMPurify-XSS-protection', () => {
    const md = '> **Simulierter Persona-O-Ton** <script>alert(1)</script>'
    const html = parseMarkdown(md)
    expect(html).not.toContain('<script>')
  })
})
```

### Schritt 6: Snapshot manuell prüfen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-07/frontend
# Dev-Server, dann in Step4 einen Bestandsreport öffnen, "Als PDF drucken" klicken,
# Screenshot speichern unter docs/2026-05-14-mai-07-screenshot.png
```

## Verifikation

```bash
# 1) Frontend-Tests
cd frontend && npm test -- --run

# 2) Typecheck
cd frontend && npm run typecheck

# 3) Build (Bundle muss CSS-Klasse enthalten)
cd frontend && npm run build
grep -r "sim-quote" dist/assets/*.css | head -3
# Erwartet: 2+ Matches (CSS-Klasse im gebauten Bundle)

# 4) Manueller Screenshot-Vergleich gegen UI
# Worklog soll das Screenshot-File referenzieren
```

## Warum?

Bewertung §6.3 und §13 Punkt 5: „Simulierte Zitate kennzeichnen — verhindert falschen Eindruck echter Marktforschung." Heute rendert die Pipeline `<simulated_quote>`-Tags zu Markdown-Blockquotes mit Sim-Header (richtig), aber im exportierten Print-PDF fehlt die visuelle Trennung — der Leser sieht ein Zitat und kann nicht auf einen Blick erkennen, dass es simuliert ist.

## Nächste Schritte

1. Worklog mit Screenshot-Anhang.
2. CHANGELOG: `MAI-07 · SIM-Badge für simulierte Persona-Quotes im Print-Export sichtbar.`
3. `/fix-mai-15-e2e-persona-compact` (Block E Abschluss).
