# v4 Step Event Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `next-step` and `go-back` events on the three v4 step wrapper views so the canonical router transitions (`StepGraphBuild → StepEnvSetup → StepSimulation`) work again after the PR #849 regression.

**Architecture:** Each wrapper view owns one or two small local handlers that translate exactly one child event into a single named `router.push(...)`. No shared composable, no refactor of the wrapper hierarchy, no changes to the embedded step components or to logging/status wiring. Three focused Vitest specs cover the new navigation; the broad smoke suite `StepWrapperViews.spec.ts` stays untouched.

**Tech Stack:** Vue 3 + `<script setup lang="ts">`, Vue Router 4 (`useRouter`, `useRoute`), `@vue/test-utils` 2, Vitest 4, Pinia, `vue-i18n`, Bun-based frontend toolchain (`bun run test`, `bun run check`), shared pre-push gate (`scripts/pre-push-gate.sh frontend`).

## Global Constraints

- Repo path inside the worktree: `/Volumes/T7/Projekte/agora/.claude/worktrees/fix-v4-step-event-wiring`.
- Branch: `fix/v4-step-event-wiring` (already cut from `main`).
- Frontend checks: `bun run test`, `bun run check`, `bash scripts/pre-push-gate.sh frontend`.
- Backend, schema, contract gates do not run for this slice (frontend-only).
- No edits to `main`, no `--no-verify`, push only after the read-only reviewer agent (`agora-opus-reviewer`) returns `APPROVE`.
- Commit messages: Conventional Commits, English, single line unless body needed, always `Co-Authored-By: Claude <noreply@anthropic.com>`.
- PR template expectations: include the CHANGELOG entry in the PR body.
- Vue Router route names (verified): `StepGraphBuild` (`/v4/graph-build/:projectId`), `StepEnvSetup` (`/v4/env-setup/:projectId`), `StepSimulation` (`/v4/simulation/:simulationId`).
- The child component `Step2EnvSetup.vue` emits `next-step` with the flat payload `{ simulationId, maxRounds?, simulationDays? }` (verified at `Step2EnvSetup.vue:271`). It emits `go-back` with no payload at `:339`.
- The child component `Step3Simulation.vue` emits `go-back` with no payload at `:493`.

## File Structure

- Modify `frontend/src/views/v4/steps/StepGraphBuildView.vue` — add `@next-step` listener and `handleNextStep` mapping to `StepEnvSetup`.
- Modify `frontend/src/views/v4/steps/StepEnvSetupView.vue` — bind `useRouter`, add `@next-step` and `@go-back` listeners with mappings to `StepSimulation` and `StepGraphBuild`.
- Modify `frontend/src/views/v4/steps/StepSimulationView.vue` — add `@go-back` listener with mapping to `StepEnvSetup`.
- Modify `frontend/src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts` — add a router navigation test for `next-step`.
- Create `frontend/src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts` — three cases for `next-step` success, `next-step` guard, and `go-back`.
- Create `frontend/src/views/v4/steps/__tests__/StepSimulationView.spec.ts` — one case for `go-back`.
- Modify `CHANGELOG.md` — single entry referencing Issue #850 and the wrapper views.

The existing `StepWrapperViews.spec.ts` stays as-is. The reproducers use `vi.mock('vue-router', …)` with a stub spy on `push` and child component stubs that re-emit events on demand.

---

## Task 1: Prep workspace and verify baseline

**Files:** none (preflight only).

**Interfaces:**
- Consumes: existing worktree state (`fix/v4-step-event-wiring`).
- Produces: known-good baseline tests against unmodified code.

- [ ] **Step 1: Confirm working tree and branch**

Run:

```bash
git rev-parse --show-toplevel
git status --short --branch
```

Expected: working tree clean other than the spec commit on branch `fix/v4-step-event-wiring`.

- [ ] **Step 2: Confirm tooling**

Run:

```bash
cd frontend && bun --version && (bun run test --version || true)
```

Expected: Bun version prints; Vitest available via the project script.

- [ ] **Step 3: Run the baseline wrapper specs**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts \
  src/views/v4/steps/__tests__/StepWrapperViews.spec.ts
