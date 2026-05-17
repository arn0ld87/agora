# FE-Redesign Slice 2 — Multi-Level-Sidebar mit Persistenz

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Die v4-Sidebar bekommt persistente Collapsible-Groups, eine Active-Trail-Detection aus `$route.matched` (statt Props), und die Breadcrumbs werden auto-derived. Damit "hält" das Menü beim Tieftauchen in Sub-Routes (`/settings/llm-routing`, `/v4/simulation/:id`) und der User verliert nie den Pfad nach oben.

**Architecture:** `useSidebarState` als Pinia-light Composable mit `localStorage`-Persistenz pro Group-Key. `SidebarGroup` wrappt `reka-ui CollapsibleRoot/Trigger/Content` und hört auf `useSidebarState`. `SidebarItem` setzt `aria-current="page"` über `$route.matched`. `Breadcrumbs` leitet den Trail aus `$route.matched` ab mit i18n-Key-Konvention `nav.<routeName>` (Fallback auf Props bleibt für Custom-Trails).

**Tech Stack:** Vue 3.5, TypeScript, reka-ui ^2.x (aus Slice 1), vue-router 5, vue-i18n 11, Vitest 4.

**Spec-Quelle:** [`docs/plans/2026-05-15-frontend-redesign-shadcn-feel.md`](2026-05-15-frontend-redesign-shadcn-feel.md), Section "Slice 2".

**Worktree:** `/private/tmp/agora-fe-redesign-2` (vom Lead vor Dispatch anzulegen).
**Branch:** `feat/fe-redesign-2-sidebar` basiert auf `feat/fe-redesign-1-reka-foundation` (NICHT auf `main` und NICHT auf `feat/fe-redesign-epic` direkt — Slice 1 muss durch sein, damit reka-ui verfügbar ist).
**Push-Verbot:** KEIN `git push`, KEIN `gh pr create`.

**Blocked by:** Slice 1 (reka-ui muss als Dep im Worktree resolvable sein).

---

## File Structure

**Create:**
- `frontend/src/composables/useSidebarState.ts` — Group-Expand-State + Active-Trail-Logik, localStorage-persistent.
- `frontend/src/composables/__tests__/useSidebarState.spec.ts` — Tests für State, Persistenz, Trail-Detection.
- `frontend/src/components/v4/shell/__tests__/SidebarGroup.spec.ts` — Tests für Collapsible-Verhalten + Auto-Open-bei-Active-Child.
- `frontend/src/components/v4/shell/__tests__/Breadcrumbs.spec.ts` — Tests für Auto-Derive aus Route.

**Modify:**
- `frontend/src/components/v4/shell/Sidebar.vue` — `useSidebarState` initialisieren, Layout unangetastet.
- `frontend/src/components/v4/shell/SidebarGroup.vue` — Collapsible-Wrapper, hört auf useSidebarState.
- `frontend/src/components/v4/shell/SidebarItem.vue` — `aria-current="page"` über `$route.matched`.
- `frontend/src/components/v4/shell/Breadcrumbs.vue` — Auto-Derive aus `$route.matched`, Props-Fallback bleibt.
- `frontend/src/locales/de.json` + `en.json` — `nav.*`-Keys für Route-Namen (nur die in Sidebar/Breadcrumbs verwendeten).

**Do NOT touch:**
- `Topbar.vue`, `PageHeader.vue`, `AppShell.vue` — eigene Slices/Polish.
- `router/index.ts` — keine Route-Änderungen.
- Andere v4-Komponenten — eigene Slices.

---

## Pre-Flight

- [ ] **Step 0.1: Worktree anlegen + Symlink (durch Lead vor Dispatch erledigt — Worker verifiziert)**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2
git branch --show-current
test -L frontend/node_modules && echo OK || echo FEHLT
node -e "require.resolve('reka-ui')" && echo "reka-ui resolvable" || echo "reka-ui FEHLT — Slice 1 nicht durch?"
```
Expected: Branch `feat/fe-redesign-2-sidebar`, Symlink OK, reka-ui resolvable. Falls reka-ui fehlt → STOP, Slice 1 ist Voraussetzung.

- [ ] **Step 0.2: Baseline grün**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun run typecheck
bun test -- --run src/components/v4/shell/__tests__/
```
Expected: typecheck exit 0, alle Shell-Tests grün. Falls rot → an Lead zurück.

