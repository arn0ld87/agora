import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

// v4 Shell-Komponenten stubben (brauchen Router + Store, der in Unit-Tests nicht vollständig aufgesetzt ist)
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
    template: '<div class="page-header-stub"><h1>{{ title }}</h1><p>{{ subtitle }}</p></div>',
  },
}))
vi.mock('@/components/v4/forms/StickyActionBar.vue', () => ({
  default: {
    name: 'StickyActionBar',
    template: '<div class="sticky-action-bar-stub"><slot name="right" /></div>',
  },
}))

// Sub-Karten stubben — Smoke-Tests prüfen Existenz, nicht inneres Rendering
vi.mock('@/views/Settings/llmRouting/GlobalDefaultCard.vue', () => ({
  default: {
    name: 'GlobalDefaultCard',
    template: '<div class="global-default-card" data-testid="card-global-default">Global Default</div>',
  },
}))
vi.mock('@/views/Settings/llmRouting/ActiveSnapshotsCard.vue', () => ({
  default: {
    name: 'ActiveSnapshotsCard',
    template: '<div class="active-snapshots-card" data-testid="card-active-snapshots">Aktive Snapshots</div>',
  },
}))
vi.mock('@/views/Settings/llmRouting/StageOverridesCard.vue', () => ({
  default: {
    name: 'StageOverridesCard',
    template: '<div class="stage-overrides-card" data-testid="card-stage-overrides">Stage Overrides</div>',
  },
}))
vi.mock('@/views/Settings/llmRouting/CustomModelCard.vue', () => ({
  default: {
    name: 'CustomModelCard',
    template: '<div class="custom-model-card" data-testid="card-custom-model">Custom Model</div>',
  },
}))

import LlmRoutingView from '../Settings/LlmRoutingView.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/settings', name: 'Settings', redirect: '/settings/general' },
      { path: '/settings/general', name: 'SettingsGeneral', component: { template: '<div />' } },
      { path: '/settings/llm-routing', name: 'SettingsLlmRouting', component: LlmRoutingView },
    ],
  })
}

async function mountView() {
  const router = makeRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  await router.push('/settings/llm-routing')
  await router.isReady()
  const wrapper = mount(LlmRoutingView, {
    global: {
      plugins: [router, pinia],
    },
  })
  await flushPromises()
  return wrapper
}

describe('LlmRoutingView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const wrapper = await mountView()
    expect(wrapper.exists()).toBe(true)
  })

  it('gibt Breadcrumbs "Settings / LLM Routing" an AppShell weiter', async () => {
    const wrapper = await mountView()
    const shell = wrapper.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toEqual(['Settings', 'LLM Routing'])
  })

  it('rendert alle vier Cards', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[data-testid="card-global-default"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="card-active-snapshots"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="card-stage-overrides"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="card-custom-model"]').exists()).toBe(true)
  })

  it('rendert StickyActionBar mit Save- und Reset-Button', async () => {
    const wrapper = await mountView()
    const bar = wrapper.find('.sticky-action-bar-stub')
    expect(bar.exists()).toBe(true)
    const buttons = bar.findAll('button')
    const texts = buttons.map((b) => b.text())
    expect(texts).toContain('Speichern')
    expect(texts).toContain('Zurücksetzen')
  })

  it('PageHeader hat korrekten Titel und Subtitle', async () => {
    const wrapper = await mountView()
    const header = wrapper.find('.page-header-stub')
    expect(header.find('h1').text()).toBe('LLM Routing')
    expect(header.find('p').text()).toContain('Provider')
  })
})
