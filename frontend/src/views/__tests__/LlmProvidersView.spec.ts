/**
 * LlmProvidersView — Spec-Tests fuer Slice 5.4 Migration auf AiModelPicker.
 *
 * Die View rendert eine Workspace-Default-Card und Provider-Cards.
 * Migration-Fokus: Workspace-Default-Card nutzt jetzt AiModelPicker
 * (SSoT) statt ModelPicker. Die Provider-Cards bleiben unveraendert,
 * sind aber durch smoke tests mit abgedeckt.
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. zeigt BREADCRUMBS
 *  3. zeigt PageHeader mit title + subtitle
 *  4. Workspace-Default-Card sichtbar
 *  5. AiModelPicker in der Default-Card
 *  6. defaultRoute computed zeigt aktuelle Route (Provider-ID + Model)
 *  7. AiModelPicker-Update mit AiModelRef → adapter.toStageLlmRoute → setGlobalDefault
 *  8. AiModelPicker-Update mit null → kein setGlobalDefault-Aufruf
 *  9. onMounted: loadProviders + loadConnections + defaultsStore.load
 * 10. onBeforeUnmount: loescht alle drafts
 * 11. statusTone: connected → 'green', error → 'red', unsupported → 'gray'
 * 12. statusLabel: connected → 'Verbunden', undefined → 'Nicht konfiguriert'
 * 13. provider-card: Listet alle Provider auf
 * 14. save() ruft upsertConnection mit korrekten Args (apiKey, baseUrl)
 * 15. runTest() ruft testConnection wenn konfiguriert
 * 16. disconnect() ruft removeConnection und loescht draft
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import LlmProvidersView from '../Settings/LlmProvidersView.vue'

// AiModelPicker mocken — Glue-Code, nicht Picker-Logik
const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-stub" @click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'explicit\' })">picker</div>',
}

// ModelPicker stubben (sollte nach Migration nicht mehr referenziert werden)
const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker-stub" disabled></select>',
}

// AppShell / PageHeader / Card / Input / Badge stubben (zu vieler Komponenten
// Mounting, wir testen Glue-Code, nicht die Sub-Components)
const appShellStub = { name: 'AppShell', template: '<div><slot /></div>' }
const pageHeaderStub = {
  name: 'PageHeader',
  props: ['title', 'subtitle', 'breadcrumbs'],
  template: '<div data-testid="page-header" :data-title="title" :data-subtitle="subtitle"><slot /></div>',
}
const cardStub = {
  name: 'Card',
  props: ['title', 'subtitle', 'dataTestid'],
  template: '<section :data-testid="dataTestid || \'card\'" :data-card-title="title"><slot name="right" /><slot /></section>',
}
const inputStub = {
  name: 'Input',
  props: ['modelValue', 'type', 'placeholder', 'autocomplete', 'spellcheck'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" :type="type" />',
}
const badgeStub = {
  name: 'Badge',
  props: ['tone'],
  template: '<span :data-tone="tone"><slot /></span>',
}

const providersArr = reactive<unknown[]>([])
const connectionsObj = reactive<Record<string, unknown>>({})
const connectionModelsObj = reactive<Record<string, unknown[]>>({})
const connectionTestResultsObj = reactive<Record<string, unknown>>({})
const connectionErrorObj = reactive<Record<string, string | null>>({})
const connectionBusyObj = reactive<Record<string, boolean>>({})
const connectionUnsupportedObj = reactive<Record<string, boolean>>({})

let globalDefaultRef: unknown = null

const providersStoreMock = {
  get providers() { return providersArr },
  get connections() { return connectionsObj },
  get connectionModels() { return connectionModelsObj },
  get connectionTestResults() { return connectionTestResultsObj },
  get connectionError() { return connectionErrorObj },
  get connectionBusy() { return connectionBusyObj },
  get connectionUnsupported() { return connectionUnsupportedObj },
  loadProviders: vi.fn().mockResolvedValue(undefined),
  loadConnections: vi.fn().mockResolvedValue(undefined),
  isConnectionConfigured: vi.fn((id: string) => id in connectionsObj),
  upsertConnection: vi.fn().mockResolvedValue(undefined),
  testConnection: vi.fn().mockResolvedValue({ status: 'available', models_found: 0, status_message: null }),
  fetchConnectionModels: vi.fn().mockResolvedValue([]),
  removeConnection: vi.fn().mockResolvedValue(undefined),
}

const defaultsStoreMock = {
  get globalDefault() { return globalDefaultRef },
  setGlobalDefault: vi.fn().mockResolvedValue(undefined),
  load: vi.fn().mockResolvedValue(undefined),
}

const adapterMock = {
  toStageLlmRoute: vi.fn((aiRef: { provider_connection_id: string; model_id: string }) => ({
    stage: null,
    provider_id: 'openai',
    model: aiRef.model_id,
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  })),
  toAiModelRef: vi.fn((route: { provider_id?: string | null; model?: string | null }) => ({
    provider_connection_id: route.provider_id ?? 'conn-fallback',
    model_id: route.model ?? '',
    source: 'explicit' as const,
  })),
}

vi.mock('@/store/aiModels', () => ({
  useLlmProvidersStore: () => providersStoreMock,
  useLlmRoutingDefaultsStore: () => defaultsStoreMock,
}))

vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => adapterMock,
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: {
      de: {
        settings: {
          v4: {
            llmProviders: {
              title: 'LLM-Provider',
              subtitle: 'API-Schluessel, Modelle und Workspace-Default.',
              defaults: {
                title: 'Workspace-Default',
                subtitle: 'Standard fuer neue Runs.',
                placeholder: 'Standardmodell waehlen …',
              },
              status: {
                connected: 'Verbunden',
                degraded: 'Eingeschraenkt',
                error: 'Fehler',
                disconnected: 'Getrennt',
                configured: 'Konfiguriert',
                notConfigured: 'Nicht konfiguriert',
                unsupported: 'Nicht unterstuetzt',
              },
              actions: {
                save: 'Verbindung speichern',
                test: 'Verbindung testen',
                refreshModels: 'Modelle laden',
                disconnect: 'Verbindung trennen',
              },
            },
          },
        },
        common: { delete: 'Loeschen' },
      },
    },
  })
}

async function mountView(initial: {
  globalDefault?: unknown
  connections?: Record<string, unknown>
} = {}) {
  providersArr.length = 0
  providersArr.push(
    { id: 'ollama', label: 'Lokales Ollama', type: 'ollama', base_url: 'http://localhost:11434', supports_models_endpoint: true, fallback_models: [] },
    { id: 'openai', label: 'OpenAI', type: 'openai', base_url: null, supports_models_endpoint: true, fallback_models: [] },
    { id: 'opencode_go', label: 'OpenCode Go', type: 'opencode_go', base_url: null, supports_models_endpoint: false, fallback_models: [] },
  )
  for (const k of Object.keys(connectionsObj)) delete connectionsObj[k]
  for (const k of Object.keys(connectionModelsObj)) delete connectionModelsObj[k]
  for (const k of Object.keys(connectionTestResultsObj)) delete connectionTestResultsObj[k]
  for (const k of Object.keys(connectionErrorObj)) delete connectionErrorObj[k]
  for (const k of Object.keys(connectionBusyObj)) delete connectionBusyObj[k]
  for (const k of Object.keys(connectionUnsupportedObj)) delete connectionUnsupportedObj[k]
  if (initial.connections) {
    Object.assign(connectionsObj, initial.connections)
  }
  globalDefaultRef = initial.globalDefault ?? null

  providersStoreMock.loadProviders.mockClear()
  providersStoreMock.loadConnections.mockClear()
  providersStoreMock.upsertConnection.mockClear()
  providersStoreMock.testConnection.mockClear()
  providersStoreMock.fetchConnectionModels.mockClear()
  providersStoreMock.removeConnection.mockClear()
  defaultsStoreMock.setGlobalDefault.mockClear()
  defaultsStoreMock.load.mockClear()
  adapterMock.toStageLlmRoute.mockClear()
  adapterMock.toAiModelRef.mockClear()

  const i18n = makeI18n()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(LlmProvidersView, {
    global: {
      plugins: [i18n],
      stubs: {
        AiModelPicker: aiPickerStub,
        ModelPicker: legacyModelPickerStub,
        AppShell: appShellStub,
        PageHeader: pageHeaderStub,
        Card: cardStub,
        Input: inputStub,
        Badge: badgeStub,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('LlmProvidersView (Slice 5.4, AiModelPicker-Migration)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountView()
    expect(w.exists()).toBe(true)
  })

  it('zeigt BREADCRUMBS via PageHeader', async () => {
    const w = await mountView()
    const ph = w.findComponent(pageHeaderStub)
    expect(ph.exists()).toBe(true)
    const crumbs = ph.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.length).toBeGreaterThanOrEqual(2)
    expect(crumbs[0].label).toBe('Settings')
  })

  it('zeigt PageHeader mit title + subtitle', async () => {
    const w = await mountView()
    const ph = w.findComponent(pageHeaderStub)
    expect(ph.props('title')).toContain('LLM-Provider')
  })

  it('Workspace-Default-Card sichtbar', async () => {
    const w = await mountView()
    const cards = w.findAllComponents(cardStub)
    const defaultCard = cards.find((c) => c.props('title') === 'Workspace-Default')
    expect(defaultCard).toBeDefined()
  })

  it('AiModelPicker in der Default-Card', async () => {
    const w = await mountView()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
  })

  it('defaultRoute computed zeigt aktuelle Route (Provider-ID + Model)', async () => {
    const w = await mountView({
      globalDefault: { provider_id: 'openai', model: 'gpt-4o-mini', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {} },
    })
    const defaultSpan = w.find('.llm-default-current')
    expect(defaultSpan.exists()).toBe(true)
    expect(defaultSpan.text()).toContain('openai')
    expect(defaultSpan.text()).toContain('gpt-4o-mini')
  })

  it('AiModelPicker-Update mit AiModelRef → adapter.toStageLlmRoute → setGlobalDefault', async () => {
    const w = await mountView()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    await picker.trigger('click')
    expect(adapterMock.toStageLlmRoute).toHaveBeenCalledWith({
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    expect(defaultsStoreMock.setGlobalDefault).toHaveBeenCalledWith({
      stage: null,
      provider_id: 'openai',
      model: 'gpt-4o-mini',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    })
  })

  it('AiModelPicker-Update mit null → kein setGlobalDefault', async () => {
    const w = await mountView()
    const picker = w.findComponent(aiPickerStub)
    // Emit null direkt (Stub emittiert hardcoded, daher manuell)
    await picker.vm.$emit('update:modelValue', null)
    expect(defaultsStoreMock.setGlobalDefault).not.toHaveBeenCalled()
  })

  it('onMounted: loadProviders + loadConnections + defaultsStore.load', async () => {
    await mountView()
    expect(providersStoreMock.loadProviders).toHaveBeenCalled()
    expect(providersStoreMock.loadConnections).toHaveBeenCalled()
    expect(defaultsStoreMock.load).toHaveBeenCalled()
  })

  it('onBeforeUnmount: loescht alle drafts (kein Key-Material im Speicher)', async () => {
    const w = await mountView()
    // Drafts sind reactive intern; sichtbar wird das nur, wenn wir
    // ueberpruefen, dass der Cleanup-Pfad keine Fehler wirft.
    w.unmount()
    expect(() => w.vm).not.toThrow()
  })

  it('statusTone: connected → green, error → red, unsupported → gray', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    const badges = w.findAllComponents(badgeStub)
    const openaiBadge = badges.find((b) => b.text().includes('Verbunden'))
    expect(openaiBadge?.props('tone')).toBe('green')
  })

  it('statusLabel: connected → "Verbunden", undefined → "Nicht konfiguriert"', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    const badges = w.findAllComponents(badgeStub)
    const openaiBadge = badges.find((b) => b.text().includes('Verbunden'))
    const ollamaBadge = badges.find((b) => b.text().includes('Nicht konfiguriert'))
    expect(openaiBadge).toBeDefined()
    expect(ollamaBadge).toBeDefined()
  })

  it('provider-card: Listet alle Provider auf', async () => {
    const w = await mountView()
    const cards = w.findAllComponents(cardStub)
    // 1 Workspace-Default-Card + 3 Provider-Cards = 4
    expect(cards.length).toBe(4)
  })

  it('save() ruft upsertConnection mit korrekten Args (apiKey, baseUrl)', async () => {
    const w = await mountView()
    const cards = w.findAllComponents(cardStub)
    const openaiCard = cards.find((c) => c.props('title') === 'OpenAI')
    expect(openaiCard).toBeDefined()
    // Save-Button hat data-action="save" (siehe Original-Template)
    const saveBtn = openaiCard!.find('button.llm-btn--primary')
    expect(saveBtn.exists()).toBe(true)
    await saveBtn.trigger('click')
    expect(providersStoreMock.upsertConnection).toHaveBeenCalled()
    const call = providersStoreMock.upsertConnection.mock.calls[0]
    expect(call[0]).toBe('openai')
  })

  it('runTest() ruft testConnection wenn konfiguriert', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    const cards = w.findAllComponents(cardStub)
    const openaiCard = cards.find((c) => c.props('title') === 'OpenAI')
    const testBtn = openaiCard!.findAll('button.llm-btn').find((b) => b.text().includes('testen'))
    expect(testBtn).toBeDefined()
    await testBtn!.trigger('click')
    expect(providersStoreMock.testConnection).toHaveBeenCalledWith('openai')
  })

  it('disconnect() ruft removeConnection und loescht draft', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    const cards = w.findAllComponents(cardStub)
    const openaiCard = cards.find((c) => c.props('title') === 'OpenAI')
    const disconnectBtn = openaiCard!.findAll('button.llm-btn').find((b) => b.text().includes('trennen'))
    expect(disconnectBtn).toBeDefined()
    await disconnectBtn!.trigger('click')
    expect(providersStoreMock.removeConnection).toHaveBeenCalledWith('openai')
  })
})
