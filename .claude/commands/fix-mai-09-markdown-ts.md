---
description: MAI-09 — frontend/src/utils/markdown.js wird TS-migriert. XSS-Sicherheit (DOMPurify) und Marker-Patterns bleiben unverändert.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-09-markdown-ts — `markdown.js` → `markdown.ts`

## Ziel

`frontend/src/utils/markdown.js` ist die letzte JS-Datei unter `frontend/src/`. Sie wird TS-migriert. DOMPurify-Konfiguration und Confidence-/Quote-Marker bleiben byte-genau erhalten.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-09/`.
- Branch: `refactor/mai-09-markdown-ts`.

## Schritt-für-Schritt

### Schritt 1: Status-Inventur

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-09
ls -la frontend/src/utils/markdown.*
cat frontend/src/utils/markdown.js
rg -n "from '.*markdown'" frontend/src/  # Aufrufer-Inventar
```

### Schritt 2: Datei umbenennen + TS-Annotationen

```bash
git mv frontend/src/utils/markdown.js frontend/src/utils/markdown.ts
```

`frontend/src/utils/markdown.ts`:

```typescript
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import type { Tokens } from 'marked'

// MAI-09: TS-Migration der letzten Frontend-JS-Datei.
// XSS-Sicherheit und Marker-Detection-Patterns sind hier unverändert.

interface PurifyConfig {
  ALLOWED_TAGS?: string[]
  ALLOWED_ATTR?: string[]
  ADD_ATTR?: string[]
  FORBID_TAGS?: string[]
  FORBID_ATTR?: string[]
}

const PURIFY_CONFIG: PurifyConfig = {
  ALLOWED_TAGS: [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'strong', 'em', 'b', 'i', 'u',
    'ul', 'ol', 'li',
    'blockquote', 'q', 'cite',
    'code', 'pre',
    'a',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'span', 'div',
  ],
  ALLOWED_ATTR: ['href', 'title', 'class', 'id', 'lang'],
  // MAI-07: sim-quote-Klasse muss durch — ADD_ATTR='class' deckt das.
  ADD_ATTR: ['class'],
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'svg'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
}

// Pattern für simulierte Persona-Quotes (Quelle: backend manager.py::_render_simulated_quote_blocks)
const SIM_QUOTE_HEADER_RE = /\*\*Simulierter Persona-O-Ton\*\*/

// Confidence-Marker (Quelle: backend sections.py::render_confidence_markers_for_section)
const CONF_LOW_RE = /⚠️\s*\*\*Low-Confidence-Hinweis\*\*/

function tagSimulatedQuotes(html: string): string {
  return html.replace(
    /<blockquote>([\s\S]*?)<\/blockquote>/g,
    (match, inner: string) => {
      if (SIM_QUOTE_HEADER_RE.test(inner)) {
        return `<blockquote class="sim-quote">${inner}</blockquote>`
      }
      if (CONF_LOW_RE.test(inner)) {
        return `<blockquote class="conf-low">${inner}</blockquote>`
      }
      return match
    },
  )
}

export function parseMarkdown(input: string | null | undefined): string {
  if (!input) return ''

  // marked → HTML
  const rawHtml = marked.parse(input, { async: false, gfm: true }) as string

  // DOMPurify → sanitize
  const sanitized = DOMPurify.sanitize(rawHtml, PURIFY_CONFIG)

  // Marker-Tagging (XSS-safe, da nach Sanitize)
  return tagSimulatedQuotes(sanitized)
}

export function renderMarkdown(input: string | null | undefined): string {
  return parseMarkdown(input)
}

// Alias für Legacy-Aufrufer
export default { parseMarkdown, renderMarkdown }
```

### Schritt 3: Aufrufer prüfen

```bash
# Vite löst .ts auf .js auf — Imports OHNE Extension funktionieren weiter.
rg -n "from '.*markdown\.js'" frontend/src/ \
  && echo "FIXEN: explizite .js-Imports gefunden" \
  || echo "OK: keine harten .js-Imports"

# Falls Treffer: Extension entfernen
# sed -i 's|markdown\.js|markdown|g' <Pfade>
```

### Schritt 4: Tests anpassen

`frontend/src/utils/__tests__/markdown.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { parseMarkdown, renderMarkdown } from '../markdown'

describe('markdown.ts', () => {
  it('renders basic markdown', () => {
    expect(parseMarkdown('# Hello')).toContain('<h1>Hello</h1>')
  })

  it('sanitizes XSS', () => {
    const evil = '<script>alert(1)</script>**bold**'
    const out = parseMarkdown(evil)
    expect(out).not.toContain('<script>')
    expect(out).toContain('<strong>bold</strong>')
  })

  it('handles null input', () => {
    expect(parseMarkdown(null)).toBe('')
    expect(parseMarkdown(undefined)).toBe('')
  })

  it('preserves sim-quote class (MAI-07)', () => {
    const md = '> **Simulierter Persona-O-Ton** (p1)\n> Text'
    const out = parseMarkdown(md)
    expect(out).toContain('class="sim-quote"')
  })
})
```

## Verifikation

```bash
# 1) Typecheck (vue-tsc muss markdown.ts mit allen Aufrufern typen)
cd frontend && npm run typecheck

# 2) Tests
cd frontend && npm test -- --run

# 3) Build
cd frontend && npm run build

# 4) Letzte JS-Datei? (nach Migration sollte unter src/ keine markdown.js mehr existieren)
find frontend/src -name "*.js" -not -path "*/node_modules/*"
# Erwartet: leer (oder nur tests-Helper, die bewusst .js sind)
```

## Warum?

REFACTORING_PLAN (1).md §R14: Letzte JS-Datei im Frontend-Tree blockiert Strict-TS-Mode in `tsconfig.json` (`allowJs=false` ist in `STATUS.md` als aktiv markiert — diese eine Datei ist die historische Ausnahme). Mit der TS-Migration ist die Frontend-TS-Konsistenz vollständig.

## Nächste Schritte

1. Worklog.
2. CHANGELOG: `MAI-09 · markdown.js → markdown.ts (letzte JS-Datei im Frontend-Tree).`
3. `/fix-mai-10-close-issue-203`.