---

## Task 1: Test-First — useSidebarState Composable (RED)

**Files:**
- Create: `frontend/src/composables/__tests__/useSidebarState.spec.ts`

- [ ] **Step 1.1: Test-File anlegen**

Create `frontend/src/composables/__tests__/useSidebarState.spec.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useSidebarState } from '../useSidebarState'

const STORAGE_KEY = 'agora.sidebar.v1'

describe('useSidebarState', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('Test 1: Default-State ist leere Map (alle Groups closed)', () => {
    const { isGroupOpen } = useSidebarState()
    expect(isGroupOpen('runs')).toBe(false)
    expect(isGroupOpen('settings')).toBe(false)
  })

  it('Test 2: toggleGroup öffnet und schließt eine Group', () => {
    const { isGroupOpen, toggleGroup } = useSidebarState()
    expect(isGroupOpen('runs')).toBe(false)
    toggleGroup('runs')
    expect(isGroupOpen('runs')).toBe(true)
    toggleGroup('runs')
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('Test 3: State persistiert in localStorage unter agora.sidebar.v1', () => {
    const { toggleGroup } = useSidebarState()
    toggleGroup('runs')
    const raw = localStorage.getItem(STORAGE_KEY)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    expect(parsed.runs).toBe(true)
  })

  it('Test 4: State wird aus localStorage hydratet bei neuem Composable-Aufruf', () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ settings: true }))
    const { isGroupOpen } = useSidebarState()
    expect(isGroupOpen('settings')).toBe(true)
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('Test 5: setGroupOpen erlaubt explizites Setzen (für Auto-Open-on-Active-Child)', () => {
    const { isGroupOpen, setGroupOpen } = useSidebarState()
    setGroupOpen('runs', true)
    expect(isGroupOpen('runs')).toBe(true)
    setGroupOpen('runs', false)
    expect(isGroupOpen('runs')).toBe(false)
  })

  it('Test 6: Korruptes localStorage-JSON wird ignoriert (graceful fallback)', () => {
    localStorage.setItem(STORAGE_KEY, 'this is not json')
    const { isGroupOpen } = useSidebarState()
    expect(isGroupOpen('runs')).toBe(false)
  })
})
```

- [ ] **Step 1.2: Tests rot laufen sehen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun test -- --run src/composables/__tests__/useSidebarState.spec.ts
```
Expected: **alle 6 Tests FAIL** mit "Cannot find module '../useSidebarState'".

- [ ] **Step 1.3: Commit "test: red — useSidebarState"**

```bash
cd /private/tmp/agora-fe-redesign-2
git add frontend/src/composables/__tests__/useSidebarState.spec.ts
git commit -m "$(cat <<'EOF'
test(composables): red — useSidebarState (persistence + toggle + hydrate)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: useSidebarState implementieren (GREEN)

**Files:**
- Create: `frontend/src/composables/useSidebarState.ts`

- [ ] **Step 2.1: Composable schreiben**

Create `frontend/src/composables/useSidebarState.ts`:

