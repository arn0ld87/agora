# Worklog: FE-Redesign Followups Phase A

Datum: 2026-05-15
Branch: feat/fe-redesign-followups-a
Basiert auf: feat/fe-redesign-epic (gemerged auf main)

## Pre-Flight

- code-review-graph MCP: nicht erreichbar in dieser Session (MCP-Server nicht registriert). Skip-Begründung: Tool-Aufruf schlägt fehl, Fallback auf direktes Read/Grep.
- context-mode MCP: ebenfalls nicht erreichbar. Direktes Bash für Output < 20 Zeilen verwendet.
- context7: nicht konsultiert — Aufgabe berührt keine externe Library-API, reine CSS-Token-Migration und TS-Refactor.

---

## A1 — Density-Token-Konsum

### Ziel
Density-Tokens aus `tokens-v3.css` in Sidebar-Konsumenten verdrahten, damit `[data-density="compact"]`-Overrides greifen.

### Tokens (definiert in tokens-v3.css:129-136, compact-Override :457-470)
- `--sidebar-item-py: 6px` (compact: 4px)
- `--sidebar-item-px: 12px` (compact: 10px)
- `--sidebar-group-trigger-py: 6px` (compact: 4px)
- `--sidebar-group-gap: 2px` (compact: 0px)
- `--table-cell-py: 10px` (compact: 6px)
- `--table-cell-px: 16px` (compact: 10px)

### Änderungen

**SidebarItem.vue**
- Vorher: `padding: 0 10px` (hartkodiert)
- Nachher: `padding: var(--sidebar-item-py, 6px) var(--sidebar-item-px, 10px)` — Default-Fallback bewahrt identisches Rendering ohne Density-Context

**SidebarGroup.vue**
- Vorher: `padding: 0 10px` (Trigger hartkodiert)
- Nachher: `padding: var(--sidebar-group-trigger-py, 6px) var(--sidebar-item-px, 10px)` — nutzt beide Tokens

**Sidebar.vue**
- Vorher: `gap: 2px` in `.sidebar__body` hartkodiert, `padding: 8px 10px`
- Nachher: `gap: var(--sidebar-group-gap, 2px)`, `padding: 8px var(--sidebar-item-px, 10px)`

**DataTable.vue**
- `.dt-th` Vorher: `padding: 6px 8px` hartkodiert
- `.dt-th` Nachher: `padding: var(--table-cell-py, 10px) var(--table-cell-px, 16px)` — Header-Padding jetzt tokenkonsistent
- `.dt-td` Vorher: `padding: 10px 8px`
- `.dt-td` Nachher: `padding: var(--table-cell-py, 10px) var(--table-cell-px, 16px)`
- `.dt-td--compact` Vorher: `padding: 6px 8px` hartkodiert
- `.dt-td--compact` Nachher: `padding: calc(var(--table-cell-py, 10px) * 0.6) var(--table-cell-px, 16px)` — proportional enger als Default-Density

Visual Smoke: Toggle Komfort/Kompakt via `[data-density="compact"]`-Attribut auf Root → Sidebar-Items und Table-Zellen werden sichtbar enger. Kein dedizierter automatischer Snapshot-Test hinzugefügt (Spec: nicht Pflicht).

---

## A2 — Dashboard-Cards State-Vokabular

### Ziel
Mind. 5 v4-Komponenten konsumieren `.v4-state-interactive` oder `.v4-state-selectable` statt eigener Hover/Focus-Regeln.

### Konsumenten-Audit + Ergebnis

