/**
 * AppShellWrappers — Smoke-Tests fuer RunDetailAppShellView (Slice F,
 * Design-v4).
 *
 * RunsAppShellView ist mit dem Legacy-Abbau (Redesign PR 10) entfallen: /runs
 * leitet seit PR 8 auf die Ablage um, die Wrapper-View war danach von keiner
 * Route mehr erreichbar. RunDetailAppShellView bleibt, solange
 * `usage-totals` und `budget-exceeded-banner` nur in RunDetailView.vue
 * existieren.
 *
 * Prueft: mountet ohne Crash, AppShell wird gerendert.
 *
 * Hinweis: DashboardView ist seit dem Workbench-Rebuild (2026-05-14) ein
 * eigener Spec unter src/views/v4/__tests__/DashboardView.spec.ts —
 * nicht mehr Teil dieser Datei.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

vi.mock('@/components/v4/shell/AppShell.vue', () => ({
  default: {
    name: 'AppShell',
    props: ['breadcrumbs'],
    template: '<div class="app-shell-stub"><slot /></div>',
  },
}))
vi.mock('@/components/v4/shell/PageHeader.vue', () => ({
  default: {
    name: 'PageHeader',
    props: ['title', 'subtitle'],
    template: '<div class="page-header-stub"><h1>{{ title }}</h1></div>',
  },
}))
vi.mock('@/components/v4/forms/Card.vue', () => ({
  default: {
    name: 'Card',
    props: ['title'],
    template: '<div class="card-stub"><slot /></div>',
  },
}))

// RunDetailView stubben — isolierter Unit-Test
vi.mock('@/views/RunDetailView.vue', () => ({
  default: {
    name: 'RunDetailView',
    template: '<div class="run-detail-view-stub">RunDetailView</div>',
  },
}))

import RunDetailAppShellView from '../v4/RunDetailAppShellView.vue'

async function mountView(component: object, path: string) {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(component, {
    global: { plugins: [router, pinia] },
  })
  await flushPromises()
  return wrapper
}

describe('RunDetailAppShellView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const router = makeTestRouter()
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/runs/abc-123')
    await router.isReady()
    const w = mount(RunDetailAppShellView, {
      global: { plugins: [router, pinia] },
    })
    await flushPromises()
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const router = makeTestRouter()
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/runs/abc-123')
    await router.isReady()
    const w = mount(RunDetailAppShellView, {
      global: { plugins: [router, pinia] },
    })
    await flushPromises()
    expect(w.find('.app-shell-stub').exists()).toBe(true)
  })

  it('bettet RunDetailView ein', async () => {
    const router = makeTestRouter()
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/runs/abc-123')
    await router.isReady()
    const w = mount(RunDetailAppShellView, {
      global: { plugins: [router, pinia] },
    })
    await flushPromises()
    expect(w.find('.run-detail-view-stub').exists()).toBe(true)
  })

  it('setzt Breadcrumb auf ["Runs", runId]', async () => {
    const router = makeTestRouter()
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/runs/abc-123')
    await router.isReady()
    const w = mount(RunDetailAppShellView, {
      global: { plugins: [router, pinia] },
    })
    await flushPromises()
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    const labels = crumbs.map((c) => c.label)
    expect(labels).toContain('Runs')
    expect(labels).toContain('abc-123')
  })
})