```typescript
/**
 * useSidebarState — Group-Expand-State mit localStorage-Persistenz.
 *
 * Slice FE-Redesign-2 · 2026-05-15
 *
 * Singleton-State (modul-level reactive Map), damit Sidebar und externe
 * Caller (z. B. Auto-Open-Logik in SidebarGroup) konsistent sind.
 *
 * Storage-Key versioniert: agora.sidebar.v1 — bei Schema-Bruch bumpen.
 */

import { reactive, watch } from 'vue'

const STORAGE_KEY = 'agora.sidebar.v1'

type GroupState = Record<string, boolean>

function hydrate(): GroupState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    const clean: GroupState = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v === 'boolean') clean[k] = v
    }
    return clean
  } catch {
    return {}
  }
}

const state = reactive<GroupState>(hydrate())

let watcherInitialized = false
function ensureWatcher(): void {
  if (watcherInitialized) return
  watcherInitialized = true
  watch(
    state,
    (next) => {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        // Quota voll, Privacy-Mode etc. — bewusst silent
      }
    },
    { deep: true },
  )
}

export function useSidebarState() {
  ensureWatcher()

  function isGroupOpen(key: string): boolean {
    return state[key] === true
  }

  function setGroupOpen(key: string, open: boolean): void {
    state[key] = open
  }

  function toggleGroup(key: string): void {
    state[key] = !state[key]
  }

  return { isGroupOpen, setGroupOpen, toggleGroup }
}
```

- [ ] **Step 2.2: Tests grün**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun test -- --run src/composables/__tests__/useSidebarState.spec.ts
```
Expected: **alle 6 grün**.

- [ ] **Step 2.3: Commit "feat: useSidebarState"**

```bash
cd /private/tmp/agora-fe-redesign-2
git add frontend/src/composables/useSidebarState.ts
git commit -m "$(cat <<'EOF'
feat(composables): add useSidebarState (persistent group expand-state)

Singleton reactive Map mit localStorage-Hydrate + auto-Persist.
Graceful fallback bei korruptem JSON oder gesperrtem Storage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: SidebarGroup mit reka-ui Collapsible (RED → GREEN)

**Files:**
- Create: `frontend/src/components/v4/shell/__tests__/SidebarGroup.spec.ts`
- Modify: `frontend/src/components/v4/shell/SidebarGroup.vue`

- [ ] **Step 3.1: Bestehende SidebarGroup lesen**

Run:
```bash
cat /private/tmp/agora-fe-redesign-2/frontend/src/components/v4/shell/SidebarGroup.vue
```

Notiere: Props-Signatur (z. B. `label`, `key`, ggf. `defaultOpen`?), Slot-Pattern, ob bereits ein Open/Close-State drin ist. Im Plan-Code-Block unten ist eine **Annahme** über die Public API — vor Implementation gegen die echte API abgleichen.

- [ ] **Step 3.2: Test-Datei anlegen**

Create `frontend/src/components/v4/shell/__tests__/SidebarGroup.spec.ts`:

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import SidebarGroup from '../SidebarGroup.vue'
import SidebarItem from '../SidebarItem.vue'

function buildRouter(currentPath: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: { template: '<div/>' } },
      { path: '/settings', name: 'Settings', component: { template: '<div/>' } },
      { path: '/settings/llm-routing', name: 'SettingsLlmRouting', component: { template: '<div/>' } },
    ],
  })
  router.push(currentPath)
  return router
}

const Host = defineComponent({
  components: { SidebarGroup, SidebarItem },
  props: { initialOpen: { type: Boolean, default: false } },
  template: `
    <SidebarGroup group-key="settings" label="Einstellungen">
      <SidebarItem route-name="SettingsLlmRouting" label="LLM Routing" />
    </SidebarGroup>
  `,
})

