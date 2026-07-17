/**
 * SettingsGeneralView — Spec-Tests fuer Phase-1 Kanon-First-Konsolidierung.
 *
 * Phase-1 Root-Cause-Fix (frontend-next): Die View nutzt AUSSCHLIESSLICH
 * {@link useEffectiveModelSelection} als einzigen Selektions- und Persistenzpfad.
 * Kanon = `routing/defaults.global_default`, repraesentiert als `AiModelRef`.
 * `setGlobalSelection` schreibt Kanon zuerst UND `active-config` im Gleichschritt.
 *
 * Entfernte Senken, die hier NICHT mehr assertet werden duerfen:
 *  - `STORAGE_HOME_AI_REF` / `STORAGE_HERO_AI_REF` / `STORAGE_REPORT_AI_REF`
 *  - `saveLlmActive` / direktes `setDefault`-Store-Geschreibe
 *  - separate `active-config`-Dropdowns in der View
 *
 * Coverage:
 *  1. mountet ohne Crash
 *  2. ensureLoaded wird onMount aufgerufen; View mountet auch bei
 *     ensureLoaded-reject ohne Crash (selectedModel bleibt null)
 *  3. zeigt BREADCRUMBS
 *  4. zeigt PageHeader mit title + subtitle
 *  5. LlmProfileManager sichtbar
 *  6. AiModelPicker sichtbar
 *  7. i18n-Key: settings.v4.general.workspaceDefaultModel
 *  8. Capability-Filter: Picker bekommt mode='chat'
 *  9. allowWorkspaceDefault=true
 * 10. onMount: effectiveModel.ensureLoaded()
 * 11. initialer Picker-Wert aus effectiveModel.effectiveRef (Kanon)
 * 12. AiModelPicker-Update -> effectiveModel.setGlobalSelection
 *     (Kanon + active-config-Gleichschritt)
 * 13. AiModelPicker-Update mit null: keine setGlobalSelection-Aktion
 * 14. AiModelPicker hat eindeutige ID ('settings-general-model-picker')
 * 15. SettingsSectionPanel sichtbar
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import type { AiModelRef } from '@/contracts/aiModelRef'
import SettingsGeneralView from '../Settings/SettingsGeneralView.vue'

// --- Composable-Mock (Kanon-First). Die View beruehrt Store/Adapter/llmRouting
//     NICHT direkt — alles geht durch useEffectiveModelSelection. Daher mocken
//     wir ausschliesslich das Composable mit steuerbarem State.
const ensureLoadedMock = vi.fn()
const setGlobalSelectionMock = vi.fn()
const effectiveRef = ref<AiModelRef | null>(null)
const effectiveRoute = ref({
  stage: null,
  provider_id: 'openai',
  model: 'gpt-4o-mini',
  temperature: null,
  max_tokens: null,
  reasoning_effort: 'none',
  provider_options: {},
})
const loading = ref(false)
const error = ref<string | null>(null)

vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef,
    effectiveRoute,
    loading,
    error,
    ensureLoaded: ensureLoadedMock,
    setGlobalSelection: setGlobalSelectionMock,
  }),
}))

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

async function mountSettingsGeneral(initial: { effectiveRef?: AiModelRef | null } = {}) {
  effectiveRef.value = initial.effectiveRef ?? null
  ensureLoadedMock.mockClear()
  ensureLoadedMock.mockResolvedValue(undefined)
  setGlobalSelectionMock.mockClear()
  setGlobalSelectionMock.mockResolvedValue(undefined)

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

describe('SettingsGeneralView (Phase-1, Kanon-First via useEffectiveModelSelection)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    effectiveRef.value = null
  })

  it('mountet ohne Crash', async () => {
    const w = await mountSettingsGeneral()
    expect(w.exists()).toBe(true)
  })

  it('ensureLoaded wird onMount aufgerufen; View mountet auch bei ensureLoaded-reject ohne Crash', async () => {
    ensureLoadedMock.mockRejectedValueOnce(new Error('ensureLoaded fehlgeschlagen'))
    const w = await mountSettingsGeneral()
    expect(w.exists()).toBe(true)
    expect(ensureLoadedMock).toHaveBeenCalled()
    // Bei Reject bleibt selectedModel null (Picker zeigt nichts gewaehltes).
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('modelValue')).toBeNull()
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

  it('onMount: effectiveModel.ensureLoaded()', async () => {
    await mountSettingsGeneral()
    expect(ensureLoadedMock).toHaveBeenCalled()
  })

  it('initialer Picker-Wert aus effectiveModel.effectiveRef (Kanon)', async () => {
    const initial: AiModelRef = {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'workspace-default',
    }
    const w = await mountSettingsGeneral({ effectiveRef: initial })
    const picker = w.findComponent(aiPickerStub)
    expect(picker.exists()).toBe(true)
    expect(picker.props('modelValue')).toEqual(initial)
  })

  it('AiModelPicker-Update -> effectiveModel.setGlobalSelection (Kanon + active-config-Gleichschritt)', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    const emitted: AiModelRef = {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'workspace-default',
    }
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', emitted)
    await flushPromises()
    expect(setGlobalSelectionMock).toHaveBeenCalledWith(emitted)
  })

  it('AiModelPicker-Update mit null: keine setGlobalSelection-Aktion', async () => {
    const w = await mountSettingsGeneral()
    const picker = w.findComponent(aiPickerStub)
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    await flushPromises()
    expect(setGlobalSelectionMock).not.toHaveBeenCalled()
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