```

Expected: all 21 tests pass (2 files).

- [ ] **Step 4: No commit**

This task is verification only. No commit needed.

---

## Task 2: RED — fail new navigation case on `StepGraphBuildView`

**Files:**
- Modify: `frontend/src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts:1-102`
- Reference: `frontend/src/views/v4/steps/StepGraphBuildView.vue:5-35` (renders `<Step1GraphBuild>`).

**Interfaces:**
- Consumes: `StepGraphBuildView` props `{ projectId: string }`.
- Produces: failing test asserting `router.push({ name: 'StepEnvSetup', params: { projectId: 'project_42' } })` after a child `next-step` emit.

- [ ] **Step 1: Append a new test file-scope module**

Open `frontend/src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts` and make it import `useRouter` indirectly through a module-level mock. Add at the top of the file (after the existing imports) a typed router-spy holder:

```ts
const routerPush = vi.hoisted(() => vi.fn())
```

Change the existing `vi.mock('vue-router', …)` line (currently mock for `useRouter` only with `replace`) to include `useRoute` (needed elsewhere later, but added here for consistency) and to expose the shared `push`:

```ts
vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: vi.fn(), push: routerPush }),
  useRoute: () => ({ name: 'StepGraphBuild', params: {} }),
}))
```

Keep the rest of the mocks unchanged.

- [ ] **Step 2: Add a router-push assertion test**

Insert as the last `it(...)` inside the existing `describe('StepGraphBuildView', …)` block:

```ts
  it('leitet ein next-step vom Child auf StepEnvSetup weiter', async () => {
    routerPush.mockClear()
    const wrapper = mount(StepGraphBuildView, {
      props: { projectId: 'project_42' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          GraphPanel: true,
          Step1GraphBuild: {
            name: 'Step1GraphBuild',
            props: ['projectData', 'currentPhase', 'ontologyProgress', 'buildProgress', 'graphData', 'systemLogs'],
            emits: ['next-step'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper.getComponent({ name: 'Step1GraphBuild' }).vm.$emit('next-step')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepEnvSetup',
      params: { projectId: 'project_42' },
    })
  })
```

- [ ] **Step 3: Run the new test in isolation**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts
```

Expected: three tests run, the new one fails with `expected "replace" mock to be called…` or similar — the assertion sees zero or unmatched `push` calls.

- [ ] **Step 4: Commit the failing test**

```bash
cd /Volumes/T7/Projekte/agora/.claude/worktrees/fix-v4-step-event-wiring
git add frontend/src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts
git commit -m $'test(frontend): cover next-step navigation on StepGraphBuildView\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, no production code changed yet.

---

## Task 3: GREEN — wire `next-step` on `StepGraphBuildView`

**Files:**
- Modify: `frontend/src/views/v4/steps/StepGraphBuildView.vue:5-35, 51-88`

**Interfaces:**
- Consumes: `StepGraphBuildView` props `{ projectId: string }`, existing `useGraphBuildPipeline` composable.
- Produces: handler `handleNextStep()` that calls `router.push({ name: 'StepEnvSetup', params: { projectId: props.projectId } })`.

- [ ] **Step 1: Update the template**

In `StepGraphBuildView.vue`, add `@next-step="handleNextStep"` to the `<Step1GraphBuild … />` element (line 26):

```html
    <Step1GraphBuild
      :currentPhase="currentPhase"
      :projectData="projectData"
      :ontologyProgress="ontologyProgress"
      :buildProgress="buildProgress"
      :graphData="graphData"
      :systemLogs="systemLogs"
      @next-step="handleNextStep"
    />
```

- [ ] **Step 2: Add the handler**

Inside `<script setup lang="ts">`, after the existing `const router = useRouter()` declaration, add:

```ts
function handleNextStep(): void {
  void router.push({
    name: 'StepEnvSetup',
    params: { projectId: props.projectId },
  })
}
```

- [ ] **Step 3: Re-run the focused spec**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts
```

Expected: three tests pass including the new `next-step` case.

- [ ] **Step 4: Re-run the broad wrapper suite to confirm no collateral damage**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepWrapperViews.spec.ts
```

Expected: 18 existing tests pass unchanged.

- [ ] **Step 5: Commit the GREEN state**

```bash
git add frontend/src/views/v4/steps/StepGraphBuildView.vue
git commit -m $'fix(frontend): handle next-step on StepGraphBuildView\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, single production file changed.

---

## Task 4: RED — create `StepEnvSetupView.spec.ts` with three failing cases

**Files:**
- Create: `frontend/src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts`

**Interfaces:**
- Consumes: `StepEnvSetupView` props `{ projectId: string }`.
- Produces: three failing tests:
  1. `next-step` with `{ simulationId: 'sim_x' }` → `router.push({ name: 'StepSimulation', params: { simulationId: 'sim_x' } })`.
  2. `next-step` with `{ simulationId: '' }` → no `router.push` call.
  3. `go-back` → `router.push({ name: 'StepGraphBuild', params: { projectId: 'project_42' } })`.

- [ ] **Step 1: Write the failing spec**

Create the file `frontend/src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts` with the following content:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({ name: 'StepEnvSetup', params: {} }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'de' } }),
  createI18n: () => ({ install: vi.fn() }),
}))