describe('SidebarGroup', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('Test 1: Group ist initial geschlossen, wenn keine Active-Child-Route', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const wrapper = mount(Host, { global: { plugins: [router] } })
    expect(wrapper.find('[data-testid="group-content"]').exists()).toBe(false)
  })

  it('Test 2: Group öffnet automatisch, wenn ein Child in $route.matched', async () => {
    const router = buildRouter('/settings/llm-routing')
    await router.isReady()
    const wrapper = mount(Host, { global: { plugins: [router] } })
    expect(wrapper.find('[data-testid="group-content"]').exists()).toBe(true)
  })

  it('Test 3: Klick auf Trigger toggled die Group und persistiert in localStorage', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const wrapper = mount(Host, { global: { plugins: [router] } })

    await wrapper.find('[data-testid="group-trigger"]').trigger('click')
    expect(wrapper.find('[data-testid="group-content"]').exists()).toBe(true)
    const stored = JSON.parse(localStorage.getItem('agora.sidebar.v1') || '{}')
    expect(stored.settings).toBe(true)
  })

  it('Test 4: Trigger trägt aria-expanded korrekt', async () => {
    const router = buildRouter('/')
    await router.isReady()
    const wrapper = mount(Host, { global: { plugins: [router] } })

    const trigger = wrapper.find('[data-testid="group-trigger"]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
  })
})
```

- [ ] **Step 3.3: Tests rot laufen sehen**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun test -- --run src/components/v4/shell/__tests__/SidebarGroup.spec.ts
```
Expected: alle 4 Tests rot (data-testids fehlen, Auto-Open-Logik fehlt).

- [ ] **Step 3.4: SidebarGroup neu schreiben**

Replace contents of `frontend/src/components/v4/shell/SidebarGroup.vue`:

```vue
<script setup lang="ts">
/**
 * SidebarGroup — Collapsible-Gruppe mit Auto-Open-on-Active-Child + Persistenz.
 *
 * Slice FE-Redesign-2 · 2026-05-15
 *
 * Verhalten:
 * - State wird über useSidebarState aus localStorage hydratet (agora.sidebar.v1).
 * - Bei mount: prüft $route.matched auf einen Child-RouteName und öffnet
 *   die Group automatisch, wenn match.
 * - Klick auf Trigger toggled und persistiert.
 */

import { computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { CollapsibleRoot, CollapsibleTrigger, CollapsibleContent } from 'reka-ui'
import { useSidebarState } from '@/composables/useSidebarState'

const props = withDefaults(
  defineProps<{
    /** Stabiler Key für localStorage-Persistenz. Muss innerhalb der Sidebar unique sein. */
    groupKey: string
    /** Sichtbarer Label-Text im Trigger. */
    label: string
    /** Optional: explizite Liste von Route-Names, die als "in dieser Group" gelten.
     *  Wenn omitted, wird die Auto-Open-Heuristik via Slot-Inspection nicht erkannt —
     *  Lead-Empfehlung: explizit setzen für saubere Active-Trail-Detection. */
    activeRouteNames?: string[]
  }>(),
  {
    activeRouteNames: () => [],
  },
)

const { isGroupOpen, setGroupOpen, toggleGroup } = useSidebarState()
const route = useRoute()

const isOpen = computed({
  get: () => isGroupOpen(props.groupKey),
  set: (v) => setGroupOpen(props.groupKey, v),
})

const hasActiveChild = computed(() => {
  if (props.activeRouteNames.length === 0) return false
  return route.matched.some((r) => {
    const name = r.name?.toString()
    return name !== undefined && props.activeRouteNames.includes(name)
  })
})

onMounted(() => {
  if (hasActiveChild.value) setGroupOpen(props.groupKey, true)
})

// Reaktiv: wenn Navigation in eine Active-Route führt, auto-öffnen.
watch(hasActiveChild, (active) => {
  if (active) setGroupOpen(props.groupKey, true)
})
</script>

<template>
  <CollapsibleRoot v-model:open="isOpen" class="sg-root">
    <CollapsibleTrigger
      class="sg-trigger"
      data-testid="group-trigger"
    >
      <span class="sg-label">{{ label }}</span>
      <span class="sg-chevron" :class="{ 'sg-chevron--open': isOpen }" aria-hidden="true">›</span>
    </CollapsibleTrigger>
    <CollapsibleContent class="sg-content" data-testid="group-content">
      <slot />
    </CollapsibleContent>
  </CollapsibleRoot>
</template>

<style scoped>
.sg-root {
  display: flex;
  flex-direction: column;
}

.sg-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: 0;
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  cursor: pointer;
  outline: none;
}

.sg-trigger:hover {
  background: var(--surface-hover);
}

.sg-trigger:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: -2px;
}

.sg-chevron {
  display: inline-block;
  transition: transform 120ms ease;
  font-size: 14px;
}

.sg-chevron--open {
  transform: rotate(90deg);
}

.sg-content {
  display: flex;
  flex-direction: column;
  padding: 2px 0 8px;
}
</style>
```

