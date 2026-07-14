/**
 * Home — minimaler Migrations-Spec fuer Slice 7.6b.
 *
 * Drei essenzielle Pruefungen (User-Direktive "nur die noetigste"):
 *  - Picker-Anbindung: AiModelPicker gerendert, ModelPicker (v4 legacy) NICHT
 *  - LocalStorage-Migration: onPickModel schreibt agora.home.aiModelRef +
 *    STORAGE_MODEL-Spiegel via adapter.toStoredModelString
 *  - null-Pfad: bei null werden beide Keys entfernt + STORAGE_MODEL='default'
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import Home from '../Home.vue'

const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
  emits: ['update:modelValue'],
  template:
    '<div data-testid="ai-model-picker-stub" '
    + '@click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-openai-1\', model_id: \'gpt-4o-mini\', source: \'explicit\' })">picker</div>',
}

const legacyModelPickerStub = {
  name: 'ModelPicker',
  props: ['modelValue', 'placeholder', 'disabled'],
  emits: ['update:modelValue'],
  template: '<select data-testid="legacy-model-picker-stub" disabled></select>',
}

const stubs = {
  AiModelPicker: aiPickerStub,
  ModelPicker: legacyModelPickerStub,
  HistoryDatabase: { template: '<div />' },
  AppFooter: { template: '<div />' },
  Button: { template: '<button><slot /></button>' },
  Badge: { template: '<span><slot /></span>' },
  Kicker: { template: '<span><slot /></span>' },
  Select: { template: '<select />' },
  AgoraGlyph: { template: '<span />' },
  AgoraBrand: { template: '<span />' },
}

const setPendingUploadMock = vi.fn()
const routerPushMock = vi.fn()

vi.mock('../api/simulation', () => ({
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: { default_provider: 'ollama', ollama_reachable: true, neo4j_reachable: true, default_language: 'de' },
  }),
}))
vi.mock('../store/pendingUpload', () => ({ setPendingUpload: setPendingUploadMock }))
vi.mock('../composables/useEnvForm', () => ({ STORAGE_LANG: 'agora.lang', STORAGE_MODEL: 'agora.lastModel' }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPushMock }) }))

const adapterMock = {
  toStageLlmRoute: vi.fn(),
  toAiModelRef: vi.fn(),
  toStoredModelString: vi.fn((aiRef: { model_id: string } | null) => aiRef?.model_id ?? 'default'),
  migrateStoredRoute: vi.fn(() => null),
}
vi.mock('@/composables/useAiModelRefAdapter', () => ({ useAiModelRefAdapter: () => adapterMock }))

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((k: string) => store[k] ?? null),
    setItem: vi.fn((k: string, v: string) => { store[k] = v }),
    removeItem: vi.fn((k: string) => { delete store[k] }),
    clear: () => { store = {} },
  }
})()

const makeI18n = () => createI18n({
  legacy: false,
  locale: 'de',
  fallbackLocale: 'de',
  messages: {
    de: {
      home: {
        edition: '', location: '',
        headline: { line1: '', line2: '', line3Italic: '' },
        lead: '', tags: { engine: '', version: '' },
        system: { kicker: '', title: '', desc: '' },
        metrics: { free: { value: '', label: '' }, private: { value: '', label: '' }, openSource: { value: '', label: '' } },
        workflow: { kicker: '' },
        console: {
          uploadKicker: '', uploadAccepted: '', uploadTitle: '', uploadHint: '',
          promptKicker: '', engineLabel: '', promptPlaceholder: '',
          startBtn: 'Start', initializing: 'Init', needFiles: '', needPrompt: '',
        },
        steps: [], differentiators: [],
      },
      history: { kicker: '' }, nav: { available: '' }, brand: { name: 'Agora', tagline: '' },
      step2: {
        model: { label: 'Modell', placeholder: '', workspaceDefaultHint: '', noOllama: '' },
        language: { label: '', de: 'DE', en: 'EN', hint: '' },
      },
      common: { refresh: '' }, aiModelPicker: { placeholder: '' },
    },
  },
})

async function mountHome() {
  localStorageMock.clear()
  for (const m of [localStorageMock.getItem, localStorageMock.setItem, localStorageMock.removeItem, adapterMock.toStoredModelString, adapterMock.migrateStoredRoute]) m.mockClear()
  adapterMock.migrateStoredRoute.mockReturnValue(null)
  vi.stubGlobal('localStorage', localStorageMock)
  const pinia = createPinia(); setActivePinia(pinia)
  return mount(Home, { global: { plugins: [makeI18n()], stubs } })
}

describe('Home (Slice 7.6b, minimal)', () => {
  beforeEach(() => { installLocalStorageSafe() })
  afterEach(() => { vi.unstubAllGlobals() })

  it('rendert AiModelPicker, nicht ModelPicker (v4 legacy)', async () => {
    const w = await mountHome()
    await flushPromises()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
    expect(w.findComponent(legacyModelPickerStub).exists()).toBe(false)
  })

  it('onPickModel: persistiert aiModelRef + STORAGE_MODEL-Spiegel via Adapter', async () => {
    const w = await mountHome()
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    await flushPromises()
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'agora.home.aiModelRef',
      expect.stringContaining('gpt-4o-mini'),
    )
    const modelCall = localStorageMock.setItem.mock.calls.find((c) => c[0] === 'agora.lastModel')
    expect(modelCall?.[1]).toBe('gpt-4o-mini')
  })

  it('onPickModel: bei null werden aiModelRef+Legacy-Key entfernt + STORAGE_MODEL="default"', async () => {
    const w = await mountHome()
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    await flushPromises()
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.home.aiModelRef')
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.home.route')
    const modelCall = localStorageMock.setItem.mock.calls.find((c) => c[0] === 'agora.lastModel')
    expect(modelCall?.[1]).toBe('default')
  })
})

function installLocalStorageSafe() { vi.stubGlobal('localStorage', localStorageMock) }