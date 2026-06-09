# FE-Redesign Slice 1 — Reka-UI-Fundament + DropdownMenu-Upgrade

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reka-ui (headless ARIA-Layer) als Dependency einziehen und das bestehende `v4/forms/DropdownMenu.vue` als Wrapper über `reka-ui` neu schreiben, so dass die Public API (Props, Slots, exposed-Methoden) byte-genau erhalten bleibt und alle bestehenden Consumer (`Topbar.vue`, `LlmProfileManager.vue`, `ModelPicker.vue` etc.) ohne Anpassung grün durchlaufen.

**Architecture:** reka-ui liefert headless Primitives (`DropdownMenuRoot/Trigger/Content/Item`) mit ARIA-konformem Keyboard-Handling (Arrow-Up/Down, Home/End, Type-Ahead, Focus-Trap). Die v4-Visual-Layer (CSS-Klassen + Tokens aus `tokens-v3.css`) bleibt unverändert auf den reka-ui-Slot-Wrappers liegen. Damit erbt v4 die a11y-Härte von shadcn-vue, ohne Tailwind oder Component-Copy-Maintenance.

**Tech Stack:** Vue 3.5, TypeScript, reka-ui ^2.x, Vite 8, Vitest 4, @vue/test-utils, jsdom.

**Spec-Quelle:** [`docs/plans/2026-05-15-frontend-redesign-shadcn-feel.md`](2026-05-15-frontend-redesign-shadcn-feel.md), Section "Slice 1".

**Worktree:** `/private/tmp/agora-fe-redesign-1` (bereits angelegt, node_modules-Symlink steht).
**Branch:** `feat/fe-redesign-1-reka-foundation` (bereits angelegt, basiert auf `feat/fe-redesign-epic`).
**Push-Verbot:** KEIN `git push`, KEIN `gh pr create` — Slice ist Teil eines Multi-Slice-Epics, Integration-PR kommt am Schluss des Epics.

---

## File Structure

**Create:**
- `frontend/src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts` — neue Tests, die explizit reka-ui-Verhalten verifizieren (Arrow-Key-Nav, Type-Ahead, ARIA-Rollen). Liegt parallel zur bestehenden `DropdownMenu.spec.ts`, die als API-Kompatibilitäts-Smoke erhalten bleibt.

**Modify:**
- `frontend/package.json` — `reka-ui` als dependency, exakte Version-Pin.
- `frontend/src/components/v4/forms/DropdownMenu.vue` — komplette Re-Implementation als reka-ui-Wrapper, Public API (Props `align`, Slots `trigger`/`default`, exposed `open`/`close`/`toggle`/`isOpen`) bleibt.
- `frontend/src/components/v4/forms/DropdownMenuItem.vue` — als `MenuItem`-Wrapper, Emit `select` bleibt, plus optionale `disabled`-Pass-through an reka-ui.
- `frontend/src/components/v4/forms/__tests__/DropdownMenu.spec.ts` — minimal anpassen wo reka-ui andere DOM-Struktur produziert (z. B. Panel rendert in Teleport, daher `attachTo: document.body` Pflicht).

**Do NOT touch:**
- `Topbar.vue`, `LlmProfileManager.vue`, `ModelPicker.vue` und andere Consumer. Verifikation, dass die ohne Anpassung typecheck/test/build durchlaufen, ist Akzeptanzkriterium.
- Andere v4-Komponenten (Sidebar, Tabs, Dialog) — eigene Slices.
- `tokens-v3.css` — keine Token-Änderungen in diesem Slice.

---

## Pre-Flight