- [ ] **Step 3.5: Tests grün**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun test -- --run src/components/v4/shell/__tests__/SidebarGroup.spec.ts
```
Expected: alle 4 grün.

- [ ] **Step 3.6: Commit**

```bash
git add frontend/src/components/v4/shell/SidebarGroup.vue frontend/src/components/v4/shell/__tests__/SidebarGroup.spec.ts
git commit -m "$(cat <<'EOF'
feat(shell): SidebarGroup with reka-ui Collapsible + auto-open-on-active-child

Group-Open-State via useSidebarState (localStorage-persistent).
$route.matched-basierte Auto-Open-Heuristik via activeRouteNames-Prop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: SidebarItem mit aria-current via $route.matched

**Files:**
- Modify: `frontend/src/components/v4/shell/SidebarItem.vue`

- [ ] **Step 4.1: Bestehende Implementation lesen**

Run:
```bash
cat /private/tmp/agora-fe-redesign-2/frontend/src/components/v4/shell/SidebarItem.vue
```

Notiere die existing Props (vermutlich `routeName`, `label`, `icon`). Wenn `aria-current` schon gesetzt wird über `<router-link>` (das macht `router-link-active` automatisch), reicht ein Audit. Wenn nicht, wir setzen es explizit.

- [ ] **Step 4.2: Modify**

Im Template `<router-link>` so erweitern, dass es `aria-current="page"` setzt wenn aktiv. Vue Router setzt das **nicht automatisch** — der `router-link-active`-Klasse-Mechanismus reicht nicht für a11y.

Patch (Beispiel, an existing Datei adaptieren):

```vue
<router-link
  :to="{ name: routeName }"
  custom
  v-slot="{ href, navigate, isExactActive, isActive }"
>
  <a
    :href="href"
    class="si-link"
    :class="{ 'si-link--active': isExactActive || isActive }"
    :aria-current="isExactActive ? 'page' : (isActive ? 'true' : undefined)"
    @click="navigate"
  >
    <slot name="icon" />
    <span class="si-label">{{ label }}</span>
  </a>
</router-link>
```

> `isExactActive` = exakt diese Route. `isActive` = diese Route ist ein Vorfahr in `$route.matched` (z. B. `/settings` aktiv wenn man auf `/settings/llm-routing` ist).
> Konvention: `aria-current="page"` nur für die exakt aktive Route. Trail-Anker bekommen `aria-current="true"`.

- [ ] **Step 4.3: Quick-Smoke (kein eigener Spec-File, weil SidebarItem ggf. schon Tests hat — wenn nicht: ergänzen)**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun test -- --run src/components/v4/shell/__tests__/SidebarItem.spec.ts 2>/dev/null || echo "Kein existing spec — minimaler Smoke folgt"
```

Falls kein Spec existiert, kleinen Smoke ergänzen:

```typescript
// frontend/src/components/v4/shell/__tests__/SidebarItem.spec.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import SidebarItem from '../SidebarItem.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'Dashboard', component: { template: '<div/>' } },
    { path: '/x', name: 'X', component: { template: '<div/>' } },
  ],
})

