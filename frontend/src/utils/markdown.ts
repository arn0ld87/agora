// S1 (Evidence-Pipeline v2) — sicheres Markdown-Rendering.
//
// `Step4Report.vue` rendert Reports und Sektionen via `v-html`. Roher
// `marked.parse(...)`-Output ohne Sanitizer war ein XSS-Vektor: ein
// präparierter Report-String konnte `<script>`/`<img onerror=...>` direkt
// ins DOM einschleusen. DOMPurify strippt das aus dem fertigen HTML.
//
// Reuse-fähig: jede Komponente, die LLM-/User-Markdown via `v-html`
// ausgibt, soll diesen Pfad nutzen.

import { marked } from 'marked'
import DOMPurify from 'dompurify'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
marked.setOptions({ gfm: true, breaks: false } as any)

export function renderMarkdown(text: string | null | undefined): string {
  if (!text) return ''
  let html: string
  try {
    html = marked.parse(text) as string
  } catch {
    html = String(text)
  }
  return DOMPurify.sanitize(html)
}
