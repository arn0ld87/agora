# FE-Redesign Slice 6 — Density-Toggle + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Density-Toggle (`comfortable`/`compact`) für App-Shell-Chrome via `data-density`-Attribut auf `<html>` + CSS-Custom-Property-Overrides. User-Setting in `localStorage` persistent. Toggle in Topbar erreichbar.

**Architecture:** Single-source-of-truth ist `data-density` auf `document.documentElement`. CSS-Variablen in `tokens-v3.css` werden im `[data-density="compact"]`-Selektor überschrieben (Padding/Font-Size für Body-Chrome, nicht für Touch-Targets). `useDensity`-Composable lädt initial aus localStorage, watcht und schreibt zurück.

**Tech Stack:** Vue 3.5, TS, CSS-Custom-Properties, Vitest.

**Spec-Quelle:** [`docs/plans/2026-05-15-frontend-redesign-shadcn-feel.md`](2026-05-15-frontend-redesign-shadcn-feel.md), Section "Slice 6".

**Worktree:** `/private/tmp/agora-fe-redesign-6` (Lead legt vor Dispatch an).
**Branch:** `feat/fe-redesign-6-density` basiert auf `feat/fe-redesign-epic` (post-Slice-1, Slice 2 nicht nötig — orthogonal).
**Push-Verbot.**

**Blocked by:** keine (orthogonal).

---

## File Structure

**Create:**
- `frontend/src/composables/useDensity.ts`
- `frontend/src/composables/__tests__/useDensity.spec.ts`
- `frontend/src/components/v4/shell/DensityToggle.vue`
- `frontend/src/components/v4/shell/__tests__/DensityToggle.spec.ts`

**Modify:**
- `frontend/src/assets/styles/tokens-v3.css` — `[data-density="compact"]`-Override-Block ergänzen.
- `frontend/src/components/v4/shell/Topbar.vue` — `<DensityToggle />` einbauen.
- `frontend/src/main.ts` (oder Bootstrap) — `useDensity().applyOnMount()` aufrufen, damit Reload-State applied wird, bevor Components mounten.

**Do NOT touch:** v4/forms, v4/data, sim-feed, andere shell-Komponenten außer Topbar.

---

## Pre-Flight

- [ ] **Step 0.1: Worktree-Check**

```bash
cd /private/tmp/agora-fe-redesign-6
git branch --show-current
test -L frontend/node_modules && echo OK || echo FEHLT
bun run typecheck && echo "Baseline typecheck OK"
```

---

## Task 1: useDensity Composable (RED → GREEN)

**Files:**
- Create: `frontend/src/composables/__tests__/useDensity.spec.ts`
- Create: `frontend/src/composables/useDensity.ts`

- [ ] **Step 1.1: Spec schreiben (RED)**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { useDensity } from '../useDensity'

const STORAGE_KEY = 'agora.density'

describe('useDensity', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-density')
  })

  it('Default ist comfortable, wenn nichts in localStorage', () => {
    const { density } = useDensity()
    expect(density.value).toBe('comfortable')
  })

  it('Hydrate aus localStorage', () => {
    localStorage.setItem(STORAGE_KEY, 'compact')
    const { density } = useDensity()
    expect(density.value).toBe('compact')
  })

  it('Korrupter Wert fällt auf comfortable', () => {
    localStorage.setItem(STORAGE_KEY, 'enormous')
    const { density } = useDensity()
    expect(density.value).toBe('comfortable')
  })

  it('setDensity aktualisiert localStorage + data-density-Attribut', () => {
    const { setDensity } = useDensity()
    setDensity('compact')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('compact')
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
  })

  it('applyOnMount setzt data-density aus aktuellem State', () => {
    localStorage.setItem(STORAGE_KEY, 'compact')
    const { applyOnMount } = useDensity()
    applyOnMount()
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
  })

  it('toggle wechselt comfortable<->compact', () => {
    const { density, toggle } = useDensity()
    expect(density.value).toBe('comfortable')
    toggle()
    expect(density.value).toBe('compact')
    toggle()
    expect(density.value).toBe('comfortable')
  })
})
```

- [ ] **Step 1.2: Tests rot laufen**

```bash
bun test -- --run src/composables/__tests__/useDensity.spec.ts
```
Expected: alle FAIL (Modul fehlt).

- [ ] **Step 1.3: Composable schreiben (GREEN)**

```typescript
/**
 * useDensity — Compact/Comfortable-Density-Toggle für App-Shell-Chrome.
 *
 * Slice FE-Redesign-6 · 2026-05-15
 *
 * Single-source-of-truth ist data-density auf document.documentElement.
 * CSS-Variablen-Overrides leben in tokens-v3.css.
 */