describe('SidebarItem', () => {
  it('setzt aria-current="page" auf aktiver Route', async () => {
    await router.push('/x')
    await router.isReady()
    const wrapper = mount(SidebarItem, {
      props: { routeName: 'X', label: 'X' },
      global: { plugins: [router] },
    })
    expect(wrapper.find('a').attributes('aria-current')).toBe('page')
  })

  it('setzt kein aria-current, wenn Route inaktiv', async () => {
    await router.push('/')
    await router.isReady()
    const wrapper = mount(SidebarItem, {
      props: { routeName: 'X', label: 'X' },
      global: { plugins: [router] },
    })
    expect(wrapper.find('a').attributes('aria-current')).toBeUndefined()
  })
})
```

- [ ] **Step 4.4: Test + Commit**

```bash
bun test -- --run src/components/v4/shell/__tests__/SidebarItem.spec.ts
git add frontend/src/components/v4/shell/SidebarItem.vue frontend/src/components/v4/shell/__tests__/SidebarItem.spec.ts
git commit -m "$(cat <<'EOF'
feat(shell): SidebarItem sets aria-current via vue-router v-slot

isExactActive → page, isActive → true. Trail-Anker bekommen Anker-
aria-current, Endknoten bekommt "page" — a11y-konform.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Breadcrumbs auto-derived aus $route.matched

**Files:**
- Modify: `frontend/src/components/v4/shell/Breadcrumbs.vue`
- Create: `frontend/src/components/v4/shell/__tests__/Breadcrumbs.spec.ts`
- Modify: `frontend/src/locales/de.json`, `en.json` (nur die in Sidebar-Routes verwendeten `nav.*`-Keys)

- [ ] **Step 5.1: i18n-Keys ergänzen**

In `de.json` (innerhalb passendem Top-Level-Key wie `nav`):

```json
{
  "nav": {
    "Dashboard": "Dashboard",
    "Runs": "Läufe",
    "RunDetail": "Lauf-Details",
    "Settings": "Einstellungen",
    "SettingsGeneral": "Allgemein",
    "SettingsLlmRouting": "LLM-Routing",
    "SettingsLlmProviders": "LLM-Provider"
  }
}
```

`en.json` analog mit englischen Strings. Die genauen Keys aus `router/index.ts` extrahieren — nur die, die in Sidebar erreichbar sind (Settings-Family + Dashboard + Runs).

- [ ] **Step 5.2: Test schreiben (RED)**

Create `frontend/src/components/v4/shell/__tests__/Breadcrumbs.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createI18n } from 'vue-i18n'
import Breadcrumbs from '../Breadcrumbs.vue'

function build(currentPath: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Dashboard', component: { template: '<div/>' } },
      {
        path: '/settings',
        name: 'Settings',
        component: { template: '<div/>' },
        children: [
          { path: 'llm-routing', name: 'SettingsLlmRouting', component: { template: '<div/>' } },
        ],
      },
    ],
  })
  const i18n = createI18n({
    legacy: false,
    locale: 'de',
    messages: {
      de: {
        nav: {
          Dashboard: 'Dashboard',
          Settings: 'Einstellungen',
          SettingsLlmRouting: 'LLM-Routing',
        },
      },
    },
  })
  return { router, i18n, push: (p: string) => router.push(p) }
}

describe('Breadcrumbs auto-derived', () => {
  it('rendert Trail aus $route.matched mit i18n-Labels', async () => {
    const { router, i18n } = build('/settings/llm-routing')
    await router.push('/settings/llm-routing')
    await router.isReady()
    const wrapper = mount(Breadcrumbs, {
      global: { plugins: [router, i18n] },
    })
    const text = wrapper.text()
    expect(text).toContain('Einstellungen')
    expect(text).toContain('LLM-Routing')
  })

  it('letzter Crumb hat aria-current="page"', async () => {
    const { router, i18n } = build('/settings/llm-routing')
    await router.push('/settings/llm-routing')
    await router.isReady()
    const wrapper = mount(Breadcrumbs, {
      global: { plugins: [router, i18n] },
    })
    const lastCrumb = wrapper.findAll('[data-crumb]').at(-1)
    expect(lastCrumb?.attributes('aria-current')).toBe('page')
  })

  it('Props-Fallback überschreibt Auto-Derive', async () => {
    const { router, i18n } = build('/')
    await router.isReady()
    const wrapper = mount(Breadcrumbs, {
      props: {
        items: [
          { label: 'Custom A' },
          { label: 'Custom B' },
        ],
      },
      global: { plugins: [router, i18n] },
    })
    expect(wrapper.text()).toContain('Custom A')
    expect(wrapper.text()).toContain('Custom B')
  })
})
```