import StepEnvSetupView from '../StepEnvSetupView.vue'

describe('StepEnvSetupView — Navigation', () => {
  beforeEach(() => {
    routerPush.mockClear()
  })

  it('leitet next-step mit simulationId an StepSimulation weiter', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: 'sim_x' })

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepSimulation',
      params: { simulationId: 'sim_x' },
      query: { projectId: 'project_42' },
    })
  })

  it('ignoriert next-step ohne nichtleere simulationId', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('next-step', { simulationId: '' })

    expect(routerPush).not.toHaveBeenCalled()
  })

  it('leitet go-back an StepGraphBuild weiter', async () => {
    const wrapper = mount(StepEnvSetupView, {
      props: { projectId: 'project_42' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: true,
          StepModelOverrideChip: true,
          Step2EnvSetup: {
            name: 'Step2EnvSetup',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back', 'add-log', 'update-status'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper
      .getComponent({ name: 'Step2EnvSetup' })
      .vm.$emit('go-back')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepGraphBuild',
      params: { projectId: 'project_42' },
    })
  })
})
```

- [ ] **Step 2: Run the new spec to confirm RED**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts
```

Expected: three tests, all fail (no handler bound, `routerPush` not called, prop mapping uses `simulation-id` while the current wrapper passes `projectId`).

- [ ] **Step 3: Commit the failing spec**

```bash
git add frontend/src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts
git commit -m $'test(frontend): cover StepEnvSetupView navigation\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, spec only.

---

## Task 5: GREEN — wire `next-step` and `go-back` on `StepEnvSetupView`

**Files:**
- Modify: `frontend/src/views/v4/steps/StepEnvSetupView.vue:1-39`

**Interfaces:**
- Consumes: `StepEnvSetupView` props `{ projectId: string }`.
- Produces:
  - `useRouter()` available in setup.
  - `handleNextStep(payload: { simulationId?: string }): void` — navigates to `StepSimulation` only when `simulationId` is a non-empty string; otherwise no call.
  - `handleGoBack(): void` — navigates to `StepGraphBuild` with `projectId: props.projectId`.

- [ ] **Step 1: Update the template**

In `StepEnvSetupView.vue`, change the `<Step2EnvSetup :simulation-id="projectId" />` element (currently line 16) to:

```html
    <Step2EnvSetup
      :simulation-id="projectId"
      @next-step="handleNextStep"
      @go-back="handleGoBack"
    />
```

- [ ] **Step 2: Add router and handlers**

Replace the `<script setup lang="ts">` block (currently lines 20-37) with:

```ts
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import PipelineStepper from '@/components/v4/steps/PipelineStepper.vue'
import Step2EnvSetup from '@/components/Step2EnvSetup.vue'
import StepModelOverrideChip from '@/components/v4/forms/StepModelOverrideChip.vue'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{
  projectId: string
}>()

const router = useRouter()

const crumbs = computed<BreadcrumbItem[]>(() => [
  { label: 'Runs', path: '/runs' },
  { label: props.projectId },
  { label: 'Personas' },
])

function handleNextStep(payload: { simulationId?: unknown }): void {
  if (typeof payload?.simulationId !== 'string' || payload.simulationId.length === 0) {
    return
  }
  void router.push({
    name: 'StepSimulation',
    params: { simulationId: payload.simulationId },
    query: { projectId: props.projectId },
  })
}

function handleGoBack(): void {
  void router.push({
    name: 'StepGraphBuild',
    params: { projectId: props.projectId },
  })
}
</script>
```

- [ ] **Step 3: Run the new spec to confirm GREEN**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts
```

Expected: three tests pass.

- [ ] **Step 4: Re-run neighboring specs**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts \
  src/views/v4/steps/__tests__/StepWrapperViews.spec.ts
