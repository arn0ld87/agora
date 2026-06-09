# Task 16b — Klickbare Quotes mit Source-Anchor-Scroll

**Datum:** 2026-05-02
**Branch:** feat/layer-4-task-16b-quote-anchor-scroll
**Basis:** 92970af (Sub-Slice 16a, ConfidenceBadge + Hover-audit_trail)
**Issue:** Closes #173 (16a + 16b zusammen schliessen den Issue)

## Ziel

Evidence-Items mit `quote`-Feld als `<blockquote>` rendern statt als `<span>`.
Items mit `source_id_anchor` bekommen einen klickbaren Button, der je nach Anchor-Format:
- `agent-log-X#entry-Y` → smooth scrollIntoView auf `#agent-entry-Y`
- `web:URL` → window.open in neuem Tab (noopener,noreferrer)
- `kg:...` → console.info (noch nicht implementiert)
- null/unbekannt → kein Effekt, keine Exception

## Geaenderte Dateien

### Neu

- `frontend/src/utils/sourceAnchor.ts` — Parser (parseSourceAnchor, entryAnchorId) fuer source_id_anchor-Strings via Regex
- `frontend/src/utils/__tests__/sourceAnchor.spec.ts` — 9 Unit-Tests fuer alle Anchor-Formate

### Geaendert

- `frontend/src/components/Step4Report.vue`
  - Import von parseSourceAnchor + entryAnchorId (Z. 17)
  - navigateToAnchor-Helper (Z. 419-436)
  - Agent-Log-Entry: :id-Attribut via entryAnchorId (Z. 722)
  - Evidence-Item-Render: blockquote v-if item.quote, span v-else, button v-if source_id_anchor (Z. 790-801)
  - CSS: .agent-entry.is-highlighted, .evidence-quote, .evidence-anchor-link (Ende style scoped)

- `frontend/src/components/__tests__/Step4Report.spec.ts`
  - 4 neue Cases: blockquote-Render, kein blockquote ohne quote, anchor-button, window.open bei web-anchor

- `frontend/src/i18n/locales/de.json` — step4.quote.openSource = "Quelle oeffnen"
- `frontend/src/i18n/locales/en.json` — step4.quote.openSource = "Open source"
- `CHANGELOG.md` — [Unreleased] Added-Bullet

## Verifikation

- npm test: 125 passed (vorher 112, +13)
- npm run lint: clean
- npm run build: clean (nur bekannte Chunk-Size-Warnung)
- git diff --exit-code schemas/: clean (Backend nicht angetastet)

## Layer-Status

Layer 4 abgeschlossen. Sub-Slices 15 (strict-Zod), 16a (ConfidenceBadge), 16b (Quotes+Anchor) vollstaendig.