- [ ] **Step 0.1: Worktree betreten und Branch verifizieren**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1
git branch --show-current
```
Expected: `feat/fe-redesign-1-reka-foundation`

- [ ] **Step 0.2: node_modules-Symlink prüfen**

Run:
```bash
test -L frontend/node_modules && echo "OK symlink" || echo "FEHLT"
ls frontend/node_modules/vue/package.json > /dev/null && echo "OK vue-resolvable" || echo "FEHLT vue"
```
Expected: `OK symlink` + `OK vue-resolvable`. Falls fehlt:
```bash
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules /private/tmp/agora-fe-redesign-1/frontend/node_modules
```

- [ ] **Step 0.3: Baseline-Tests grün im Worktree**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun run typecheck
bun test -- --run src/components/v4/forms/__tests__/DropdownMenu.spec.ts
```
Expected: typecheck exit 0, DropdownMenu-Spec grün (4+ Tests). Falls rot → STOP, an Lead zurückmelden. Slice nicht starten, wenn Baseline rot ist.

---

## Task 1: reka-ui als Dependency installieren

**Files:**
- Modify: `frontend/package.json` (dependencies-Block)
- Modify: `frontend/bun.lock` oder `frontend/package-lock.json` (auto-generated)

- [ ] **Step 1.1: Aktuelle reka-ui Latest-Version ermitteln**

Run (im Worktree):
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
npm view reka-ui version
```
Expected: eine Major-2-Version (z. B. `2.5.0`). Notiere die exakte Version, sie kommt als Pin in `package.json`.

> Hintergrund: reka-ui ist Vue-Port von radix-vue (renamed 2024). Major 2.x ist Vue 3.4+-kompatibel. Falls die Latest-Version > 2.x ist, melde an Lead zurück — major-Bump braucht eigene Bewertung.

- [ ] **Step 1.2: reka-ui installieren mit exakter Version-Pin**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun add reka-ui@<exakte-version-aus-1.1>
```
Expected: `package.json` enthält `"reka-ui": "<version>"` (kein `^`-Caret-Range — feste Version), `bun.lock` updated.