import { ref, watch } from 'vue'

export type Density = 'comfortable' | 'compact'

const STORAGE_KEY = 'agora.density'
const VALID: ReadonlyArray<Density> = ['comfortable', 'compact'] as const

function hydrate(): Density {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && VALID.includes(raw as Density)) return raw as Density
  } catch {
    // ignore
  }
  return 'comfortable'
}

const density = ref<Density>(hydrate())

let watcherInitialized = false
function ensureWatcher(): void {
  if (watcherInitialized) return
  watcherInitialized = true
  watch(density, (next) => {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Storage gesperrt
    }
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-density', next)
    }
  })
}

export function useDensity() {
  ensureWatcher()

  function setDensity(value: Density): void {
    density.value = value
  }

  function toggle(): void {
    density.value = density.value === 'comfortable' ? 'compact' : 'comfortable'
  }

  function applyOnMount(): void {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-density', density.value)
    }
  }

  return { density, setDensity, toggle, applyOnMount }
}
```

- [ ] **Step 1.4: Tests grün + Commit**

```bash
bun test -- --run src/composables/__tests__/useDensity.spec.ts
git add frontend/src/composables/useDensity.ts frontend/src/composables/__tests__/useDensity.spec.ts
git commit -m "feat(composables): useDensity (compact/comfortable + persistence)"
```

---

## Task 2: tokens-v3.css — Density-Overrides

**Files:**
- Modify: `frontend/src/assets/styles/tokens-v3.css`

- [ ] **Step 2.1: Override-Block hinzufügen**

Am Ende der Datei (nach den Default-Tokens) ergänzen:

```css
/* ============================================================
   Density: compact — Slice FE-Redesign-6
   Greift NUR auf Shell-Chrome-Spacing/Typo, NICHT auf
   Touch-Targets (Buttons bleiben ≥40px für a11y).
   ============================================================ */

[data-density="compact"] {
  /* Sidebar-Items */
  --sidebar-item-py: 4px;
  --sidebar-item-px: 10px;
  --sidebar-group-trigger-py: 4px;
  --sidebar-group-gap: 0;

  /* Topbar */
  --topbar-h: 44px;
  --topbar-px: 12px;

  /* DataTable */
  --table-cell-py: 6px;
  --table-cell-px: 10px;

  /* Body-Text-Scale leicht runter */
  --text-body-fs: 12px;
  --text-body-lh: 1.45;
}
```

> Annahme: `tokens-v3.css` definiert die obigen Variablen in der `:root`. Falls die Variablennamen anders sind (z. B. `--v3-sidebar-item-padding-y`), entsprechend angleichen. Vor Edit grep:
> ```bash
> grep -nE '^\s*--(sidebar|topbar|table|text-body)' frontend/src/assets/styles/tokens-v3.css
> ```
> Und für jeden gefundenen Var-Namen den Compact-Override schreiben.

- [ ] **Step 2.2: Konsumierende Komponenten verifizieren**

In Sidebar/Topbar/DataTable die Padding-Werte auf die obigen Variablen umstellen, falls noch hartkodiert.

- [ ] **Step 2.3: Commit**

---

## Task 3: DensityToggle.vue — Topbar-Integration

**Files:**
- Create: `frontend/src/components/v4/shell/DensityToggle.vue`
- Create: `frontend/src/components/v4/shell/__tests__/DensityToggle.spec.ts`
- Modify: `frontend/src/components/v4/shell/Topbar.vue`

- [ ] **Step 3.1: DensityToggle.vue**

```vue
<script setup lang="ts">
import { useDensity } from '@/composables/useDensity'

const { density, toggle } = useDensity()
</script>

