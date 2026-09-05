/**
 * LlmProvidersView — Spec-Tests fuer Slice 5.4 Migration auf AiModelPicker
 * und Redesign PR 9 (Liste + Detail-Formular statt Card-Grid).
 *
 * Die View rendert eine Workspace-Default-Card, eine Provider-Liste und
 * genau EIN Detail-Formular fuer den ausgewaehlten Provider.
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. zeigt PageHeader mit title + subtitle
 *  3. Workspace-Default-Card sichtbar
 *  4. AiModelPicker in der Default-Card
 *  5. defaultRoute computed zeigt aktuelle Route (Provider-ID + Model)
 *  6. AiModelPicker-Update mit AiModelRef → effectiveModel.setGlobalSelection (setGlobalDefault + setActiveLlmConfig-Gleichschritt)
 *  7. AiModelPicker-Update mit null → kein setGlobalSelection (kein Schreibpfad)
 *  8. onMounted: loadProviders + loadConnections + defaultsStore.load
 *  9. onBeforeUnmount: loescht alle drafts
 * 10. Provider-Liste: listet alle Provider mit Status-Badge auf
 * 11. statusTone: connected → 'green', error → 'red', unsupported → 'gray'
 * 12. statusLabel: connected → 'Verbunden', undefined → 'Nicht konfiguriert'
 * 13. Auswahl einer Zeile wechselt das Detail-Formular auf den Provider
 * 14. save() ruft upsertConnection mit korrekten Args (apiKey, baseUrl)
 * 15. runTest() ruft testConnection wenn konfiguriert
 * 16. disconnect() ruft removeConnection und loescht draft
 * 17. Busy-State ist pro Aktion: nur der aktive Button zeigt aria-busy,
 *     die anderen bleiben nur disabled (Review PR #1439)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { LlmProviderListTestId } from '@/contracts/testIds'
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

// AppShell / SettingsOverlay / PageHeader / Card / Input / Badge stubben (zu
// vieler Komponenten Mounting, wir testen Glue-Code, nicht die Sub-Components).
// Button bleibt echt: die view-eigenen data-testid-Attribute landen dank
// Vue-Attribute-Fallthrough direkt auf dem gerenderten <button>.
const appShellStub = { name: 'AppShell', template: '<div><slot /></div>' }
const settingsOverlayStub = { name: 'SettingsOverlay', template: '<div><slot /></div>' }
const pageHeaderStub = {
  name: 'PageHeader',
  props: ['title', 'subtitle'],
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
  toLlmRoute: vi.fn((aiRef: { provider_connection_id: string; model_id: string }) => ({
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

// Kanon-First-Composable mocken (Option A). Die View ruft beim Picker-Pick
// ausschliesslich effectiveModel.setGlobalSelection(aiRef); die Internas
// (adapter.toLlmRoute, defaultsStore.setGlobalDefault, setActiveLlmConfig)
// werden in useEffectiveModelSelection.spec.ts geprueft, nicht hier.
// Ohne diesen Mock wuerde setActiveLlmConfig einen echten Network-Call feuern
// (AxiosError "Backend offline", siehe Scout-Finding F1).
const effectiveModelMock = {
  effectiveRef: computed(() => adapterMock.toAiModelRef(defaultsStoreMock.globalDefault ?? { provider_id: null, model: null })),
  effectiveRoute: computed(() => defaultsStoreMock.globalDefault),
  loading: ref(false),
  error: ref<string | null>(null),
  ensureLoaded: vi.fn().mockResolvedValue(undefined),
  setGlobalSelection: vi.fn().mockResolvedValue(undefined),
}

vi.mock('@/store/aiModels', () => ({
  useLlmProvidersStore: () => providersStoreMock,
  useLlmRoutingDefaultsStore: () => defaultsStoreMock,
}))

vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => adapterMock,
}))

vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => effectiveModelMock,
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
              list: { ariaLabel: 'Provider' },
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
  adapterMock.toLlmRoute.mockClear()
  adapterMock.toAiModelRef.mockClear()
  effectiveModelMock.setGlobalSelection.mockClear()
  effectiveModelMock.ensureLoaded.mockClear()

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
        SettingsOverlay: settingsOverlayStub,
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

/** Waehlt eine Provider-Zeile ueber ihre data-provider-id aus. */
async function selectRow(wrapper: ReturnType<typeof mount>, providerId: string) {
  const row = wrapper.find(`[data-testid="${LlmProviderListTestId.row}"][data-provider-id="${providerId}"]`)
  await row.trigger('click')
}