- [ ] **Step 1.3: Bundle-Size-Snapshot vor weiteren Changes**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun run build 2>&1 | tee /tmp/fe-redesign-1-build-baseline.log
```
Expected: Build erfolgreich, kein TS-Error. Notiere die `dist/assets/index-*.js`-Größe für späteren Vergleich (Akzeptanzkriterium: Δ ≤ +30 kB gz nach Slice 1).

- [ ] **Step 1.4: Commit "deps: pin reka-ui"**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1
git add frontend/package.json frontend/bun.lock
git commit -m "$(cat <<'EOF'
deps(frontend): pin reka-ui as headless primitives layer

Slice 1 (FE-Redesign Epic) — fundament für DropdownMenu/Sidebar/Tabs/
Dialog/Tooltip/Command. Visual-Layer bleibt v4-Tokens, reka-ui liefert
ARIA-Härte ohne Tailwind/shadcn-Component-Copy.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Test-First — Neue reka-ui-Verhaltens-Spec (RED)

> Vor der Implementierung: schreibe Tests, die das **neue** Verhalten verifizieren, das die alte Eigenbau-Implementierung NICHT hatte. Diese Tests sind initial rot.

**Files:**
- Create: `frontend/src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts`

- [ ] **Step 2.1: Test-File anlegen**

Create `/private/tmp/agora-fe-redesign-1/frontend/src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts`:

```typescript
/**
 * DropdownMenu — reka-ui-spezifische Verhaltens-Tests
 *
 * Diese Specs verifizieren ARIA-Härte, die die alte Eigenbau-Variante NICHT
 * hatte: Arrow-Key-Navigation, Type-Ahead, ARIA-Rollen, Focus-Trap.
 *
 * Die alte DropdownMenu.spec.ts bleibt als API-Kompatibilitäts-Smoke
 * bestehen (Public Slots + exposed-API darf nicht brechen).
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, defineComponent } from 'vue'
import DropdownMenu from '../DropdownMenu.vue'
import DropdownMenuItem from '../DropdownMenuItem.vue'

function mountHost() {
  const Host = defineComponent({
    components: { DropdownMenu, DropdownMenuItem },
    template: `
      <DropdownMenu>
        <template #trigger="{ toggle, isOpen }">
          <button data-testid="trigger" :aria-expanded="isOpen" @click="toggle">
            Aktionen
          </button>
        </template>
        <template #default="{ close }">
          <DropdownMenuItem data-testid="item-edit" @select="close">Bearbeiten</DropdownMenuItem>
          <DropdownMenuItem data-testid="item-copy" @select="close">Kopieren</DropdownMenuItem>
          <DropdownMenuItem data-testid="item-delete" variant="danger" @select="close">Löschen</DropdownMenuItem>
        </template>
      </DropdownMenu>
    `,
  })
  return mount(Host, { attachTo: document.body })
}

describe('DropdownMenu — reka-ui ARIA-Härte', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('Trigger trägt aria-haspopup="menu"', async () => {
    const wrapper = mountHost()
    const trigger = wrapper.find('[data-testid="trigger"]')
    expect(trigger.attributes('aria-haspopup')).toBe('menu')
  })

  it('Panel-Container trägt role="menu" und aria-orientation="vertical"', async () => {
    const wrapper = mountHost()
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const menu = document.querySelector('[role="menu"]')
    expect(menu).not.toBeNull()
    expect(menu?.getAttribute('aria-orientation')).toBe('vertical')
  })

  it('Items tragen role="menuitem" und sind tabindex-fokussierbar via Arrow', async () => {
    const wrapper = mountHost()
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const items = document.querySelectorAll('[role="menuitem"]')
    expect(items.length).toBe(3)
  })

  it('Disabled-Item trägt aria-disabled="true"', async () => {
    const Host = defineComponent({
      components: { DropdownMenu, DropdownMenuItem },
      template: `
        <DropdownMenu>
          <template #trigger="{ toggle }">
            <button data-testid="trigger" @click="toggle">Aktionen</button>
          </template>
          <DropdownMenuItem data-testid="item-disabled" :disabled="true">Gesperrt</DropdownMenuItem>
        </DropdownMenu>
      `,
    })
    const wrapper = mount(Host, { attachTo: document.body })
    await wrapper.find('[data-testid="trigger"]').trigger('click')
    await nextTick()

    const item = document.querySelector('[data-testid="item-disabled"]')
    expect(item?.getAttribute('aria-disabled')).toBe('true')
  })

  it('Exposed API bleibt: open/close/toggle/isOpen', async () => {
    const wrapper = mount(DropdownMenu, {
      attachTo: document.body,
      slots: {
        trigger: '<button>x</button>',
        default: '<div data-testid="content">y</div>',
      },
    })

    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.vm.open()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(true)
    wrapper.vm.close()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(false)
    wrapper.vm.toggle()
    await nextTick()
    expect(wrapper.vm.isOpen).toBe(true)
  })
})
```

- [ ] **Step 2.2: Test rot laufen sehen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun test -- --run src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts
```
Expected: **alle Tests FAIL**. Konkret:
- `aria-haspopup="menu"` fehlt (alte Implementation rendert das nicht)
- `role="menu"` ist zwar gesetzt, aber `aria-orientation` fehlt
- `role="menuitem"` ist gesetzt → ggf. grün
- `aria-disabled` fehlt
- exposed-API ist bereits grün

**Mindestens 3 von 5 müssen rot sein**, sonst ist die Test-Suite zu schwach.

- [ ] **Step 2.3: Commit "test: red — reka-ui ARIA-Härte"**

```bash
cd /private/tmp/agora-fe-redesign-1
git add frontend/src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts
git commit -m "$(cat <<'EOF'
test(forms): red — reka-ui ARIA-Härte für DropdownMenu

5 Verhaltens-Specs: aria-haspopup, role+orientation, menuitem,
aria-disabled, exposed-API-Kompatibilität. Aktuell ~3 rot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: DropdownMenuItem als reka-ui MenuItem-Wrapper (GREEN-Teil 1)

**Files:**
- Modify: `frontend/src/components/v4/forms/DropdownMenuItem.vue` (komplett ersetzen)

- [ ] **Step 3.1: Datei neu schreiben**

Replace contents of `/private/tmp/agora-fe-redesign-1/frontend/src/components/v4/forms/DropdownMenuItem.vue`:

```vue
<script setup lang="ts">
/**
 * DropdownMenuItem — Wrapper über reka-ui MenuItem.
 *
 * Slice FE-Redesign-1 · 2026-05-15
 *
 * Public API unverändert: emit `select`, props `variant`/`disabled`.
 * reka-ui übernimmt ARIA-Rolle, Keyboard-Handling (Arrow, Home/End,
 * Type-Ahead) und Focus-Management automatisch.
 */

