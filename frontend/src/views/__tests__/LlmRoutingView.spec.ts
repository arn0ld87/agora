import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { LlmRoutingTestId } from '@/contracts/testIds'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

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
// Redesign PR 9: SettingsOverlay ersetzt die Breadcrumbs, braucht aber i18n +
// eine vollstaendige Sektions-Router-Landschaft — beides fehlt in diesem
// schlanken Router-only-Setup. Diese Suite prueft die Run-Picker-Glue-Logik,
// nicht das Settings-Chrome, daher genuegt ein reiner Slot-Stub.
vi.mock('@/components/v4/forms/SettingsOverlay.vue', () => ({
  default: {
    name: 'SettingsOverlay',
    template: '<div class="settings-overlay-stub"><slot /></div>',
  },
}))
vi.mock('@/components/v4/forms/Card.vue', () => ({
  default: {
    name: 'Card',
    props: ['title', 'subtitle'],
    template: '<section class="card-stub"><h2>{{ title }}</h2><p>{{ subtitle }}</p><slot /></section>',
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

async function mountView(locale: 'de' | 'en' = 'de') {
  const router = makeRouter()
  const pinia = createPinia()
  const i18n = createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'de',
    messages: { de, en },
  })
  setActivePinia(pinia)
  await router.push('/settings/llm-routing')
  await router.isReady()
  const wrapper = mount(LlmRoutingView, {
    global: {
      plugins: [router, pinia, i18n],
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

  it('bettet SettingsOverlay ein statt eigener Breadcrumbs (Redesign PR 9)', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('.settings-overlay-stub').exists()).toBe(true)
  })

  it('laedt Runs und rendert das echte LLM-Routing-Panel fuer den ersten Run', async () => {
    const wrapper = await mountView()

    expect(mocks.listRuns).toHaveBeenCalledWith({ limit: 25 })
    expect(wrapper.find('[data-testid="run-llm-routing-panel"]').text()).toBe('run_latest')
  })

  it('uebernimmt manuelle Run-ID-Eingaben fuer das Routing-Panel', async () => {
    const wrapper = await mountView()

    await wrapper.find(`[data-testid="${LlmRoutingTestId.runId}"]`).setValue('run_manual')
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

  it('rendert die Run-Auswahl und den Leerzustand vollstaendig auf Englisch', async () => {
    mocks.listRuns.mockResolvedValue({
      success: true,
      data: { runs: [], total: 0, aggregation: null },
    })

    const wrapper = await mountView('en')

    expect(wrapper.text()).toContain('Configure run-specific providers, model selection, and stage routing.')
    expect(wrapper.text()).toContain('Run selection')
    expect(wrapper.text()).toContain('The LLM routing configuration is stored per run.')
    expect(wrapper.text()).toContain('Current runs')
    expect(wrapper.text()).toContain('Run ID')
    expect(wrapper.find('select').attributes('placeholder')).toBe('Select a run')
    expect(wrapper.text()).toContain('Refresh')
    expect(wrapper.text()).toContain('No run selected')
    expect(wrapper.text()).toContain('Select a run or enter a specific run ID.')
    expect(wrapper.text()).not.toContain('Run-spezifische Provider')
    expect(wrapper.text()).not.toContain('Kein Run ausgewählt')
  })

  it('rendert den Fallback-Ladefehler auf Englisch', async () => {
    mocks.listRuns.mockRejectedValue('offline')

    const wrapper = await mountView('en')

    expect(wrapper.find('.llmr-error').text()).toBe('Runs could not be loaded')
  })
})