```

Expected: all 24 tests pass (3 + 18 + 3).

- [ ] **Step 5: Commit the GREEN state**

```bash
git add frontend/src/views/v4/steps/StepEnvSetupView.vue
git commit -m $'fix(frontend): wire next-step and go-back on StepEnvSetupView\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, single production file changed.

---

## Task 6: RED — create `StepSimulationView.spec.ts` for go-back

**Files:**
- Create: `frontend/src/views/v4/steps/__tests__/StepSimulationView.spec.ts`

**Interfaces:**
- Consumes: `StepSimulationView` props `{ simulationId: string }`.
- Produces: a failing test asserting `router.push({ name: 'StepEnvSetup', params: { projectId: 'sim-99' } })` after a `go-back` emit, plus a baseline mount/structure test (mirrors the existing pattern in `StepWrapperViews.spec.ts`).

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/views/v4/steps/__tests__/StepSimulationView.spec.ts` with:

```ts
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
  useRoute: () => ({ name: 'StepSimulation', params: { simulationId: 'sim-99' } }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'de' } }),
  createI18n: () => ({ install: vi.fn() }),
}))

import StepSimulationView from '../StepSimulationView.vue'

describe('StepSimulationView — Navigation', () => {
  beforeEach(() => {
    routerPush.mockClear()
  })

  it('mountet mit PipelineStepper currentStep=3', () => {
    const wrapper = mount(StepSimulationView, {
      props: { simulationId: 'sim-99' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: { name: 'PipelineStepper', props: ['currentStep'], template: '<div />' },
          StepModelOverrideChip: true,
          Tabs: { name: 'Tabs', props: ['modelValue', 'tabs'], emits: ['update:modelValue'], template: '<div />' },
          Step3Simulation: {
            name: 'Step3Simulation',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back'],
            template: '<section />',
          },
        },
      },
    })

    const stepper = wrapper.findComponent({ name: 'PipelineStepper' })
    expect(stepper.exists()).toBe(true)
    expect(stepper.props('currentStep')).toBe(3)
  })

  it('leitet go-back an StepEnvSetup mit simulierter ID weiter', async () => {
    const wrapper = mount(StepSimulationView, {
      props: { simulationId: 'sim-99' },
      global: {
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          PageHeader: { template: '<header><slot /><slot name="right" /></header>' },
          PipelineStepper: { name: 'PipelineStepper', props: ['currentStep'], template: '<div />' },
          StepModelOverrideChip: true,
          Tabs: { name: 'Tabs', props: ['modelValue', 'tabs'], emits: ['update:modelValue'], template: '<div />' },
          Step3Simulation: {
            name: 'Step3Simulation',
            props: ['simulation-id'],
            emits: ['next-step', 'go-back'],
            template: '<section />',
          },
        },
      },
    })

    await wrapper.getComponent({ name: 'Step3Simulation' }).vm.$emit('go-back')

    expect(routerPush).toHaveBeenCalledTimes(1)
    expect(routerPush).toHaveBeenCalledWith({
      name: 'StepEnvSetup',
      params: { projectId: 'sim-99' },
    })
  })
})
```

- [ ] **Step 2: Run the new spec to confirm RED**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepSimulationView.spec.ts
```

Expected: two tests, `go-back` test fails because the wrapper ignores the emit today.

- [ ] **Step 3: Commit the failing spec**

```bash
git add frontend/src/views/v4/steps/__tests__/StepSimulationView.spec.ts
git commit -m $'test(frontend): cover go-back navigation on StepSimulationView\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, spec only.

---

## Task 7: GREEN — wire `go-back` on `StepSimulationView`

**Files:**
- Modify: `frontend/src/views/v4/steps/StepSimulationView.vue:11-81`

**Interfaces:**
- Consumes: `StepSimulationView` props `{ simulationId: string }`, existing `useRoute`/`useRouter` usage.
- Produces: handler `handleGoBack()` that reads `projectId` from `route.query.projectId` (set by `StepEnvSetupView.handleNextStep`) and calls `router.push({ name: 'StepEnvSetup', params: { projectId } })`; missing/empty query → no-op.

- [ ] **Step 1: Wire the template**

In `StepSimulationView.vue`, replace the `<Step3Simulation … />` element (currently line 32) with:

```html
    <Step3Simulation
      v-if="activeTab === 'pipeline'"
      :simulation-id="simulationId"
      @go-back="handleGoBack"
    />