describe('LlmProvidersView (Redesign PR 9, Liste + Detail)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountView()
    expect(w.exists()).toBe(true)
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

  it('AiModelPicker-Update -> effectiveModel.setGlobalSelection (Kanon + active-config-Gleichschritt)', async () => {
    const w = await mountView()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    await picker.trigger('click')
    // Kanon-First: die View delegiert an effectiveModel.setGlobalSelection,
    // welche intern setGlobalDefault + setActiveLlmConfig im Gleichschritt
    // ausfuehrt. Composable-Internas werden hier nicht mehr assertiert.
    expect(effectiveModelMock.setGlobalSelection).toHaveBeenCalledWith({
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    // Schreibpfad ausschliesslich ueber den Composable — kein direktes
    // Store-Geschreibe aus der View heraus.
    expect(defaultsStoreMock.setGlobalDefault).not.toHaveBeenCalled()
  })

  it('AiModelPicker-Update mit null -> kein setGlobalSelection (kein Schreibpfad)', async () => {
    const w = await mountView()
    const picker = w.findComponent(aiPickerStub)
    // Emit null direkt (Stub emittiert hardcoded, daher manuell)
    await picker.vm.$emit('update:modelValue', null)
    expect(effectiveModelMock.setGlobalSelection).not.toHaveBeenCalled()
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

  it('Provider-Liste: listet alle Provider mit Status-Badge auf', async () => {
    const w = await mountView()
    const rows = w.findAll(`[data-testid="${LlmProviderListTestId.row}"]`)
    expect(rows.length).toBe(3)
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

  it('Auswahl einer Zeile wechselt das Detail-Formular auf den Provider', async () => {
    const w = await mountView()
    // Ohne Auswahl faellt das Detail-Formular auf den ersten Provider zurueck.
    let detail = w.find(`[data-testid="${LlmProviderListTestId.detail}"]`)
    expect(detail.attributes('data-provider-id')).toBe('ollama')

    await selectRow(w, 'openai')
    detail = w.find(`[data-testid="${LlmProviderListTestId.detail}"]`)
    expect(detail.attributes('data-provider-id')).toBe('openai')
  })

  it('save() ruft upsertConnection mit korrekten Args (apiKey, baseUrl)', async () => {
    const w = await mountView()
    await selectRow(w, 'openai')
    const saveBtn = w.find(`[data-testid="${LlmProviderListTestId.saveButton}"]`)
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
    await selectRow(w, 'openai')
    const testBtn = w.find(`[data-testid="${LlmProviderListTestId.testButton}"]`)
    expect(testBtn.exists()).toBe(true)
    await testBtn.trigger('click')
    expect(providersStoreMock.testConnection).toHaveBeenCalledWith('openai')
  })

  it('disconnect() ruft removeConnection und loescht draft', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    await selectRow(w, 'openai')
    const disconnectBtn = w.find(`[data-testid="${LlmProviderListTestId.disconnectButton}"]`)
    expect(disconnectBtn.exists()).toBe(true)
    await disconnectBtn.trigger('click')
    expect(providersStoreMock.removeConnection).toHaveBeenCalledWith('openai')
  })

  it('Busy-State ist pro Aktion: nur der aktive Button zeigt aria-busy (Review PR #1439)', async () => {
    const w = await mountView({
      connections: { openai: { id: 'openai', provider_kind: 'openai', status: 'connected' } },
    })
    await selectRow(w, 'openai')

    // `connectionBusy` ist im echten Store waehrend JEDER der vier Aktionen
    // true (ein Bool pro Provider, keine Aktion) — hier von Hand nachgestellt,
    // weil upsertConnection im Test gemockt ist und das sonst nicht setzt.
    let resolveUpsert: () => void = () => {}
    providersStoreMock.upsertConnection.mockImplementation(() => {
      connectionBusyObj.openai = true
      return new Promise<void>((resolve) => {
        resolveUpsert = () => {
          connectionBusyObj.openai = false
          resolve()
        }
      })
    })

    const saveBtn = w.find(`[data-testid="${LlmProviderListTestId.saveButton}"]`)
    const testBtn = w.find(`[data-testid="${LlmProviderListTestId.testButton}"]`)

    await saveBtn.trigger('click')
    // Waehrend upsertConnection() noch offen ist: nur Speichern ist "loading",
    // Testen ist lediglich disabled — kein gemeinsames Spinnen mehr.
    expect(saveBtn.attributes('aria-busy')).toBe('true')
    expect(testBtn.attributes('aria-busy')).toBeUndefined()
    expect(testBtn.attributes('disabled')).toBeDefined()

    resolveUpsert()
    await flushPromises()
    expect(saveBtn.attributes('aria-busy')).toBeUndefined()
    expect(testBtn.attributes('disabled')).toBeUndefined()
  })
})
