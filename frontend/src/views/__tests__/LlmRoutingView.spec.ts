import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  listRuns: vi.fn(),
}))

const localStorageState = new Map<string, string>()
const localStorageMock = {
  getItem: vi.fn((key: string) => localStorageState.get(key) ?? null),
  setItem: vi.fn((key: string, value: string) => {
    localStorageState.set(key, value)
  }),
}

vi.mock('@/api/runs', () => ({
  listRuns: mocks.listRuns,
}))

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
vi.mock('@/components/v4/forms/Card.vue', () => ({
  default: {
    name: 'Card',
    props: ['title', 'subtitle'],
    template: '<section class="card-stub"><h2>{{ title }}</h2><slot /></section>',
  },
}))
vi.mock('@/components/v4/forms/Field.vue', () => ({
  default: {
    name: 'Field',
    props: ['label'],
    template: '<label class="field-stub"><span>{{ label }}</span><slot /></label>',
  },
}))
vi.mock('@/components/v4/forms/Input.vue', () => ({
  default: {
    name: 'Input',
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: `
      <input
        data-testid="manual-run-id"
        :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
      />
    `,
  },
}))
vi.mock('@/components/v4/forms/Select.vue', () => ({
  default: {
    name: 'Select',
    props: ['modelValue', 'options'],
    emits: ['update:modelValue'],
    template: `
      <select
        data-testid="run-select"
        :value="modelValue"
        @change="$emit('update:modelValue', $event.target.value)"
      >
        <option v-for="opt in options" :key="opt.value" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
    `,
  },
}))
vi.mock('@/components/LlmRouting/LlmRoutingView.vue', () => ({
  default: {
    name: 'RunLlmRoutingPanel',
    props: ['runId'],
    template: '<div data-testid="run-llm-routing-panel">{{ runId }}</div>',
  },
}))

import LlmRoutingView from '../Settings/LlmRoutingView.vue'

function makeRun(runId: string) {
  return {
    run_id: runId,
    run_type: 'project_run',
    entity_id: 'project-1',
    parent_run_id: null,
    status: 'processing',
    progress: 10,
    message: '',
    error: null,
    started_at: '2026-05-14T10:00:00Z',
    updated_at: '2026-05-14T10:01:00Z',
    completed_at: null,
    branch_label: null,
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: { available: false, action: 'resume', label: 'Resume', reason: null },
  }
}

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
    localStorageState.clear()
    Object.defineProperty(window, 'localStorage', {
      value: localStorageMock,
      configurable: true,
    })
    // Issue #580: listRuns now returns RunsListResponse { runs, total, aggregation }
    mocks.listRuns.mockResolvedValue({
      success: true,
      data: { runs: [makeRun('run_latest'), makeRun('run_previous')], total: 2, aggregation: null },
    })
  })

  it('gibt Breadcrumbs "Settings / LLM Routing" an AppShell weiter', async () => {
    const wrapper = await mountView()
    const shell = wrapper.findComponent({ name: 'AppShell' })
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.map((c) => c.label)).toEqual(['Settings', 'LLM Routing'])
  })

  it('laedt Runs und rendert das echte LLM-Routing-Panel fuer den ersten Run', async () => {
    const wrapper = await mountView()

    expect(mocks.listRuns).toHaveBeenCalledWith({ limit: 25 })
    expect(wrapper.find('[data-testid="run-llm-routing-panel"]').text()).toBe('run_latest')
  })

  it('uebernimmt manuelle Run-ID-Eingaben fuer das Routing-Panel', async () => {
    const wrapper = await mountView()

    await wrapper.find('[data-testid="manual-run-id"]').setValue('run_manual')
    await flushPromises()

    expect(wrapper.find('[data-testid="run-llm-routing-panel"]').text()).toBe('run_manual')
    expect(window.localStorage.getItem('agora.llmRouting.selectedRunId')).toBe('run_manual')
  })

  it('rendert keine globale Save-Schaltflaeche ohne Persistenzhandler', async () => {
    const wrapper = await mountView()

    const buttons = wrapper.findAll('button').map((button) => button.text())
    expect(buttons).not.toContain('Speichern')
  })

  it('PageHeader hat korrekten Titel und Subtitle', async () => {
    const wrapper = await mountView()
    const header = wrapper.find('.page-header-stub')
    expect(header.find('h1').text()).toBe('LLM Routing')
    expect(header.find('p').text()).toContain('Run')
  })
})