- [ ] **Step 5.3: Tests rot laufen sehen**

Run:
```bash
bun test -- --run src/components/v4/shell/__tests__/Breadcrumbs.spec.ts
```
Expected: alle 3 rot (Auto-Derive fehlt, Props-Fallback evtl. schon da).

- [ ] **Step 5.4: Breadcrumbs umschreiben**

Bestehende `Breadcrumbs.vue` lesen, dann so umbauen, dass:
- Wenn `items`-Prop gesetzt → wie bisher.
- Wenn nicht → Trail aus `$route.matched.filter(r => r.name)` ableiten, `nav.<name>`-Key via `t()` lookup. Letzter Crumb bekommt `aria-current="page"`.

Skeleton (an existing Datei anpassen):

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    items?: Array<{ label: string; to?: string }>
  }>(),
  { items: undefined },
)

const route = useRoute()
const { t, te } = useI18n()

const derivedItems = computed(() => {
  return route.matched
    .filter((r) => r.name !== undefined)
    .map((r) => {
      const name = r.name!.toString()
      const key = `nav.${name}`
      const label = te(key) ? t(key) : name
      return { label, to: r.path }
    })
})

const crumbs = computed(() => props.items ?? derivedItems.value)
</script>

<template>
  <nav class="bc-root" aria-label="Breadcrumb">
    <ol class="bc-list">
      <li
        v-for="(c, idx) in crumbs"
        :key="idx"
        class="bc-item"
        data-crumb
        :aria-current="idx === crumbs.length - 1 ? 'page' : undefined"
      >
        <router-link v-if="c.to && idx < crumbs.length - 1" :to="c.to">{{ c.label }}</router-link>
        <span v-else>{{ c.label }}</span>
        <span v-if="idx < crumbs.length - 1" class="bc-sep" aria-hidden="true">/</span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.bc-list {
  display: flex;
  gap: 6px;
  list-style: none;
  padding: 0;
  margin: 0;
}

.bc-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.bc-item:last-child {
  color: var(--text-primary);
}

.bc-sep {
  color: var(--text-tertiary, var(--text-secondary));
}
</style>
```

- [ ] **Step 5.5: Tests grün + Commit**

```bash
bun test -- --run src/components/v4/shell/__tests__/Breadcrumbs.spec.ts
git add frontend/src/components/v4/shell/Breadcrumbs.vue frontend/src/components/v4/shell/__tests__/Breadcrumbs.spec.ts frontend/src/locales/de.json frontend/src/locales/en.json
git commit -m "$(cat <<'EOF'
feat(shell): Breadcrumbs auto-derived from \$route.matched + i18n

nav.<RouteName>-Key-Konvention, te()-Fallback auf Route-Name.
Last-Crumb bekommt aria-current="page". Props-Override bleibt für
Custom-Trails erhalten.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Sidebar.vue Verdrahtung verifizieren

**Files:**
- Inspect (modify nur falls nötig): `frontend/src/components/v4/shell/Sidebar.vue`

- [ ] **Step 6.1: Audit**

Run:
```bash
cat /private/tmp/agora-fe-redesign-2/frontend/src/components/v4/shell/Sidebar.vue
```

Prüfen:
- Werden SidebarGroup-Children mit `group-key` und `:active-route-names` aufgerufen? Falls nein → ergänzen.
- Beispiel für Settings-Family:

```vue
<SidebarGroup
  group-key="settings"
  :label="$t('nav.Settings')"
  :active-route-names="['Settings', 'SettingsGeneral', 'SettingsLlmRouting', 'SettingsLlmProviders', 'SettingsIntegrations', 'SettingsUsersTeams', 'SettingsApiKeys', 'SettingsAuditLogs']"
>
  <SidebarItem route-name="SettingsGeneral" :label="$t('nav.SettingsGeneral')" />
  <SidebarItem route-name="SettingsLlmRouting" :label="$t('nav.SettingsLlmRouting')" />
  ...
</SidebarGroup>
```

