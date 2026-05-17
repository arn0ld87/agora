# FE-Redesign Slice 3 + 4 — State-Vokabular + Command-Palette

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Beide Slices sind disjunkt und können von unterschiedlichen Workern parallel gemacht werden.

## Slice 3 — State-Vokabular-Audit + states.css

**Goal:** Einheitliches CSS-State-Vokabular für alle interaktiven v4-Komponenten. Hover/Focus/Active/Disabled-Behandlung kommt aus einer zentralen `states.css`-Datei, jede Komponente konsumiert die uniformen Mixin-Klassen `.v4-state-interactive` / `.v4-state-selectable`. Audit-Report dokumentiert vorher/nachher.

**Worktree:** `/private/tmp/agora-fe-redesign-3` (Lead legt an, Branch `feat/fe-redesign-3-state-vocab` von `feat/fe-redesign-epic`).

**File Structure:**
- Create: `frontend/src/assets/styles/states.css`
- Create: `docs/2026-05-15-v4-state-audit.md` — Diff-Liste pro Component-Family (vorher/nachher)
- Create: `docs/2026-05-15-fe-redesign-slice-3-worklog.md`
- Modify: alle interaktiven v4-Komponenten in `v4/forms/` (Button, Input, Select, Field, SegmentedControl, DropdownMenuItem) und `v4/data/` (Tabs, DataTable, Dialog), die heute eigene Hover/Focus-Regeln schreiben
- Modify: `frontend/src/main.ts` (oder root-CSS-Import) — `states.css` einbinden

**Token-Vokabular (in `states.css`):**

```css
/* v4 State-Vokabular — Slice FE-Redesign-3
   Eine Quelle für interaktive State-Tokens, verwendet als Custom Properties.
   Jede Komponente konsumiert via Mixin-Klassen .v4-state-interactive
   oder .v4-state-selectable. */

:root {
  /* Rest */
  --v4-state-rest-bg: transparent;
  --v4-state-rest-border: var(--hairline);
  --v4-state-rest-fg: var(--text-primary);

  /* Hover */
  --v4-state-hover-bg: var(--surface-hover);
  --v4-state-hover-border: var(--hairline-strong, var(--hairline));
  --v4-state-hover-fg: var(--text-primary);

  /* Focus (Tastatur sichtbar) */
  --v4-state-focus-ring: var(--accent, currentColor);
  --v4-state-focus-ring-width: 2px;
  --v4-state-focus-ring-offset: 2px;

  /* Active / Pressed / Selected */
  --v4-state-active-bg: var(--accent-bg, var(--surface-hover));
  --v4-state-active-border: var(--accent, var(--hairline));
  --v4-state-active-fg: var(--accent-fg, var(--text-primary));

  /* Disabled */
  --v4-state-disabled-opacity: 0.45;
  --v4-state-disabled-cursor: not-allowed;
}

/* Mixin für Buttons/Items/Toggle-artige Components */
.v4-state-interactive {
  background: var(--v4-state-rest-bg);
  border: 1px solid var(--v4-state-rest-border);
  color: var(--v4-state-rest-fg);
  transition: background 80ms ease, border-color 80ms ease, color 80ms ease;
  cursor: pointer;
}

.v4-state-interactive:hover:not(:disabled):not([data-disabled]) {
  background: var(--v4-state-hover-bg);
  border-color: var(--v4-state-hover-border);
  color: var(--v4-state-hover-fg);
}

.v4-state-interactive:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: var(--v4-state-focus-ring-offset);
}

.v4-state-interactive:disabled,
.v4-state-interactive[data-disabled] {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
}

/* Mixin für Items in Listen / Sidebar / Dropdown */
.v4-state-selectable {
  background: var(--v4-state-rest-bg);
  color: var(--v4-state-rest-fg);
  transition: background 80ms ease;
  cursor: pointer;
}

.v4-state-selectable:hover:not(:disabled):not([data-disabled]),
.v4-state-selectable[data-highlighted]:not([data-disabled]) {
  background: var(--v4-state-hover-bg);
}

.v4-state-selectable:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: calc(-1 * var(--v4-state-focus-ring-width));
}

.v4-state-selectable[aria-current="page"],
.v4-state-selectable[aria-selected="true"],
.v4-state-selectable[data-state="active"] {
  background: var(--v4-state-active-bg);
  color: var(--v4-state-active-fg);
}

@media (prefers-reduced-motion: reduce) {
  .v4-state-interactive, .v4-state-selectable { transition: none; }
}
```

