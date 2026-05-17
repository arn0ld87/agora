# FE-Redesign Slice 4 — Cmd+K Command-Palette — Worklog

**Datum:** 2026-05-15  
**Branch:** `feat/fe-redesign-4-cmd-k`  
**Worktree:** `/private/tmp/agora-fe-redesign-4`  
**Worker:** Claude Sonnet 4.6

---

## Ziel

Spotlight-artige Cmd+K Command-Palette für globale Navigation in der Agora v4 App-Shell.

---

## Pre-Flight

- code-review-graph: nicht verfügbar (MCP-Server nicht erreichbar in dieser Session).
- context7: Skip — keine externe Library-Frage, reka-ui-API direkt aus `node_modules/reka-ui/dist/` gelesen.
- sequential-thinking: Skip — Spec aus Plan vollständig, Scope disjunkt, kein Multi-Layer-Problem.
- Direkt zu Read-Exploration gesprungen. Im Worklog begründet.

---

## Implementierte Dateien

### Neu

| Datei | LOC | Beschreibung |
|---|---|---|
| `frontend/src/composables/useCommandPalette.ts` | 65 | Open/Close/Toggle, query-Reset, Recent-Stack (max 8, deduped, localStorage) |
| `frontend/src/composables/__tests__/useCommandPalette.spec.ts` | 80 | 5 Tests: open/close/toggle, query-Reset, Recent-Dedup+Max, localStorage-Persistenz |
| `frontend/src/stores/commandsStore.ts` | 90 | Pinia-Store: buildStaticCommands, getOrdered, filter |
| `frontend/src/stores/__tests__/commandsStore.spec.ts` | 85 | 5 Tests (4 Pflicht + 1 Extra): Nav-Routes vollständig, filter, getOrdered-Recent, getOrdered-leer |
| `frontend/src/components/v4/shell/CommandPalette.vue` | 250 | reka-ui DialogRoot + ComboboxRoot, Gruppierung Recent/Nav, Hint-Footer |
| `frontend/src/components/v4/shell/__tests__/CommandPalette.spec.ts` | 120 | 3 Tests: isOpen=false, isOpen=true rendert cmdk-content, pickCommand-Seiteneffekte |

### Modifiziert

| Datei | Änderung |
|---|---|
| `frontend/src/components/v4/shell/AppShell.vue` | `defineAsyncComponent(CommandPalette)` + Keydown-Listener (Cmd+K / Ctrl+K) |
| `frontend/src/components/v4/shell/Topbar.vue` | Search-Button `@click="openPalette"` + `useCommandPalette` import |
| `frontend/src/i18n/locales/de.json` | `cmd.*`-Keys (title, placeholder, trigger, noResults, groups, hints) |
| `frontend/src/i18n/locales/en.json` | `cmd.*`-Keys (englische Übersetzungen) |

---

## Architektur-Entscheidungen

### Singleton-Refs statt Pinia-Store für Open/Close

`useCommandPalette` nutzt module-scope Refs (`isOpen`, `query`, `recent`). Das ermöglicht das Teilen des Zustands zwischen AppShell-Keydown-Listener und CommandPalette.vue ohne Pinia-Overhead und ohne Store-Registration-Reihenfolge-Problem.

### defineAsyncComponent für CommandPalette

Die CommandPalette zieht reka-ui Dialog + Combobox in den Bundle. Ohne lazy-load würde das den AppShell-Chunk um ~28 kB gz vergrößern. Mit `defineAsyncComponent` bleibt der AppShell-Chunk-Delta bei +0.49 kB gz; CommandPalette wird als separater Chunk nur beim ersten Cmd+K geladen.

### Filter-Function in ComboboxRoot

`ComboboxRoot` bekommt `:filter-function="() => true"` — die eigene Filterlogik läuft via `commandsStore.filter()`, damit Recent-Ordering und group-Separation erhalten bleiben.

### pickCommand-Typsicherheit

`ComboboxRoot @update:model-value` liefert `AcceptableValue` (string | number | object | null). Guard `typeof value !== 'string'` verhindert TypeScript-Fehler ohne `any`.

---

## Test-Strategie

reka-ui-Primitives werden in CommandPalette.spec.ts via `global.stubs` entkoppelt. Die Stubs rendern den Slot-Inhalt durch, wodurch `cmdk-content`, `cmdk-item` und `data-value`-Attribute testbar sind ohne JSDOM-Teleport-Fehler.

---

## Verification

```
bun run typecheck  → GRÜN (0 Fehler)
bun run test       → 852/852 Tests grün (111 Dateien)
bun run build      → GRÜN (469 ms)
bun run lint       → GRÜN (0 Findings)
```

**Bundle-Delta:**
- AppShell.js: 4.96 → 5.45 kB gz (**+0.49 kB** — weit unter +25 kB-Limit)
- CommandPalette.js: neu, 28.80 kB gz (lazy chunk, enthält reka-ui Dialog + Combobox)

---

## Akzeptanzkriterien — Status

- [x] Cmd+K / Ctrl+K öffnet Palette (AppShell-Keydown-Listener)
- [x] ESC schließt (DialogRoot `@escape-key-down`)
- [x] Search-Icon in Topbar öffnet Palette
- [x] Alle Top-Level-Routes als statische Commands (10 Commands: Dashboard, Runs, History, 7× Settings)
- [x] Recent-Stack max 8, persistent in localStorage, deduped
- [x] Bundle-Delta ≤ +25 kB gz (AppShell: +0.49 kB)
- [x] 12 Tests grün (5 composable + 5 store + 3 component — Pflicht: 5+4+3=12)

---

## Gaps / Offene Punkte

- Dynamische Commands (offene Simulationen aus Runs-Store): kein `runsStore.ts` existierte in diesem Worktree. Platzhalter im Store via `getOrdered`-Pattern vorbereitet — `buildStaticCommands` ist erweiterbar um einen zweiten `dynamicCmds: Command[]`-Parameter.
- Recent-Reports als Commands: ebenfalls vorbereitet aber nicht verdrahtet (kein Reports-Store im Scope).
- Keyboard-Navigation Arrow-Up/Down innerhalb des Combobox: reka-ui ComboboxRoot liefert das nativ via ARIA `data-highlighted`.