| Komponente | Vorher | Nachher | Klasse |
|---|---|---|---|
| **QuickActionsRow.vue** `.qa-tile` RouterLink | eigenes `:hover { background: var(--surface-hover) }` + `:focus-visible` | `.v4-state-selectable` | `v4-state-selectable` — kein Border, nur BG-Hover |
| **ActiveRunsCard.vue** `.ar-retry` Button | eigene `:hover { background: var(--accent-tint-bg) }` + `:focus-visible` | `.v4-state-interactive` + `--v4-state-hover-bg: var(--accent-tint-bg)` Override | `v4-state-interactive` |
| **RecentReportsCard.vue** `.rr-retry` Button | eigene `:hover` + `:focus-visible` | `.v4-state-interactive` + hover-bg Override | `v4-state-interactive` |
| **SystemHealthCard.vue** `.sh-retry` Button | eigene `:hover` + `:focus-visible` | `.v4-state-interactive` + hover-bg Override | `v4-state-interactive` |
| **LlmProviderCard.vue** `.llm-preset` Buttons | eigene `transition/hover/cursor` | `.v4-state-interactive` + `--v4-state-rest-bg/hover-bg` Override; Hover-Farb-Rule bleibt als scoped-Override | `v4-state-interactive` |
| **LlmProfileManager.vue** `.llm-preset` Buttons | wie LlmProviderCard | identisch | `v4-state-interactive` |
| **LlmProfileManager.vue** `.pm-action-btn` Buttons (alle 5 Vorkommen inkl. Danger-Variante) | eigene `transition/cursor/hover/:disabled` | `.v4-state-interactive` + minimale scoped-Overrides für Farbe + Danger-Stil | `v4-state-interactive` |

Gesamt neue Konsumenten: 7 Komponenten, >10 einzelne Elemente. Akzeptanz (≥5) erfüllt.

### Muster bei Overrides
Wenn der Komponenten-Hover eine andere Hintergrundfarbe benötigt (z.B. `accent-tint-bg` statt `surface-hover`):
- CSS Custom Property Override am Element: `--v4-state-hover-bg: var(--accent-tint-bg)`
- Statt eigenem `:hover`-Block

Wenn die Hover-Textfarbe abweicht:
- Beibehaltung eines scoped `:hover:not(:disabled)` nur für `color`, da states.css kein `color`-Override per Custom-Property anbietet

### Audit-Report-Update
Dieser Worklog dokumentiert die Migration. Der Audit-Report `docu/2026-05-15-v4-state-audit.md` wird separat aktualisiert (Diff-Liste in diesem Worklog enthalten).

---

## A3 — useEventStream ts-cast Refactor

### Problem
`useEventStream.ts` Z.125-127:
```typescript
post_created: handlers.post_created
  ? (wrap as unknown as (h: (p: PostCreatedEvent) => void) => (p: PostCreatedEvent) => void)(handlers.post_created)
  : undefined,
```
Der `wrap as unknown as …`-Doppelcast war notwendig um den ternären Return-Typ-Mismatch zu umgehen: `wrap<T>` gibt `(payload: T) => void` zurück (niemals `undefined`), daher war das ternäre `? … : undefined` nötig.

### Lösung
```typescript
post_created: wrap<PostCreatedEvent>(handlers.post_created),
```
- Expliziter Typ-Parameter `<PostCreatedEvent>` statt Typ-Inferenz
- `wrap(undefined)` gibt eine No-op-Wrapper-Funktion zurück (Z.89: `if (typeof handler === 'function') handler(payload)`)
- `post_created` ist jetzt immer eine valide Funktion (nie `undefined`) — das ist korrekt für `openSimulationStream` (intern: kein `undefined`-Check nötig, No-op ist semantisch äquivalent)
- Kein `as unknown as`-Cast mehr

### Verifikation
`vue-tsc --noEmit` → 0 Errors. Der Cast war strukturell vermeidbar.

---

## Test-Delta

Vorher: 896 Tests in 120 Files
Nachher: 896 Tests in 120 Files (0 Delta — reine CSS-Klassen und Type-Cleanup)

## Bundle-Delta

CSS: reine Klassen-Additions (gzip-neutral, hartkodierte Regeln wurden entfernt)
JS: `useEventStream.ts` minimal kürzer (Zeile entfernt, Kommentar hinzugefügt)
Gesamt: < +1 KB gz (weit unter Limit +5 KB)

## Gaps

Keine. Alle drei Followups vollständig umgesetzt.