**Audit-Vorgehen:**

- [ ] **Step 1: Inventar**

```bash
cd /private/tmp/agora-fe-redesign-3/frontend
grep -lr ":hover" src/components/v4/ --include="*.vue" | sort
grep -lr ":focus-visible" src/components/v4/ --include="*.vue" | sort
grep -lr ":disabled" src/components/v4/ --include="*.vue" | sort
```

Notiere im Audit-Report jede Datei + welche State-Regeln sie heute schreibt.

- [ ] **Step 2: states.css schreiben + in main.ts importen**

- [ ] **Step 3: Per Komponente** (mind. Button, Input, Select, SegmentedControl, DropdownMenuItem, Tabs, SidebarItem):
  - Audit der existing State-Regeln
  - Hartkodierte Werte ersetzen durch Mixin-Klasse + ggf. komponentenspezifische Overrides via Custom-Property-Override
  - Smoke-Test im Worktree (existing Specs müssen grün bleiben)
  - Im Audit-Report dokumentieren

- [ ] **Step 4: Verification**

```bash
bun run typecheck && bun run test:coverage && bun run build && bun run lint
```

- [ ] **Step 5: Audit-Report `docs/2026-05-15-v4-state-audit.md`** mit Sektionen pro Component-Family und Diff-Liste.

- [ ] **Step 6: Worklog + code-review-graph update + Rückmeldung**

**Akzeptanzkriterien:**
- mind. 6 v4-Komponenten konsumieren `.v4-state-interactive` oder `.v4-state-selectable`
- Audit-Report listet vorher/nachher pro Komponente
- Alle bestehenden Tests grün
- Bundle-Delta ≈ 0 (CSS-Refactor)

---

## Slice 4 — Cmd+K Command-Palette

**Goal:** `Cmd+K` (Mac) / `Ctrl+K` (Win) öffnet eine Spotlight-artige Palette. Sie listet statische Nav-Commands (jede Route aus `router/index.ts`) plus dynamische Commands (offene Simulationen aus existing-Store, Recent-Commands aus localStorage). Auswahl navigiert per `router.push`.

**Worktree:** `/private/tmp/agora-fe-redesign-4` (Lead legt an, Branch `feat/fe-redesign-4-cmd-k` von `feat/fe-redesign-epic`).

**File Structure:**
- Create: `frontend/src/components/v4/shell/CommandPalette.vue`
- Create: `frontend/src/components/v4/shell/__tests__/CommandPalette.spec.ts`
- Create: `frontend/src/composables/useCommandPalette.ts` (Open/Close-State + Recent-Stack)
- Create: `frontend/src/composables/__tests__/useCommandPalette.spec.ts`
- Create: `frontend/src/stores/commandsStore.ts` (Pinia, statische + dynamische Commands)
- Create: `frontend/src/stores/__tests__/commandsStore.spec.ts`
- Create: `docs/2026-05-15-fe-redesign-slice-4-worklog.md`
- Modify: `frontend/src/components/v4/shell/AppShell.vue` — `<CommandPalette />` einbinden + global `Cmd+K`-Listener
- Modify: `frontend/src/components/v4/shell/Topbar.vue` — Search-Icon-Trigger (öffnet Palette)
- Modify: `frontend/src/locales/de.json` + `en.json` — `cmd.*`-Keys

**reka-ui Primitives:**
- `DialogRoot` + `DialogPortal` + `DialogOverlay` + `DialogContent` für den Modal-Layer
- `ComboboxRoot` + `ComboboxInput` + `ComboboxList` + `ComboboxItem` für die Liste

**useCommandPalette:**

```typescript
// composables/useCommandPalette.ts
import { ref } from 'vue'

const STORAGE_KEY = 'agora.cmdk.recent'

const isOpen = ref(false)
const query = ref('')
const recent = ref<string[]>(hydrateRecent())

function hydrateRecent(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function useCommandPalette() {
  function open(): void { isOpen.value = true; query.value = '' }
  function close(): void { isOpen.value = false }
  function toggle(): void { isOpen.value ? close() : open() }
  function pushRecent(commandId: string): void {
    const without = recent.value.filter((id) => id !== commandId)
    recent.value = [commandId, ...without].slice(0, 8)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(recent.value)) } catch {}
  }
  return { isOpen, query, recent, open, close, toggle, pushRecent }
}
```

