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

marked.setOptions({ gfm: true, breaks: false, mangle: false, headerIds: false })

export function renderMarkdown(text) {
  if (!text) return ''
  let html
  try {
    html = marked.parse(text)
  } catch {
    html = String(text)
  }
  return DOMPurify.sanitize(html)
}
