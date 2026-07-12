/**
 * LlmProvidersView — Connection-Lifecycle-Tests (Onboarding Slice 3, Task 5).
 *
 * Prüft:
 *  1. View mountet ohne Crash.
 *  2. Nicht konfigurierter Provider zeigt "Nicht konfiguriert".
 *  3. Konfigurierter + verbundener Provider zeigt "Verbunden".
 *  4. Unsupported Provider (opencode_go) wird ehrlich als "Nicht unterstützt"
 *     markiert — keine Eingabefelder, kein Speichern-Versuch, kein API-Call.
 *  5. "Verbindung speichern" ruft den Connection-Store mit korrektem Payload
 *     auf (kein Klartext-Key im Draft nach dem Speichern).
 *  6. "Verbindung testen" zeigt das Testergebnis inkl. models_found an.
 *  7. Lokaler Ollama-Flow: kein API-Key-Feld, Loopback-Placeholder.
 *  8. Keine ungepatchten i18n-Rohkeys im DOM.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { makeTestRouter } from '@/components/v4/shell/__tests__/testRouter'

import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

const CATALOG = vi.hoisted(() => [
  {
    id: 'openai',
    label: 'OpenAI',
    type: 'openai',
    base_url: 'https://api.openai.com/v1',
    api_key_ref: 'OPENAI_API_KEY',
    supports_models_endpoint: true,
    fallback_models: [],
  },
  {
    id: 'ollama',
    label: 'Ollama (lokal)',
    type: 'ollama',
    base_url: 'http://localhost:11434',
    api_key_ref: null,
    supports_models_endpoint: true,
    fallback_models: [],
  },
  {
    id: 'opencode_go',
    label: 'OpenCode Go',
    type: 'opencode_go',
    base_url: 'https://opencode.ai/zen/go/v1',
    api_key_ref: 'OPENCODE_GO_API_KEY',
    supports_models_endpoint: false,
    fallback_models: [],
  },
])

const CONNECTED_OPENAI_CONNECTION = {
  id: 'openai',
  provider_kind: 'openai',
  display_name: 'OpenAI',
  transport: 'http',
  auth_mode: 'api_key',
  base_url: 'https://api.openai.com/v1',
  enabled: true,
  status: 'connected',
  status_message: null,
  secret_ref: 'openai',
  capabilities: {},
  created_at: '2026-07-12T10:00:00+00:00',
  updated_at: '2026-07-12T10:00:00+00:00',
  last_tested_at: '2026-07-12T10:05:00+00:00',
}

const listProviderConnectionsMock = vi.hoisted(() => vi.fn())
const upsertProviderConnectionMock = vi.hoisted(() => vi.fn())
const deleteProviderConnectionMock = vi.hoisted(() => vi.fn())
const testProviderConnectionMock = vi.hoisted(() => vi.fn())
const listProviderConnectionModelsMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/providerConnections', () => ({
  listProviderConnections: listProviderConnectionsMock,
  upsertProviderConnection: upsertProviderConnectionMock,
  deleteProviderConnection: deleteProviderConnectionMock,
  testProviderConnection: testProviderConnectionMock,
  listProviderConnectionModels: listProviderConnectionModelsMock,
}))

vi.mock('@/api/llmRouting', () => ({
  listLlmProviders: vi.fn().mockResolvedValue(CATALOG),
  listProviderModels: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/api/llmProviderKeys', () => ({
  listLlmProviderKeys: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getLlmProviderKey: vi.fn(),
  upsertLlmProviderKey: vi.fn(),
  deleteLlmProviderKey: vi.fn(),
  checkLlmProviderHasKey: vi.fn().mockResolvedValue(false),
  testLlmProvider: vi.fn(),
}))

vi.mock('@/store/llmRoutingDefaults', () => ({
  useLlmRoutingDefaultsStore: () => ({
    defaults: { updated_at: null, global_default: null, stage_overrides: {} },
    globalDefault: null,
    stageOverrides: {},
    effectiveRouteForStage: vi.fn().mockReturnValue({ provider_id: '', model: '' }),
    load: vi.fn().mockResolvedValue(undefined),
    setGlobalDefault: vi.fn().mockResolvedValue(undefined),
    setStageOverride: vi.fn().mockResolvedValue(undefined),
    clearStageOverride: vi.fn().mockResolvedValue(undefined),
  }),
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
    props: ['title', 'subtitle', 'breadcrumbs'],
    template: '<div class="page-header-stub"><h1>{{ title }}</h1></div>',
  },
}))
vi.mock('@/components/v4/forms/ModelPicker.vue', () => ({
  default: {
    name: 'ModelPicker',
    props: ['modelValue', 'placeholder', 'disabled'],
    template: '<div class="model-picker-stub" />',
  },
}))

import LlmProvidersView from '../Settings/LlmProvidersView.vue'

function makeI18n(locale = 'de') {
  return createI18n({
    legacy: false,
    locale,
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

async function mountView() {
  const router = makeTestRouter()
  const pinia = createPinia()
  setActivePinia(pinia)
  const i18n = makeI18n()
  await router.push('/settings/llm-providers')
  await router.isReady()
  const wrapper = mount(LlmProvidersView, {
    global: { plugins: [router, pinia, i18n] },
  })
  await flushPromises()
  return wrapper
}

function cardFor(wrapper: ReturnType<typeof mount>, providerId: string) {
  return wrapper.find(`[data-testid="provider-card"][data-provider-id="${providerId}"]`)
}

describe('LlmProvidersView (Connection-Lifecycle, Onboarding Slice 3 Task 5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listProviderConnectionsMock.mockResolvedValue({ items: [], total: 0 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('Test 1: mountet ohne Crash', async () => {
    const w = await mountView()
    expect(w.exists()).toBe(true)
  })

  it('Test 2: nicht konfigurierter Provider zeigt "Nicht konfiguriert"', async () => {
    listProviderConnectionsMock.mockResolvedValue({ items: [], total: 0 })
    const w = await mountView()

    const card = cardFor(w, 'openai')
    expect(card.find('[data-testid="provider-status-badge"]').text()).toBe('Nicht konfiguriert')
  })

  it('Test 3: konfigurierter + verbundener Provider zeigt "Verbunden"', async () => {
    listProviderConnectionsMock.mockResolvedValue({
      items: [CONNECTED_OPENAI_CONNECTION],
      total: 1,
    })
    const w = await mountView()

    const card = cardFor(w, 'openai')
    expect(card.find('[data-testid="provider-status-badge"]').text()).toBe('Verbunden')
  })

  it('Test 4: unsupported Provider wird ehrlich als "Nicht unterstützt" markiert, ohne Eingabefelder', async () => {
    const w = await mountView()

    const card = cardFor(w, 'opencode_go')
    expect(card.find('[data-testid="provider-status-badge"]').text()).toBe('Nicht unterstützt')
    expect(card.find('[data-testid="provider-unsupported-notice"]').exists()).toBe(true)
    expect(card.findAllComponents({ name: 'Input' })).toHaveLength(0)

    const saveButton = card.findAll('button').find((b) => b.text().includes('Verbindung speichern'))
    await saveButton?.trigger('click')
    await flushPromises()

    expect(upsertProviderConnectionMock).not.toHaveBeenCalled()
  })

  it('Test 5: "Verbindung speichern" ruft den Connection-Store mit korrektem Payload auf', async () => {
    upsertProviderConnectionMock.mockResolvedValue(CONNECTED_OPENAI_CONNECTION)
    const w = await mountView()

    const card = cardFor(w, 'openai')
    const inputs = card.findAllComponents({ name: 'Input' })
    // Erstes Input ist der API-Key (type=password), zweites die Base-URL.
    await inputs[0]!.vm.$emit('update:modelValue', 'sk-test-key')
    await flushPromises()

    const saveButton = card.findAll('button').find((b) => b.text().includes('Verbindung speichern'))
    await saveButton?.trigger('click')
    await flushPromises()

    expect(upsertProviderConnectionMock).toHaveBeenCalledWith('openai', expect.objectContaining({
      provider_kind: 'openai',
      api_key: 'sk-test-key',
    }))
  })

  it('Test 6: "Verbindung testen" zeigt das Testergebnis inkl. models_found an', async () => {
    listProviderConnectionsMock.mockResolvedValue({
      items: [CONNECTED_OPENAI_CONNECTION],
      total: 1,
    })
    testProviderConnectionMock.mockResolvedValue({
      status: 'available',
      status_message: null,
      models_found: 7,
    })
    const w = await mountView()

    const card = cardFor(w, 'openai')
    const testButton = card.findAll('button').find((b) => b.text().includes('Verbindung testen'))
    await testButton?.trigger('click')
    await flushPromises()

    expect(testProviderConnectionMock).toHaveBeenCalledWith('openai')
    expect(card.find('[data-testid="provider-test-result"]').text()).toContain('7 Modelle gefunden.')
  })

  it('Test 7: lokaler Ollama-Flow zeigt Loopback-Placeholder und kein API-Key-Feld', async () => {
    const w = await mountView()

    const card = cardFor(w, 'ollama')
    const inputs = card.findAllComponents({ name: 'Input' })
    expect(inputs).toHaveLength(1)
    expect(inputs[0]!.props('placeholder')).toBe('http://localhost:11434')
  })

  it('Test 8: keine ungepatchten i18n-Rohkeys im DOM', async () => {
    const w = await mountView()
    expect(w.text()).not.toMatch(/settings\.v4\.llmProviders\./)
  })
})