- [ ] **Step 6.2: Lokal smoken**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun run dev &
DEV_PID=$!
sleep 5
# Open http://localhost:5173/settings/llm-routing in Browser manuell
# Visuell prüfen:
# - Settings-Group ist offen
# - LLM-Routing-Item hat Active-Style
# - Breadcrumb zeigt: Einstellungen > LLM-Routing
# - Refresh: Settings bleibt offen (localStorage)
kill $DEV_PID
```

Falls möglich, headless Playwright-Smoke als Folge-Slice — in Slice 2 nicht zwingend.

- [ ] **Step 6.3: Verification-Gate**

Run:
```bash
cd /private/tmp/agora-fe-redesign-2/frontend
bun run typecheck && bun run test:coverage && bun run build && bun run lint
```
Expected: alle exit 0.

- [ ] **Step 6.4: Commit (falls Sidebar.vue angefasst)**

---

## Task 7: Arbeitsprotokoll + Verification-Gate

**Files:**
- Create: `docs/2026-05-15-fe-redesign-slice-2-worklog.md`

- [ ] **Step 7.1: Worklog** (Template analog Slice 1, mit Sektion "Was useSidebarState/Auto-Open kann", "Test-Delta", "Bundle-Delta", "Skip-Begründungen", "Offene Punkte").

- [ ] **Step 7.2: code-review-graph update**

```bash
cd /private/tmp/agora-fe-redesign-2
code-review-graph update
```

- [ ] **Step 7.3: Rückmeldung an Lead**

```
Branch: feat/fe-redesign-2-sidebar
Letzter Commit: <hash>
Test-Delta: +<N> specs (useSidebarState=6, SidebarGroup=4, SidebarItem=2, Breadcrumbs=3)
Bundle-Delta: <X> KB gz (Erwartung: minimal, da reka-ui-Collapsible bereits durch Slice 1 inkl.)
Visual-Smoke: localStorage-Persistenz manuell verifiziert / failed
Gaps: <leer oder konkret>
Worklog: docs/2026-05-15-fe-redesign-slice-2-worklog.md
```

---

## Self-Review

**Spec coverage:**
- ✅ SidebarGroup mit reka-ui Collapsible + Auto-Open-bei-Active-Child → Task 3
- ✅ useSidebarState persistiert in localStorage (`agora.sidebar.v1`) → Task 1 + 2
- ✅ SidebarItem `aria-current="page"` über `$route.matched` → Task 4
- ✅ Breadcrumbs auto-derived aus `$route.matched`, Props-Fallback bleibt, i18n-Key-Konvention `nav.<routeName>` → Task 5
- ⚠️ "Sidebar collapsed-Modus (Icon-only) hinter Feature-Flag" — Spec sagt "optional, Slice-4-Vorgriff". In Slice 2 NICHT umgesetzt — bewusst out-of-scope, dokumentiere im Worklog unter "Offene Punkte".
- ⚠️ Smoke-Test der Navigation `/dashboard → /settings/llm-routing → /v4/simulation/:id` — Plan deckt Unit-Test-Level ab (SidebarGroup-Auto-Open + SidebarItem-aria-current + Breadcrumbs-Trail), E2E-Navigation-Smoke ist Folge-Slice (Playwright M11.4-Erweiterung), nicht hier.

**Placeholder scan:** alle Code-Blöcke voll. SidebarItem-Patch in Task 4 ist explizit als "an existing Datei adaptieren" markiert, weil ich die existing Public API der Komponente nicht ungelesen ersetzen will — Worker muss Step 4.1 ernst nehmen.

**Type consistency:** `groupKey`/`group-key`, `activeRouteNames`/`active-route-names`, `routeName`/`route-name` — vue's kebab-case-Konvention durchgängig.
