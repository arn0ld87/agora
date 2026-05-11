/**
 * AppShellWrappers — Smoke-Tests fuer DashboardView, RunsAppShellView,
 * RunDetailAppShellView (Slice F, Design-v4).
 *
 * Prueft: mountet ohne Crash, AppShell wird gerendert.
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

// RunsView und RunDetailView stubben — isolierte Unit-Tests
vi.mock('@/views/RunsView.vue', () => ({
  default: {
    name: 'RunsView',
    template: '<div class="runs-view-stub">RunsView</div>',
  },
}))
vi.mock('@/views/RunDetailView.vue', () => ({
  default: {
    name: 'RunDetailView',
    template: '<div class="run-detail-view-stub">RunDetailView</div>',
  },
}))

import DashboardView from '../v4/DashboardView.vue'
import RunsAppShellView from '../v4/RunsAppShellView.vue'
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

describe('DashboardView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(DashboardView, '/dashboard')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(DashboardView, '/dashboard')
    expect(w.find('.app-shell-stub').exists()).toBe(true)
  })

  it('uebergibt Breadcrumb "Dashboard"', async () => {
    const w = await mountView(DashboardView, '/dashboard')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('Dashboard')
  })

  it('zeigt Slice-H-Hinweis', async () => {
    const w = await mountView(DashboardView, '/dashboard')
    expect(w.text()).toContain('Slice H')
  })
})

describe('RunsAppShellView', () => {
  beforeEach(() => vi.clearAllMocks())

  it('mountet ohne Crash', async () => {
    const w = await mountView(RunsAppShellView, '/runs')
    expect(w.exists()).toBe(true)
  })

  it('rendert AppShell', async () => {
    const w = await mountView(RunsAppShellView, '/runs')
    expect(w.find('.app-shell-stub').exists()).toBe(true)
  })

  it('bettet RunsView ein', async () => {
    const w = await mountView(RunsAppShellView, '/runs')
    expect(w.find('.runs-view-stub').exists()).toBe(true)
  })

  it('uebergibt Breadcrumb "Runs"', async () => {
    const w = await mountView(RunsAppShellView, '/runs')
    const shell = w.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toContain('Runs')
  })
})

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
