/**
 * SettingsGeneralView — Spec-Tests fuer Slice 5.4 Pilot-Abschluss.
 *
 * Die View wurde in Slice 5.2 als Pilot auf AiModelPicker migriert, hatte
 * aber keinen Persistenz-Anschluss an den Workspace-Default-Store. Slice
 * 5.4 schliesst das:
 *  - AiModelPicker-Update -> useAiModelRefAdapter -> setGlobalDefault
 *  - Initial-Wert aus defaultsStore.globalDefault (via Adapter)
 *  - i18n-Keys veredelt (settings.v4.general.workspaceDefaultModel)
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. zeigt BREADCRUMBS
 *  3. zeigt PageHeader mit title + subtitle
 *  4. LlmProfileManager sichtbar
 *  5. AiModelPicker sichtbar
 *  6. i18n-Key: settings.v4.general.workspaceDefaultModel
 *  7. Capability-Filter: Picker bekommt mode='chat'
 *  8. allowWorkspaceDefault=true
 *  9. onMount: defaultsStore.load()
 * 10. initialer Picker-Wert aus defaultsStore.globalDefault (via Adapter)
 * 11. AiModelPicker-Update mit AiModelRef -> adapter.toStageLlmRoute -> setGlobalDefault
 * 12. AiModelPicker-Update mit null: keine setGlobalDefault-Aktion
 * 13. AiModelPicker hat eindeutige ID ('settings-general-model-picker')
 * 14. SettingsSectionPanel sichtbar
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { ref, reactive } from 'vue'
import { listLlmProviders } from '@/api/llmRouting'
import SettingsGeneralView from '../Settings/SettingsGeneralView.vue'

// AiModelPicker mocken
const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'allowWorkspaceDefault', 'id'],
  emits: ['update:modelValue'],
  template: '<div data-testid="ai-model-picker-stub" :data-mode="mode" :data-allow-ws="allowWorkspaceDefault" :data-id="id" @click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'workspace-default\' })">picker</div>',
}

const appShellStub = {
  name: 'AppShell',
  props: ['breadcrumbs'],
  template: '<div data-testid="app-shell" :data-crumbs-len="(breadcrumbs || []).length"><slot /></div>',
}
const pageHeaderStub = {
  name: 'PageHeader',
  props: ['title', 'subtitle', 'breadcrumbs'],
  template: '<div data-testid="page-header" :data-title="title" :data-subtitle="subtitle"><slot /></div>',
}
const llmProfileManagerStub = { name: 'LlmProfileManager', template: '<div data-testid="llm-profile-manager" />' }
const settingsSectionPanelStub = {
  name: 'SettingsSectionPanel',
  props: ['allowedSections'],
  template: '<div data-testid="settings-section-panel" />',
}

const loadMock = vi.fn()
const setGlobalDefaultMock = vi.fn()
let globalDefaultRef: unknown = null

vi.mock('@/store/aiModels', () => ({
  useLlmRoutingDefaultsStore: () => ({
    get globalDefault() { return globalDefaultRef },
    load: loadMock,
    setGlobalDefault: setGlobalDefaultMock,
  }),
}))

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
    source: 'workspace-default' as const,
  })),
}

vi.mock('@/composables/useAiModelRefAdapter', () => ({
  useAiModelRefAdapter: () => adapterMock,
}))

vi.mock('@/api/llmRouting', () => ({
  listLlmProviders: vi.fn().mockResolvedValue([
    { id: 'ollama', label: 'Ollama' },
  ]),
  listProviderModels: vi.fn().mockResolvedValue([
    { id: 'qwen3', label: 'Qwen 3' },
  ]),
  getActiveLlmConfig: vi.fn().mockResolvedValue({ provider_id: 'ollama', model: 'qwen3' }),
  setActiveLlmConfig: vi.fn().mockResolvedValue({ provider_id: 'ollama', model: 'qwen3' }),
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'de',
    messages: {
      de: {
        settings: {
          llmActive: {
            title: 'Aktiver LLM-Anbieter und Modell',
            subtitle: 'Backend-Fallback fuer LLM-Aufrufe',
            providerLabel: 'Provider',
            modelLabel: 'Modell',
            providerPlaceholder: 'Provider waehlen',
            providerLoading: 'Provider werden geladen',
            modelPlaceholder: 'Modell waehlen',
            modelLoading: 'Modelle werden geladen',
            modelEmpty: 'Keine Modelle gefunden',
            modelNeedsProvider: 'Erst Provider waehlen',
            save: 'Speichern',
            flashSaved: 'Auswahl gespeichert',
            errorSelectionMissing: 'Provider und Modell waehlen',
            errorLoadProviders: 'Provider konnten nicht geladen werden',
            errorLoadModels: 'Modelle konnten nicht geladen werden',
            errorLoadActive: 'Aktive Auswahl konnte nicht geladen werden',
            errorSaveFailed: 'Speichern fehlgeschlagen',
          },
          v4: {
            general: {
              title: 'Allgemein',
              subtitle: 'Globale Einstellungen',
              workspaceDefaultModel: 'Standardmodell fuer den Workspace',
            },
          },
        },
        aiModelPicker: { label: 'Modell waehlen' },
      },
    },
  })
}

async function mountSettingsGeneral(initial: { globalDefault?: unknown } = {}) {
  globalDefaultRef = initial.globalDefault ?? null
  loadMock.mockClear()
  loadMock.mockResolvedValue(undefined)
  setGlobalDefaultMock.mockClear()
  setGlobalDefaultMock.mockResolvedValue(undefined)
  adapterMock.toStageLlmRoute.mockClear()
  adapterMock.toAiModelRef.mockClear()

  const i18n = makeI18n()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(SettingsGeneralView, {
    global: {
      plugins: [i18n],
      stubs: {
        AiModelPicker: aiPickerStub,
        AppShell: appShellStub,
        PageHeader: pageHeaderStub,
        LlmProfileManager: llmProfileManagerStub,
        SettingsSectionPanel: settingsSectionPanelStub,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('SettingsGeneralView (Slice 5.4, Pilot-Abschluss mit Persistenz)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('mountet ohne Crash', async () => {
    const w = await mountSettingsGeneral()
    expect(w.exists()).toBe(true)
  })

  it('behält den Provider-Discovery-Fehler, wenn active-config und Modelle laden', async () => {
    vi.mocked(listLlmProviders).mockRejectedValueOnce(new Error('Provider-Discovery fehlgeschlagen'))

    const w = await mountSettingsGeneral()

    expect(w.get('[role="alert"]').text()).toContain('Provider-Discovery fehlgeschlagen')
  })

  it('zeigt BREADCRUMBS via AppShell', async () => {
    const w = await mountSettingsGeneral()
    const shell = w.findComponent(appShellStub)
    expect(shell.exists()).toBe(true)
    const crumbs = shell.props('breadcrumbs') as Array<{ label: string }>
    expect(crumbs.length).toBeGreaterThanOrEqual(2)
    expect(crumbs[0].label).toBe('Settings')
  })

  it('zeigt PageHeader mit title + subtitle', async () => {
    const w = await mountSettingsGeneral()
    const ph = w.findComponent({ name: 'PageHeader' })
    expect(ph.props('title')).toContain('Allgemein')
  })

  it('LlmProfileManager sichtbar', async () => {
    const w = await mountSettingsGeneral()
    expect(w.find('[data-testid="llm-profile-manager"]').exists()).toBe(true)
  })

  it('AiModelPicker sichtbar', async () => {
    const w = await mountSettingsGeneral()
    expect(w.find('[data-testid="ai-model-picker-stub"]').exists()).toBe(true)
  })

  it('i18n-Key: settings.v4.general.workspaceDefaultModel rendert Label', async () => {
    const w = await mountSettingsGeneral()
    expect(w.text()).toContain('Standardmodell fuer den Workspace')
  })

  it('Capability-Filter: Picker bekommt mode="chat"', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('mode')).toBe('chat')
  })

  it('allowWorkspaceDefault=true', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('allowWorkspaceDefault')).toBe(true)
  })

  it('onMount: defaultsStore.load()', async () => {
    await mountSettingsGeneral()
    expect(loadMock).toHaveBeenCalled()
  })

  it('initialer Picker-Wert aus defaultsStore.globalDefault (via Adapter)', async () => {
    const w = await mountSettingsGeneral({
      globalDefault: { provider_id: 'ollama', model: 'qwen3', temperature: null, max_tokens: null, reasoning_effort: 'none', provider_options: {} },
    })
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    // adapter.toAiModelRef wurde fuer die Initial-Konvertierung aufgerufen
    expect(adapterMock.toAiModelRef).toHaveBeenCalled()
  })

  it('AiModelPicker-Update mit AiModelRef -> adapter.toStageLlmRoute -> setGlobalDefault', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'workspace-default',
    })
    await flushPromises()
    expect(adapterMock.toStageLlmRoute).toHaveBeenCalled()
    expect(setGlobalDefaultMock).toHaveBeenCalledWith({
      stage: null,
      provider_id: 'openai',
      model: 'gpt-4o-mini',
      temperature: null,
      max_tokens: null,
      reasoning_effort: 'none',
      provider_options: {},
    })
  })

  it('AiModelPicker-Update mit null: keine setGlobalDefault-Aktion', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    await flushPromises()
    expect(setGlobalDefaultMock).not.toHaveBeenCalled()
  })

  it('AiModelPicker hat eindeutige ID', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('id')).toBe('settings-general-model-picker')
  })

  it('SettingsSectionPanel sichtbar', async () => {
    const w = await mountSettingsGeneral()
    expect(w.find('[data-testid="settings-section-panel"]').exists()).toBe(true)
  })
})