**commandsStore (Pinia, static + dynamic):**

```typescript
// stores/commandsStore.ts
import { defineStore } from 'pinia'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export interface Command {
  id: string
  label: string
  group: 'nav' | 'sim' | 'report' | 'recent'
  action: () => void
}

export const useCommandsStore = defineStore('commands', () => {
  // dynamisch via Router + Runs-Store + Reports-Store
  const all = computed<Command[]>(() => {
    /* Static-Routes aus router/index.ts + open simulations aus useRunsStore + recent reports */
    return []
  })

  function filter(query: string): Command[] {
    const q = query.toLowerCase()
    if (!q) return all.value
    return all.value.filter((c) => c.label.toLowerCase().includes(q))
  }

  return { all, filter }
})
```

**CommandPalette.vue (Skelett):**

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent } from 'reka-ui'
import { ComboboxRoot, ComboboxInput, ComboboxList, ComboboxItem, ComboboxAnchor } from 'reka-ui'
import { useCommandPalette } from '@/composables/useCommandPalette'
import { useCommandsStore } from '@/stores/commandsStore'

const { isOpen, query, close, pushRecent } = useCommandPalette()
const store = useCommandsStore()
const { t } = useI18n()
const filtered = computed(() => store.filter(query.value))

function pickCommand(id: string): void {
  const cmd = store.all.find((c) => c.id === id)
  if (!cmd) return
  pushRecent(id)
  close()
  cmd.action()
}
</script>

<template>
  <DialogRoot v-model:open="isOpen">
    <DialogPortal>
      <DialogOverlay class="cmdk-overlay" />
      <DialogContent class="cmdk-content">
        <ComboboxRoot v-model:search-term="query" @update:model-value="pickCommand">
          <ComboboxAnchor>
            <ComboboxInput
              class="cmdk-input"
              :placeholder="t('cmd.placeholder')"
              autofocus
            />
          </ComboboxAnchor>
          <ComboboxList class="cmdk-list">
            <ComboboxItem
              v-for="cmd in filtered"
              :key="cmd.id"
              :value="cmd.id"
              class="cmdk-item v4-state-selectable"
            >
              <span class="cmdk-label">{{ cmd.label }}</span>
              <span class="cmdk-group">{{ cmd.group }}</span>
            </ComboboxItem>
          </ComboboxList>
        </ComboboxRoot>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
```

**Cmd+K-Trigger in AppShell.vue:**

```typescript
import { onMounted, onBeforeUnmount } from 'vue'
import { useCommandPalette } from '@/composables/useCommandPalette'
const { toggle } = useCommandPalette()
function onKeyDown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    toggle()
  }
}
onMounted(() => window.addEventListener('keydown', onKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))
```

**Tests (Minimum):**

- useCommandPalette.spec.ts (5): open/close/toggle, query reset on open, recent push max 8 + Dedup, localStorage-Persistenz
- commandsStore.spec.ts (4): includes static routes, filter by query, recent injection, ordering
- CommandPalette.spec.ts (3): rendert nicht wenn isOpen=false, rendert wenn open, ComboboxItem-Pick triggert action + pushRecent

**Tasks:**

- [ ] Step 1: useCommandPalette RED → GREEN + Commit
- [ ] Step 2: commandsStore RED → GREEN + Commit
- [ ] Step 3: CommandPalette.vue + Spec + Commit
- [ ] Step 4: AppShell-Integration + Topbar-Trigger + Commit
- [ ] Step 5: i18n-Keys + Commit
- [ ] Step 6: Verification + Worklog + code-review-graph update

**Akzeptanzkriterien:**
- `Cmd+K` öffnet/schließt Palette
- mind. alle Top-Level-Routes als statische Commands
- Recent-Stack max 8, persistent in localStorage
- Bundle-Delta ≤ +25 KB gz
- Alle Tests grün

**Push-Verbot beide Slices.**

**Rückmeldungs-Format:** wie Slice 5 Step 6.4 — Branch, Letzter Commit, Test-Delta, Bundle-Delta, Gaps, Worklog.