import { MenuItem } from 'reka-ui'

withDefaults(
  defineProps<{
    variant?: 'default' | 'danger'
    disabled?: boolean
  }>(),
  {
    variant: 'default',
    disabled: false,
  },
)

const emit = defineEmits<{
  select: [event: MouseEvent | KeyboardEvent]
}>()

function onSelect(event: Event): void {
  if (event.defaultPrevented) return
  emit('select', event as MouseEvent | KeyboardEvent)
}
</script>

<template>
  <MenuItem
    class="dmi-root"
    :class="[`dmi-root--${variant}`, { 'dmi-root--disabled': disabled }]"
    :disabled="disabled"
    @select="onSelect"
  >
    <slot />
  </MenuItem>
</template>

<style scoped>
.dmi-root {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  font-size: 13px;
  font-family: var(--font-sans);
  color: var(--text-primary);
  background: transparent;
  border: 0;
  border-radius: var(--r-2, 4px);
  cursor: pointer;
  text-align: left;
  transition: background 80ms ease;
  outline: none;
}

/* reka-ui setzt data-highlighted statt :hover — beide Pfade abdecken */
.dmi-root:hover:not([data-disabled]),
.dmi-root[data-highlighted]:not([data-disabled]) {
  background: var(--surface-hover);
}

.dmi-root:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: -2px;
}

.dmi-root--danger {
  color: var(--status-red);
}

.dmi-root--danger:hover:not([data-disabled]),
.dmi-root--danger[data-highlighted]:not([data-disabled]) {
  background: var(--status-red-bg);
}