```

Keep the rest of the template block (including the `Tabs` control) untouched.

- [ ] **Step 2: Add the handler**

Inside `<script setup lang="ts">`, immediately after the existing `function onTabChange(tab: string): void { … }`, add:

```ts
function handleGoBack(): void {
  const projectId = route.query.projectId
  if (typeof projectId !== 'string' || projectId.length === 0) {
    return
  }
  void router.push({
    name: 'StepEnvSetup',
    params: { projectId },
  })
}
```

- [ ] **Step 3: Run the new spec to confirm GREEN**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepSimulationView.spec.ts
```

Expected: both tests pass.

- [ ] **Step 4: Re-run the full v4 steps test cluster**

Run:

```bash
cd frontend && bun run test --run \
  src/views/v4/steps/__tests__/StepGraphBuildView.spec.ts \
  src/views/v4/steps/__tests__/StepEnvSetupView.spec.ts \
  src/views/v4/steps/__tests__/StepSimulationView.spec.ts \
  src/views/v4/steps/__tests__/StepWrapperViews.spec.ts
```

Expected: all 26 tests pass across four files.

- [ ] **Step 5: Commit the GREEN state**

```bash
git add frontend/src/views/v4/steps/StepSimulationView.vue
git commit -m $'fix(frontend): handle go-back on StepSimulationView\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, single production file changed.

---

## Task 8: Update `CHANGELOG.md`

**Files:**
- Modify: `CHANGELOG.md` (top-most unreleased section)

**Interfaces:**
- Consumes: existing changelog section convention used for recent fix entries.
- Produces: single bullet line referencing Issue #850 and the three wrapper views.

- [ ] **Step 1: Inspect current section header**

Run:

```bash
head -n 40 CHANGELOG.md
```

Expected: current `## [Unreleased]` or equivalent section header visible.

- [ ] **Step 2: Insert a bullet line in that section**

Add a single bullet aligned with the existing style (en-dash or `-`, no trailing period), placed under the most recent sub-heading used for fixes. Use this exact text:

```
- fix(frontend): wire `next-step`/`go-back` events in v4 Step-Views (StepGraphBuildView, StepEnvSetupView, StepSimulationView) — regression nach #849 ([#850](https://github.com/arn0ld87/agora/issues/850))
```

Match indentation and bullet character to surrounding entries.

- [ ] **Step 3: Verify no other sections were disturbed**

Run:

```bash
git diff CHANGELOG.md
```

Expected: only the new line appears in the diff.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m $'docs(frontend): changelog entry for v4 step event wiring (#850)\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
```

Expected: one commit, single line added.

---

## Task 9: Full frontend verification and pre-push gate

**Files:** none (verification).

**Interfaces:**
- Consumes: all committed changes from Tasks 1-8.
- Produces: clean local verification outputs suitable for the read-only reviewer.

- [ ] **Step 1: Full frontend test suite**

Run:

```bash
cd frontend && bun run test
```

Expected: all suites pass; no snapshot, no console warnings introduced by the touched files. Capture the summary line.

- [ ] **Step 2: Lint, typecheck and build check**

Run:

```bash
cd frontend && bun run check
```

Expected: exit 0; ESLint, `vue-tsc`, Vite build all green.

- [ ] **Step 3: Frontend-only pre-push gate**

Run:

```bash
bash scripts/pre-push-gate.sh frontend
```

Expected: exit 0 with the frontend scope report.

- [ ] **Step 4: Diff review**

Run:

```bash
git diff --stat main..HEAD
git log --oneline main..HEAD
```

Expected: five commit messages visible (one design doc + four code/test pairs + CHANGELOG). The spec commit from the brainstorming phase appears as `docs(frontend): design v4 step event wiring`.

- [ ] **Step 5: No commit, ready for reviewer**

Stop after passing checks. The next gate is the read-only `agora-opus-reviewer` review; do not push yet.

---

## Self-Review Summary

- Spec coverage:
  - Architecture, transitions, payload handling, error behaviour — Tasks 2-7.
  - TDD additions and navigation tests — Tasks 2, 4, 6.
  - CHANGELOG entry — Task 8.
  - Verification chain (`bun run test`, `bun run check`, frontend-only pre-push gate) — Task 9.
- Placeholder scan: none.
- Type consistency: all handler signatures cross-checked; `routerPush` symbol names uniform across specs; `StepEnvSetup` prop name `simulation-id` matches the child component (`Step2EnvSetup.vue:29`); `Step3Simulation` prop `simulation-id` matches `Step3Simulation.vue:40`.
