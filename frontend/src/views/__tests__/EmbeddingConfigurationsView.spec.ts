/**
 * EmbeddingConfigurationsView — Spec-Tests fuer das Anlege-Formular
 * (Issue #1193, Etappe 1/2).
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. laedt Provider-Connections beim Mount
 *  3. oeffnet das Anlege-Modal
 *  4. Submit ruft upsertConfiguration mit korrektem Payload und
 *     anschliessend testConfiguration
 *  5. Dimension 0 -> kein API-Aufruf, Fehlermeldung sichtbar
 *  6. leere Dimension -> kein API-Aufruf, Fehlermeldung sichtbar
 *  7. keine Provider-Connections -> Hinweis statt Formular
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import { reactive } from 'vue'
import EmbeddingConfigurationsView from '../Settings/EmbeddingConfigurationsView.vue'

const configurationsArr = reactive<unknown[]>([])
const migrationByConfigurationObj = reactive<Record<string, unknown>>({})

const probeByConfigurationObj = reactive<Record<string, unknown>>({})

// Steuerbar, damit einzelne Tests die Legacy-Quelle bzw. eine aktive
// Konfiguration einstellen koennen.
const storeState = reactive<{
  activeConfiguration: unknown
  activeSource: 'store' | 'legacy' | 'none'
}>({
  activeConfiguration: null,
  activeSource: 'none',
})

const storeMock = {
  get configurations() { return configurationsArr },
  get configurationsLoading() { return false },
  get configurationsError() { return null },
  get activeConfiguration() { return storeState.activeConfiguration },
  get activeSource() { return storeState.activeSource },
  get migrationByConfiguration() { return migrationByConfigurationObj },
  get probeByConfiguration() { return probeByConfigurationObj },
  loadConfigurations: vi.fn().mockResolvedValue(undefined),
  loadActiveConfiguration: vi.fn().mockResolvedValue(undefined),
  upsertConfiguration: vi.fn(),
  testConfiguration: vi.fn().mockResolvedValue(undefined),
  syncLegacy: vi.fn(),
  deleteConfiguration: vi.fn().mockResolvedValue(undefined),
}

vi.mock('@/store/embeddingConfigurations', () => ({
  useEmbeddingConfigurationsStore: () => storeMock,
}))

const listProviderConnectionsMock = vi.fn()

vi.mock('@/api/providerConnections', () => ({
  listProviderConnections: (...args: unknown[]) => listProviderConnectionsMock(...args),
}))

const CONN_OLLAMA = {
  id: 'conn-ollama-1',
  provider_kind: 'ollama',
  display_name: 'Lokales Ollama',
  transport: 'local',
  auth_mode: 'none',
  base_url: 'http://localhost:11434',
  enabled: true,
  status: 'connected',
  status_message: null,
  secret_ref: null,
  capabilities: {},
  created_at: null,
  updated_at: null,
  last_tested_at: null,
}

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: { de: {} },
  })
}

function makeRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', name: 'SettingsGeneral', component: { template: '<div />' } },
      { path: '/llm-providers', name: 'SettingsLlmProviders', component: { template: '<div />' } },
    ],
  })
  return router
}

async function mountView(initial: { connections?: unknown[] } = {}) {
  configurationsArr.length = 0
  for (const k of Object.keys(migrationByConfigurationObj)) delete migrationByConfigurationObj[k]

  storeMock.loadConfigurations.mockClear()
  storeMock.loadActiveConfiguration.mockClear()
  storeMock.upsertConfiguration.mockClear()
  storeMock.testConfiguration.mockClear()
  storeMock.upsertConfiguration.mockResolvedValue({ id: 'cfg-new-1' })
  storeMock.testConfiguration.mockResolvedValue(undefined)
  storeMock.syncLegacy.mockClear()
  storeMock.syncLegacy.mockResolvedValue({ id: 'cfg-adopted' })
  storeMock.deleteConfiguration.mockClear()
  storeMock.deleteConfiguration.mockResolvedValue(undefined)
  for (const k of Object.keys(probeByConfigurationObj)) delete probeByConfigurationObj[k]
  storeState.activeConfiguration = null
  storeState.activeSource = 'none'

  listProviderConnectionsMock.mockClear()
  listProviderConnectionsMock.mockResolvedValue({
    items: initial.connections ?? [CONN_OLLAMA],
    total: (initial.connections ?? [CONN_OLLAMA]).length,
  })

  const i18n = makeI18n()
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  router.push('/')
  await router.isReady()

  const wrapper = mount(EmbeddingConfigurationsView, {
    global: {
      plugins: [i18n, pinia, router],
      stubs: {
        // AppShell rendert die vollstaendige Sidebar und loest dabei
        // Routen auf, die dieser Router nicht kennt. PageHeader reicht
        // seinen Default-Slot durch, damit die Header-Buttons sichtbar
        // bleiben.
        AppShell: { name: 'AppShell', template: '<div><slot /></div>' },
        PageHeader: {
          name: 'PageHeader',
          props: ['breadcrumbs', 'title'],
          template: '<div><slot /></div>',
        },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('EmbeddingConfigurationsView (Anlege-Formular, #1193)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountView()
    expect(w.exists()).toBe(true)
  })

  it('laedt Provider-Connections beim Mount', async () => {
    await mountView()
    expect(listProviderConnectionsMock).toHaveBeenCalled()
  })

  it('oeffnet das Anlege-Modal', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="create-config-modal"]').exists()).toBe(false)
    await w.find('[data-testid="open-create-config"]').trigger('click')
    expect(w.find('[data-testid="create-config-modal"]').exists()).toBe(true)
  })

  it('Submit ruft upsertConfiguration mit korrektem Payload und danach testConfiguration', async () => {
    const w = await mountView()
    await w.find('[data-testid="open-create-config"]').trigger('click')

    await w.find('[data-testid="create-config-connection"]').setValue('conn-ollama-1')
    await w.find('[data-testid="create-config-model"]').setValue('nomic-embed-text')
    await w.find('[data-testid="create-config-dimensions"]').setValue('768')

    await w.find('[data-testid="create-config-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.upsertConfiguration).toHaveBeenCalledWith('new', {
      provider_connection_id: 'conn-ollama-1',
      provider_kind: 'ollama',
      model_id: 'nomic-embed-text',
      dimensions: 768,
      scope: 'global',
      project_id: null,
    })
    expect(storeMock.testConfiguration).toHaveBeenCalledWith('cfg-new-1')
    expect(w.find('[data-testid="create-config-modal"]').exists()).toBe(false)
  })

  it('fehlgeschlagene Probe bricht den Flow nicht ab', async () => {
    const w = await mountView()
    storeMock.testConfiguration.mockRejectedValueOnce(new Error('probe failed'))
    await w.find('[data-testid="open-create-config"]').trigger('click')
    await w.find('[data-testid="create-config-connection"]').setValue('conn-ollama-1')
    await w.find('[data-testid="create-config-model"]').setValue('nomic-embed-text')
    await w.find('[data-testid="create-config-dimensions"]').setValue('768')

    await w.find('[data-testid="create-config-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.upsertConfiguration).toHaveBeenCalled()
    expect(w.find('[data-testid="create-config-modal"]').exists()).toBe(false)
  })

  it('Dimension 0 -> kein API-Aufruf, Fehlermeldung sichtbar', async () => {
    const w = await mountView()
    await w.find('[data-testid="open-create-config"]').trigger('click')
    await w.find('[data-testid="create-config-connection"]').setValue('conn-ollama-1')
    await w.find('[data-testid="create-config-model"]').setValue('nomic-embed-text')
    await w.find('[data-testid="create-config-dimensions"]').setValue('0')

    await w.find('[data-testid="create-config-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.upsertConfiguration).not.toHaveBeenCalled()
    expect(w.find('[data-testid="create-config-modal"]').text()).toContain('positive Ganzzahl')
  })

  it('leere Dimension -> kein API-Aufruf, Fehlermeldung sichtbar', async () => {
    const w = await mountView()
    await w.find('[data-testid="open-create-config"]').trigger('click')
    await w.find('[data-testid="create-config-connection"]').setValue('conn-ollama-1')
    await w.find('[data-testid="create-config-model"]').setValue('nomic-embed-text')

    await w.find('[data-testid="create-config-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.upsertConfiguration).not.toHaveBeenCalled()
    expect(w.find('[data-testid="create-config-modal"]').text()).toContain('positive Ganzzahl')
  })

  it('keine Provider-Connections -> Hinweis statt Formular', async () => {
    const w = await mountView({ connections: [] })
    await w.find('[data-testid="open-create-config"]').trigger('click')
    expect(w.find('[data-testid="create-config-connection"]').exists()).toBe(false)
    expect(w.text()).toContain('Keine Provider-Connections vorhanden')
  })
})

const CONFIG_PROBED = {
  id: 'cfg-1',
  provider_connection_id: 'conn-ollama-1',
  provider_kind: 'ollama',
  model_id: 'nomic-embed-text',
  dimensions: 768,
  scope: 'global',
  project_id: null,
  index_version: 1,
  status: 'probed',
  status_message: null,
  created_at: null,
  updated_at: null,
  last_validated_at: null,
}

describe('EmbeddingConfigurationsView — Legacy-Uebernahme (#1193)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('zeigt den Uebernehmen-Button nur bei activeSource "legacy"', async () => {
    const w = await mountView()
    expect(w.find('[data-testid="adopt-legacy"]').exists()).toBe(false)

    storeState.activeConfiguration = CONFIG_PROBED
    storeState.activeSource = 'legacy'
    await flushPromises()

    expect(w.find('[data-testid="adopt-legacy"]').exists()).toBe(true)
  })

  it('Submit ruft syncLegacy mit der gewaehlten Connection und danach testConfiguration', async () => {
    const w = await mountView()
    storeState.activeConfiguration = CONFIG_PROBED
    storeState.activeSource = 'legacy'
    await flushPromises()

    await w.find('[data-testid="adopt-legacy"]').trigger('click')
    expect(w.find('[data-testid="adopt-legacy-modal"]').exists()).toBe(true)

    await w.find('[data-testid="adopt-legacy-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.syncLegacy).toHaveBeenCalledWith('conn-ollama-1')
    expect(storeMock.testConfiguration).toHaveBeenCalledWith('cfg-adopted')
    expect(w.find('[data-testid="adopt-legacy-modal"]').exists()).toBe(false)
  })

  it('haelt das Modal offen und zeigt den Fehler, wenn syncLegacy scheitert', async () => {
    const w = await mountView()
    storeState.activeConfiguration = CONFIG_PROBED
    storeState.activeSource = 'legacy'
    await flushPromises()
    storeMock.syncLegacy.mockRejectedValue(new Error('active_configuration_exists'))

    await w.find('[data-testid="adopt-legacy"]').trigger('click')
    await w.find('[data-testid="adopt-legacy-submit"]').trigger('click')
    await flushPromises()

    expect(w.find('[data-testid="adopt-legacy-modal"]').exists()).toBe(true)
    expect(w.find('[data-testid="adopt-legacy-error"]').text()).toContain('active_configuration_exists')
  })
})

describe('EmbeddingConfigurationsView — Loeschen und Dimension-Korrektur (#1193)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loescht erst nach Bestaetigung', async () => {
    const w = await mountView()
    configurationsArr.push(CONFIG_PROBED)
    await flushPromises()

    await w.find('[data-testid="delete-config"]').trigger('click')
    expect(storeMock.deleteConfiguration).not.toHaveBeenCalled()

    await w.find('[data-testid="delete-confirm-submit"]').trigger('click')
    await flushPromises()

    expect(storeMock.deleteConfiguration).toHaveBeenCalledWith('cfg-1')
  })

  it('schuetzt die aktive Konfiguration vor dem Loeschen', async () => {
    const w = await mountView()
    configurationsArr.push({ ...CONFIG_PROBED, status: 'active' })
    await flushPromises()

    expect(w.find('[data-testid="delete-config"]').attributes('disabled')).toBeDefined()
  })

  it('bietet die gemessene Dimension nur bei Abweichung an und uebernimmt sie', async () => {
    const w = await mountView()
    configurationsArr.push({ ...CONFIG_PROBED, status: 'failed' })
    await flushPromises()
    expect(w.find('[data-testid="apply-measured-dimensions"]').exists()).toBe(false)

    probeByConfigurationObj['cfg-1'] = {
      status: 'available',
      status_message: null,
      actual_dimensions: 1024,
    }
    await flushPromises()

    const button = w.find('[data-testid="apply-measured-dimensions"]')
    expect(button.exists()).toBe(true)
    await button.trigger('click')
    await flushPromises()

    expect(storeMock.upsertConfiguration).toHaveBeenCalledWith(
      'cfg-1',
      expect.objectContaining({ dimensions: 1024, model_id: 'nomic-embed-text' }),
    )
    expect(storeMock.testConfiguration).toHaveBeenCalledWith('cfg-1')
  })
})