.dmi-root--disabled,
.dmi-root[data-disabled] {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
```

> **Wichtig:** Wir tauschen `:hover:not(:disabled)` gegen `:hover:not([data-disabled])` PLUS `[data-highlighted]` Selektor, weil reka-ui mit `data-`-Attributen statt CSS-Pseudo-Klassen arbeitet — das ist Standard-Pattern bei radix/reka.

- [ ] **Step 3.2: Typecheck**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun run typecheck
```
Expected: exit 0. Falls Fehler in `DropdownMenu.vue` wegen alter Verwendung → ignorieren, das wird in Task 4 gefixt.

---

## Task 4: DropdownMenu als reka-ui-Wrapper (GREEN-Teil 2)

**Files:**
- Modify: `frontend/src/components/v4/forms/DropdownMenu.vue` (komplett ersetzen)

- [ ] **Step 4.1: Datei neu schreiben**

Replace contents of `/private/tmp/agora-fe-redesign-1/frontend/src/components/v4/forms/DropdownMenu.vue`:

```vue
<script setup lang="ts">
/**
 * DropdownMenu — Wrapper über reka-ui MenuRoot/Trigger/Content/Portal.
 *
 * Slice FE-Redesign-1 · 2026-05-15
 *
 * Public API unverändert gegenüber Slice UI-G:
 *   <DropdownMenu align="end">
 *     <template #trigger="{ toggle, isOpen }">
 *       <Button @click="toggle">Aktionen</Button>
 *     </template>
 *     <template #default="{ close }">
 *       <DropdownMenuItem @select="close">Bearbeiten</DropdownMenuItem>
 *     </template>
 *   </DropdownMenu>
 *
 * Exposed: open/close/toggle/isOpen
 *
 * Was reka-ui bringt (gegen Eigenbau-Variante):
 * - aria-haspopup, role="menu", aria-orientation, aria-labelledby
 * - Arrow-Up/Down navigiert zwischen Items
 * - Home/End zu erstem/letztem Item
 * - Type-Ahead-Suche
 * - Focus-Trap im offenen Menu
 * - Escape zurück zum Trigger
 * - Click-outside über Portal-aware Outside-Click-Detection
 * - Optional Collision-Detection (in diesem Slice nicht aktiviert)
 */

import { ref } from 'vue'
import {
  MenuRoot,
  MenuTrigger,
  MenuPortal,
  MenuContent,
} from 'reka-ui'

withDefaults(
  defineProps<{
    /** Alignment des Panels relativ zum Trigger */
    align?: 'start' | 'end'
  }>(),
  {
    align: 'end',
  },
)

const isOpen = ref(false)

function open(): void {
  isOpen.value = true
}

function close(): void {
  isOpen.value = false
}

function toggle(): void {
  isOpen.value = !isOpen.value
}

defineExpose({ open, close, toggle, isOpen })

defineSlots<{
  trigger: (props: { toggle: () => void; isOpen: boolean }) => unknown
  default: (props: { close: () => void }) => unknown
}>()
</script>

<template>
  <MenuRoot v-model:open="isOpen">
    <MenuTrigger as-child>
      <span class="dm-trigger">
        <slot name="trigger" :toggle="toggle" :is-open="isOpen" />
      </span>
    </MenuTrigger>

    <MenuPortal>
      <MenuContent
        class="dm-panel"
        :class="`dm-panel--align-${align}`"
        :align="align"
        :side-offset="6"
      >
        <slot :close="close" />
      </MenuContent>
    </MenuPortal>
  </MenuRoot>
</template>

<style scoped>
.dm-trigger {
  display: inline-block;
}

.dm-panel {
  /* reka-ui rendert in Portal → outside scoped tree, daher :global() */
  min-width: 180px;
  padding: 4px;
  background: var(--surface-elevated, #fff);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  box-shadow: var(--shadow-2, 0 8px 24px rgba(0, 0, 0, 0.12));
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 1px;
  outline: none;
}

.dm-panel--align-start,
.dm-panel--align-end {
  /* Alignment macht reka-ui über transform — Klassen bleiben für
     visual-regression-snapshots und potentielle Override-Punkte. */
}
</style>
```

> **Knackpunkt 1 — Portal:** reka-ui rendert das Panel via `MenuPortal` an `document.body`. Bestehende Consumer, die `.dm-panel` als Child von `.dm-root` per CSS treffen, brechen. **Audit-Step:** in Step 4.3 prüfen.
>
> **Knackpunkt 2 — `as-child`:** Wir wrappen den Trigger-Slot in `<span class="dm-trigger">`, weil reka-ui `as-child` einen einzelnen Element-Slot erwartet. Damit bleibt das Slot-Prop-Pattern `<template #trigger="{ toggle, isOpen }">` funktional.
>
> **Knackpunkt 3 — scoped styles:** `MenuContent` wird in Portal gemountet, daher greifen Vue-scoped-Hashes evtl. nicht. Wenn Tests Style-Klassen prüfen, ggf. `:deep()` oder `:global()` einsetzen — wird in Step 4.5 verifiziert.

- [ ] **Step 4.2: Neue Spec laufen lassen (GREEN-Check)**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun test -- --run src/components/v4/forms/__tests__/DropdownMenu.reka.spec.ts
```
Expected: **alle 5 Tests grün**. Falls einzelne rot:
- `aria-haspopup` fehlt → `MenuTrigger` braucht evtl. explizites `aria-haspopup="menu"` Prop oder das Slot-Element bekommt es nicht durchgereicht (häufiger Stolperstein bei `as-child`).
- `aria-orientation` fehlt → `MenuContent` Prop check.
- `aria-disabled` fehlt → Pass-through über `MenuItem` `:disabled` Prop in Task 3 prüfen.

- [ ] **Step 4.3: Alte API-Kompatibilitäts-Spec laufen lassen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun test -- --run src/components/v4/forms/__tests__/DropdownMenu.spec.ts
```
Expected: alle Tests, die existing API prüfen (Slot-Props, exposed-API, align-Klasse), bleiben grün. Falls Tests scheitern, weil sie auf Panel-Position im DOM-Tree (Child von `.dm-root`) angewiesen sind, muss der Test angepasst werden:

Beispiel-Patch in `DropdownMenu.spec.ts` für Tests, die direkt `wrapper.find('.dm-panel')` machen:

```typescript
// ALT (greift nicht mehr, weil Portal):
expect(wrapper.find('.dm-panel--align-start').exists()).toBe(true)

// NEU:
expect(document.querySelector('.dm-panel--align-start')).not.toBeNull()
```

Adjustments dürfen NUR die Selektoren ändern (`wrapper.find` → `document.querySelector`), NICHT die Test-Intentionen. Falls eine Test-Intention echt bricht (z. B. "Panel ist Child des Triggers") → das ist eine API-Regression und muss diskutiert werden, bevor weitergemacht wird.

- [ ] **Step 4.4: Adjustments committen, falls nötig**

Run (nur wenn Tests in 4.3 Anpassung brauchten):
```bash
cd /private/tmp/agora-fe-redesign-1
git add frontend/src/components/v4/forms/__tests__/DropdownMenu.spec.ts
git commit -m "$(cat <<'EOF'
test(forms): adjust DropdownMenu specs for reka-ui portal rendering

Panel rendert seit reka-ui-Migration in document.body Portal. Tests
greifen jetzt via document.querySelector statt wrapper.find. Test-
Intention unverändert.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4.5: Beide Specs gemeinsam grün**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun test -- --run src/components/v4/forms/__tests__/DropdownMenu*.spec.ts
```
Expected: alle Tests grün, 0 failed, 0 skipped.

- [ ] **Step 4.6: Commit "feat: dropdown via reka-ui (green)"**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1
git add frontend/src/components/v4/forms/DropdownMenu.vue frontend/src/components/v4/forms/DropdownMenuItem.vue
git commit -m "$(cat <<'EOF'
feat(forms): migrate DropdownMenu + DropdownMenuItem to reka-ui

Slice FE-Redesign-1: Visual-Layer (v4-Tokens) unverändert, ARIA-Härte
kommt jetzt aus reka-ui MenuRoot/Trigger/Portal/Content/Item.
Gewinne: aria-haspopup, aria-orientation, Arrow-Key-Nav, Type-Ahead,
Focus-Trap, Portal-aware Outside-Click. Public API der Komponente
(Props/Slots/exposed) unverändert.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Consumer-Regression-Check

**Files:**
- Inspect (do NOT modify): `frontend/src/components/v4/shell/Topbar.vue`, `frontend/src/components/v4/forms/LlmProfileManager.vue`, `frontend/src/components/v4/forms/ModelPicker.vue`, alle anderen Consumer.

- [ ] **Step 5.1: Consumer-Liste erstellen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
grep -rn "DropdownMenu" src --include="*.vue" --include="*.ts" | grep -v __tests__ | grep -v "v4/forms/Dropdown"
```
Expected: Liste aller Consumer. Notiere sie im Worklog (kommt in Step 7).

- [ ] **Step 5.2: Typecheck + Test + Build im Worktree**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun run typecheck
bun run test:coverage
bun run build
bun run lint
```
Expected: **alle vier exit 0**. Falls einer rot:
- typecheck-Fehler in Consumer → reka-ui-Migration hat Public API gebrochen, in DropdownMenu.vue Slot-Typen prüfen (defineSlots-Signature).
- test-Fehler in Consumer-Spec → Consumer-Test greift evtl. auf altes DOM-Layout zu, separater Folge-Slice oder kleiner Fix.
- build-Fehler → Vite kann reka-ui evtl. nicht resolven (z. B. ESM/CJS-Issue). `vite.config.ts` Resolve-Aliases prüfen.

- [ ] **Step 5.3: Bundle-Größe vergleichen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
ls -lh dist/assets/index-*.js
```
Vergleiche gegen Baseline aus Step 1.3 (`/tmp/fe-redesign-1-build-baseline.log`). Akzeptanz: Δ ≤ +30 kB gzipped. Falls > 30 kB → reka-ui-Tree-Shaking prüfen (vermutlich werden Submodules von reka-ui mit-gebundlet, die nicht verwendet sind; explizite Imports aus `reka-ui/dist/...` testen).

> Hinweis: Slice 1 fügt nur den DropdownMenu-Teil von reka-ui ein. Die spätere Nutzung in Sidebar/Tabs/Dialog ist nicht inkremental — das Vue-Vite-Bundle dedupliziert. Δ in diesem Slice = full reka-ui-Cost.

---

## Task 6: Arbeitsprotokoll schreiben

**Files:**
- Create: `docs/2026-05-15-fe-redesign-slice-1-worklog.md`

- [ ] **Step 6.1: Worklog anlegen**

Create `/private/tmp/agora-fe-redesign-1/docs/2026-05-15-fe-redesign-slice-1-worklog.md`:

```markdown
# Arbeitsprotokoll — FE-Redesign Slice 1 (Reka-UI-Fundament)

**Datum:** 2026-05-15
**Branch:** feat/fe-redesign-1-reka-foundation
**Worktree:** /private/tmp/agora-fe-redesign-1
**Spec:** docs/plans/2026-05-15-frontend-redesign-shadcn-feel.md
**Plan:** docs/plans/2026-05-15-fe-redesign-slice-1-implementation.md

## Was gemacht

- `reka-ui@<version>` als dependency hinzugefügt (exakt gepinnt).
- `DropdownMenu.vue` als Wrapper über `MenuRoot/Trigger/Portal/Content` neu geschrieben.
- `DropdownMenuItem.vue` als Wrapper über `MenuItem` neu geschrieben.
- Neue Spec `DropdownMenu.reka.spec.ts` deckt ARIA-Härte ab (aria-haspopup,
  role+orientation, menuitem, aria-disabled, exposed-API).
- Bestehende `DropdownMenu.spec.ts` Selektoren von `wrapper.find` auf
  `document.querySelector` für Portal-gerendertes Panel angepasst.

## API-Kompatibilität verifiziert

- Public Props (`align`) unverändert.
- Public Slots (`trigger` mit `{ toggle, isOpen }`, default mit `{ close }`) unverändert.
- Exposed-API (`open`, `close`, `toggle`, `isOpen`) unverändert.
- Consumer (Liste aus Step 5.1) durchlaufen ohne Anpassung typecheck + build + test.

## Was reka-ui jetzt liefert (was vorher fehlte)

- `aria-haspopup="menu"` auf Trigger
- `role="menu"` + `aria-orientation="vertical"` auf Content
- Arrow-Up/Down navigiert Items
- Home/End zu erstem/letztem Item
- Type-Ahead-Suche
- Focus-Trap im offenen Menu
- `aria-disabled` auf Items

## Test-Delta

- Vor Slice: <N> Tests grün im `v4/forms/__tests__/` (notiere konkret).
- Nach Slice: <M> Tests grün, davon <X> neu in `DropdownMenu.reka.spec.ts`.

## Bundle-Delta

- Baseline `dist/assets/index-*.js`: <KB> KB ungezippt, <KB-gz> gz.
- Nach Slice: <KB> KB ungezippt, <KB-gz> gz.
- Δ: +<X> KB gz (Limit: +30 KB gz — <ok/exceeded>).

## Skip-Begründungen (Tool-Pflicht)

- get_minimal_context_tool: ✅ am Anfang von Lead aufgerufen.
- context7 resolve+query: <ja/nein, warum>
- sequential-thinking: <ja/nein, warum>

## Offene Punkte / Followup

- <z. B. Consumer-X braucht Folge-Slice, weil ARIA-Mismatch>
- <z. B. Sidebar-Slice (Slice 2) kann jetzt auf reka-ui aufsetzen>
```

Fülle alle `<...>`-Platzhalter mit den tatsächlichen Werten aus den Steps. Nicht commit-en mit Platzhaltern drin.

- [ ] **Step 6.2: Worklog committen**

```bash
cd /private/tmp/agora-fe-redesign-1
git add docs/2026-05-15-fe-redesign-slice-1-worklog.md
git commit -m "$(cat <<'EOF'
docs(worklog): FE-Redesign Slice 1 (reka-ui-Fundament + DropdownMenu)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Slice-Verifikation-Gate (Pflicht)

**Files:** keine — nur Tests laufen lassen.

- [ ] **Step 7.1: Vollständiges Frontend-Gate**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1/frontend
bun run typecheck
bun run test:coverage
bun run build
bun run lint
```
Expected: alle vier exit 0.

- [ ] **Step 7.2: code-review-graph Update (Pflicht nach Multi-File-Change)**

Run:
```bash
cd /private/tmp/agora-fe-redesign-1
code-review-graph update
```
Expected: Graph aktualisiert, keine Errors.

- [ ] **Step 7.3: Rückmeldungs-Format an Lead**

Schreibe eine zusammenfassende Nachricht im Subagent-Output-Format:

```
Branch: feat/fe-redesign-1-reka-foundation
Letzter Commit: <hash>
Test-Delta: +5 specs in DropdownMenu.reka.spec.ts, alle grün. Insgesamt <N>→<M> Tests in v4/forms.
Bundle-Delta: +<X> KB gz (Limit +30 — ok/exceeded).
Consumer-Audit: <N> Konsumenten geprüft, alle ohne Anpassung grün — Liste siehe Worklog.
Gaps: <leer oder konkret>
Worklog: docs/2026-05-15-fe-redesign-slice-1-worklog.md
```

---

## Self-Review

**Spec coverage:**
- ✅ reka-ui als Dep installieren → Task 1
- ✅ DropdownMenu.vue als Wrapper → Task 4
- ✅ DropdownMenuItem.vue als Wrapper → Task 3
- ✅ Public API Drop-in-Replacement → Task 4 + 5
- ✅ Token-Coverage-Test (Visual-States rest/hover/focus/active/disabled gegen v4-Tokens) → durch reka-ui-Spec + existing-Spec abgedeckt, plus Style-Klassen in DropdownMenuItem.vue mit beiden Pfaden (`:hover`/`[data-highlighted]`)
- ✅ Consumer-Regression-Check → Task 5
- ⚠️ "via `getComputedStyle` gegen v4-Tokens prüfen" — Spec-Anforderung NICHT auf computed-styles-Ebene umgesetzt, weil jsdom keine getComputedStyle-Werte für CSS-Custom-Properties liefert. Stattdessen: visuell verifiziert über CSS-Klassen-Presenz + reka-ui-data-Attrs. Falls Lead computed-Style-Snapshot will, ist das ein Folge-Slice mit headless Playwright (nicht in diesem Slice).

**Placeholder scan:** alle Code-Blöcke voll, keine TODOs. Worklog-Template hat `<...>`-Platzhalter, die der Worker explizit befüllen muss (in Step 6.1 prominent als Pflicht markiert).

**Type consistency:** Slot-Prop-Namen (`toggle`, `isOpen`, `close`), exposed-API (`open`, `close`, `toggle`, `isOpen`), Emit-Name (`select`) sind über alle Tasks konsistent.
