# S1 — XSS-Fix Markdown-Rendering · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S1 (Evidence-Pipeline-v2-Initiative, Security-P0)
**Plan:** [docu/2026-05-01-evidence-pipeline-plan.md](2026-05-01-evidence-pipeline-plan.md)
**Status:** abgeschlossen

## Ziel

Den im externen Repo-Review (`agora_repo_review_neuer_stand.md`) gemeldeten XSS-Vektor in `Step4Report.vue` schließen: `marked.parse()`-Output wurde via `v-html` ohne Sanitizer ins DOM geschrieben.

## Vorgehen

1. Im `Step4Report.vue` lief alles Markdown-Rendering durch eine lokale `renderMarkdown(text)`-Funktion (Zeilen 274–276 vor dem Fix), die `marked.parse(text)` direkt zurückgab.
2. Das Ergebnis wurde an zwei Stellen via `v-html` gerendert (`Step4Report.vue:578` und `:640`).
3. Untrusted-Markdown-Quellen: LLM-generierte Sektionen, Report-Volltexte. Beide können präparierte Tags wie `<script>`, `<iframe>`, `<img onerror=…>`, `javascript:`-URLs einschmuggeln.

## Implementierung

- DOMPurify (^3.4.2) als production-dependency installiert: `cd frontend && npm install dompurify`.
- Neue Util `frontend/src/utils/markdown.js` exportiert `renderMarkdown(text)`. Pipeline: `marked.parse(text) → DOMPurify.sanitize(html)`. `marked.setOptions({ gfm: true, breaks: false, mangle: false, headerIds: false })` aus dem Komponenten-Setup hierhin verschoben (single source of truth).
- `Step4Report.vue` entzieht die lokale `renderMarkdown` und importiert die Util. `import { marked } from 'marked'` ist nicht mehr nötig — entfernt.
- Vitest-Tests in `frontend/src/utils/__tests__/markdown.spec.js`:
  - rendert Standard-Markdown korrekt (Heading, bold, code-fences, http-Links)
  - falsy Input → leerer String
  - `<script>` wird gestrippt
  - `onerror`-Attribute werden entfernt
  - `<iframe>` wird gestrippt
  - `javascript:`-Links werden entfernt
  - `<style>` wird gestrippt

## Tests

- `npm run check` grün:
  - Backend Ruff: All checks passed
  - Backend Pytest: **488 passed, 2 skipped** (Redis-Tests skip, erwartet)
  - Frontend ESLint: 0 errors, 1 warning (preexisting `nextTick` unused)
  - Frontend Vitest: **40 passed (5 Test-Files)** — vorher 31, +9 neu für `renderMarkdown`
  - Vite Build: erfolgreich, Bundle 509 kB (vorher 484 kB; +25 kB durch DOMPurify)

## Geänderte/neue Dateien

- `frontend/package.json` + `frontend/package-lock.json` — DOMPurify hinzugefügt
- `frontend/src/utils/markdown.js` (neu)
- `frontend/src/utils/__tests__/markdown.spec.js` (neu)
- `frontend/src/components/Step4Report.vue` — lokales `renderMarkdown` entfernt, Util importiert, ungenutzter `marked`-Import raus
- `docu/2026-05-01-s1-xss-fix-protokoll.md` (neu, dieses Protokoll)

## Folgeaktionen

- Andere `v-html`-Stellen im Frontend mal abscannen, ob noch ungesicherte Markdown-Renderings existieren (Out-of-Scope S1, könnte R-Cluster-Slice werden, falls relevant).
- Bundle-Size-Warning (509 kB > 500 kB Vite-Default-Limit) ist preexisting; ein dedizierter Code-Splitting-Slice gehört auf den Roadmap-Backlog, nicht in S1.

## Nächster Slice

S2-pre — Schema-Fix `_extract_target_agent` im `NetworkAnalyticsService`. Akzeptanzkriterium: nach Implementierung `backend/scripts/diagnose_metric_snapshot.py --limit 10` zeigt für ≥6 Runs Verdict `metrics_consistent`.