<template>
  <button
    type="button"
    class="dt-root"
    :aria-pressed="density === 'compact'"
    :title="density === 'compact' ? 'Compact Mode aktiv' : 'Comfortable Mode aktiv'"
    @click="toggle"
  >
    <span class="dt-icon" aria-hidden="true">
      {{ density === 'compact' ? '▤' : '▦' }}
    </span>
    <span class="dt-label">
      {{ density === 'compact' ? 'Kompakt' : 'Komfort' }}
    </span>
  </button>
</template>

<style scoped>
.dt-root {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: transparent;
  border: 1px solid var(--hairline);
  border-radius: var(--r-2, 4px);
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 12px;
  cursor: pointer;
}

.dt-root:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}

.dt-root[aria-pressed="true"] {
  background: var(--accent-bg, var(--surface-hover));
  color: var(--accent, var(--text-primary));
}

.dt-root:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: 2px;
}

.dt-icon {
  font-size: 14px;
}
</style>
```

- [ ] **Step 3.2: Spec**

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import DensityToggle from '../DensityToggle.vue'

describe('DensityToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-density')
  })

  it('rendert Comfort-Label im Default', () => {
    const wrapper = mount(DensityToggle)
    expect(wrapper.text()).toContain('Komfort')
    expect(wrapper.find('button').attributes('aria-pressed')).toBe('false')
  })

  it('Klick toggled auf compact und setzt aria-pressed=true', async () => {
    const wrapper = mount(DensityToggle)
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('Kompakt')
    expect(wrapper.find('button').attributes('aria-pressed')).toBe('true')
    expect(document.documentElement.getAttribute('data-density')).toBe('compact')
    expect(localStorage.getItem('agora.density')).toBe('compact')
  })
})
```

- [ ] **Step 3.3: Topbar-Integration**

In `Topbar.vue` — DensityToggle rechts neben User-Menu oder existing Topbar-Actions einbinden (Position dem Lead überlassen, Worker prüft existing Layout-Pattern).

- [ ] **Step 3.4: Tests + Commit**

---

## Task 4: applyOnMount in App-Bootstrap

**Files:**
- Modify: `frontend/src/main.ts` (oder gleichwertiger Entry)

- [ ] **Step 4.1: useDensity().applyOnMount() aufrufen**

In `main.ts` vor `app.mount('#app')`:

```typescript
import { useDensity } from '@/composables/useDensity'
useDensity().applyOnMount()
```

> Damit ist `data-density="compact"` schon auf `<html>`, bevor Vue mountet — verhindert FOUC.

- [ ] **Step 4.2: Manueller Smoke**

```bash
bun run dev &
# Im Browser: Toggle klicken, reloaden → Compact bleibt
```

- [ ] **Step 4.3: Commit**

---

## Task 5: Verification + Worklog

- [ ] **Step 5.1: Gates**

```bash
cd /private/tmp/agora-fe-redesign-6/frontend
bun run typecheck && bun run test:coverage && bun run build && bun run lint
```

- [ ] **Step 5.2: Worklog** `docs/2026-05-15-fe-redesign-slice-6-worklog.md` analog Slice 1 Pattern.

- [ ] **Step 5.3: code-review-graph update + Rückmeldungs-Format**

```
Branch: feat/fe-redesign-6-density
Letzter Commit: <hash>
Test-Delta: +<N> (useDensity=6, DensityToggle=2)
Bundle-Delta: minimal (~<X> KB gz)
Visual-Smoke: toggle persistiert über Reload — verifiziert / nicht getestet
Gaps: <leer oder konkret, z.B. "Density wirkt noch nicht auf DataTable, weil var-Names dort hartkodiert sind — Followup">
Worklog: docs/2026-05-15-fe-redesign-slice-6-worklog.md
```

---

## Self-Review

- ✅ `data-density="compact"` auf `<html>` → Task 1
- ✅ localStorage `agora.density` → Task 1
- ✅ Affects Sidebar/Topbar/DataTable, nicht Buttons (touch-target 40 px bleibt) → Task 2 Constraint
- ✅ Toggle in Topbar → Task 3
- ⚠️ Dark/Light-Toggle (Spec hat es als "kommt nach Density" — out-of-scope für Slice 6).

**Type consistency:** `Density` Type-Alias, `density` ref, `setDensity`/`toggle`/`applyOnMount` Methoden — durchgängig.
