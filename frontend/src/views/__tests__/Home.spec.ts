/**
 * Home — Kanon-First-Spec (Phase-1 Konsolidierung, frontend-next).
 *
 * Drei Kanon-First-Pruefungen + zwei Init-Tests:
 *  - Picker-Anbindung: AiModelPicker gerendert, ModelPicker (v4 legacy) NICHT
 *  - Picker-Pick ist TRANSIENT (KEIN setGlobalSelection): Beim Start wird der
 *    volle AiModelRef als Run-Override gespeichert; Legacy-Modell-Keys bleiben
 *    unangetastet.
 *  - null-Pfad: entfernt agora.home.route, modelOverridden wird wieder false.
 *  - Kanon-First-Init: selectedModel wird aus effectiveRef vorbelegt, wenn
 *    der User nichts waehlt (ensureLoaded in onMounted aufgerufen).
 *  - Nach explizitem Pick (modelOverridden=true) ueberschreibt die
 *    Kanon-Vorbelegung selectedModel nicht mehr.
 *
 * Entfernte Senken, die NICHT mehr assertet werden duerfen:
 * STORAGE_HOME_AI_REF (agora.home.aiModelRef), saveLlmActive, direktes
 * setDefault-Store-Geschreibe.
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
const runOverrideMocks = vi.hoisted(() => ({
  set: vi.fn(),
  clear: vi.fn(),
}))

vi.mock('@/api/simulation', () => ({
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: { default_provider: 'ollama', ollama_reachable: true, neo4j_reachable: true, default_language: 'de' },
  }),
}))
vi.mock('../store/pendingUpload', () => ({ setPendingUpload: setPendingUploadMock }))
vi.mock('../composables/useEnvForm', () => ({ STORAGE_LANG: 'agora.lang' }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPushMock }) }))
vi.mock('@/store/runModelOverride', () => ({
  setRunModelOverride: runOverrideMocks.set,
  clearRunModelOverride: runOverrideMocks.clear,
}))

// ---- Kanon-Composable-Mock (steuerbar, Kanon-First). ----
// effectiveRef/effectiveRoute als Plain-Ref-Objekte (.value wird von Home
// gelesen), ensureLoaded/setGlobalSelection als vi.fns, damit wir Aufruf
// UND Nicht-Aufruf asserten koennen. vi.hoisted, damit der Mock-Factory die
// Halter-Referenz schon vor dem Hoisten sieht.
const effMock = vi.hoisted(() => ({
  effectiveRefValue: null as unknown,
  effectiveRouteValue: null as unknown,
  ensureLoadedImpl: null as ((...a: unknown[]) => Promise<void>) | null,
  setGlobalSelection: null as ((...a: unknown[]) => Promise<void>) | null,
  resolveEnsureLoaded: null as (() => void) | null,
}))
vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { value: effMock.effectiveRefValue },
    effectiveRoute: { value: effMock.effectiveRouteValue },
    loading: { value: false },
    error: { value: null },
    ensureLoaded: (...args: unknown[]) => effMock.ensureLoadedImpl!(...args),
    setGlobalSelection: (...args: unknown[]) => effMock.setGlobalSelection!(...args),
  }),
}))

// Kanon-Default, der via effectiveRef vorbelegt wird (unterscheidbar vom
// Picker-Pick gpt-4o-mini, damit Verwechslung auffaellt).
const kanonAiRef = {
  provider_connection_id: 'conn-anthropic-1',
  model_id: 'claude-sonnet-4',
  source: 'workspace_default',
}
const kanonRoute = { provider: 'anthropic', model: 'claude-sonnet-4' }

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
        // Erkennbarer Text, damit wir modelOverridden===false am gerenderten
        // workspaceDefaultHint-Paragraph (v-if="!modelOverridden && !loadingModels")
        // verifizieren koennen.
        model: { label: 'Modell', placeholder: '', workspaceDefaultHint: 'WORKSPACE_DEFAULT_HINT', noOllama: '' },
        language: { label: '', de: 'DE', en: 'EN', hint: '' },
      },
      common: { refresh: '' }, aiModelPicker: { placeholder: '' },
    },
  },
})

function resetEffMock(opts: { deferEnsureLoaded?: boolean } = {}) {
  effMock.effectiveRefValue = kanonAiRef
  effMock.effectiveRouteValue = kanonRoute
  effMock.setGlobalSelection = vi.fn().mockResolvedValue(undefined)
  effMock.resolveEnsureLoaded = null
  if (opts.deferEnsureLoaded) {
    effMock.ensureLoadedImpl = vi.fn(() => new Promise<void>((resolve) => {
      effMock.resolveEnsureLoaded = resolve
    }))
  } else {
    effMock.ensureLoadedImpl = vi.fn().mockResolvedValue(undefined)
  }
}

async function mountHome() {
  localStorageMock.clear()
  for (const m of [localStorageMock.getItem, localStorageMock.setItem, localStorageMock.removeItem]) m.mockClear()
  runOverrideMocks.set.mockClear()
  runOverrideMocks.clear.mockClear()
  vi.stubGlobal('localStorage', localStorageMock)
  const pinia = createPinia(); setActivePinia(pinia)
  return mount(Home, { global: { plugins: [makeI18n()], stubs } })
}

describe('Home (Kanon-First, Phase-1)', () => {
  beforeEach(() => {
    installLocalStorageSafe()
    resetEffMock()
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('rendert AiModelPicker, nicht ModelPicker (v4 legacy)', async () => {
    const w = await mountHome()
    await flushPromises()
    expect(w.findComponent(aiPickerStub).exists()).toBe(true)
    expect(w.findComponent(legacyModelPickerStub).exists()).toBe(false)
  })

  it('onPickModel berührt die Legacy-Modell-Keys nicht und speichert den Override noch nicht', async () => {
    const w = await mountHome()
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    picker.vm.$emit('update:modelValue', {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    await flushPromises()

    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    expect(runOverrideMocks.set).not.toHaveBeenCalled()

    // (b) Legacy-Route-Key defensiv entfernt (mindestens beim Pick).
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.home.route')

    // (c) agora.home.aiModelRef wird weder gelesen noch geschrieben noch entfernt.
    const aiRefKeyCalls = [
      ...localStorageMock.getItem.mock.calls,
      ...localStorageMock.setItem.mock.calls,
      ...localStorageMock.removeItem.mock.calls,
    ].filter((c) => c[0] === 'agora.home.aiModelRef')
    expect(aiRefKeyCalls).toHaveLength(0)

    // (d) Picker-Pick ist transient — Kanon-Schreibpfad wird NICHT beruehrt.
    expect(effMock.setGlobalSelection).not.toHaveBeenCalled()
  })

  it('onPickModel(null) schreibt oder cleart keine Legacy-Modell-Keys', async () => {
    const w = await mountHome()
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    ;(picker.vm as unknown as { $emit: (e: string, v: unknown) => void }).$emit('update:modelValue', null)
    await flushPromises()

    // Legacy-Route-Key entfernt (onMounted + beim null-Pick).
    expect(localStorageMock.removeItem).toHaveBeenCalledWith('agora.home.route')
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastModel')
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.lastCustomModel')
    // Entfernter aiModelRef-Sink wird NICHT angeruehrt.
    expect(localStorageMock.removeItem).not.toHaveBeenCalledWith('agora.home.aiModelRef')
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.home.aiModelRef', expect.anything())

    // modelOverridden===false: workspaceDefaultHint wird wieder gerendert
    // (v-if="!modelOverridden && !loadingModels", loadingModels=false nach flush).
    expect(w.html()).toContain('WORKSPACE_DEFAULT_HINT')
  })

  it('speichert einen expliziten Picker-Pick erst beim Start als vollständigen Run-Override', async () => {
    const w = await mountHome()
    await flushPromises()
    const picker = w.findComponent(aiPickerStub)
    await picker.trigger('click')
    expect(runOverrideMocks.set).not.toHaveBeenCalled()

    const file = new File(['briefing'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await w.find<HTMLTextAreaElement>('textarea.prompt').setValue('Analyse')
    await w.findAll('button').find(button => button.text() === 'Start')!.trigger('click')
    await flushPromises()

    expect(runOverrideMocks.set).toHaveBeenCalledWith({
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    })
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastModel', expect.anything())
    expect(localStorageMock.setItem).not.toHaveBeenCalledWith('agora.lastCustomModel', expect.anything())
  })

  it('Kanon-First-Init: selectedModel wird aus effectiveRef vorbelegt, wenn User nichts waehlt; ensureLoaded in onMounted aufgerufen, setGlobalSelection NICHT', async () => {
    resetEffMock()
    const w = await mountHome()
    await flushPromises()

    // ensureLoaded wurde in onMounted aufgerufen.
    expect(effMock.ensureLoadedImpl).toHaveBeenCalledTimes(1)

    // selectedModel wurde aus dem Kanon (effectiveRef) vorbelegt, nicht null.
    const picker = w.findComponent(aiPickerStub)
    expect(picker.props('modelValue')).toEqual(kanonAiRef)

    // Kanon-Schreibpfad bei reinem Init nicht beruehrt (nur Lese-Pfad).
    expect(effMock.setGlobalSelection).not.toHaveBeenCalled()
  })

  it('Nach explizitem Pick (modelOverridden=true) ueberschreibt Kanon-Vorbelegung selectedModel nicht mehr', async () => {
    // ensureLoaded bewusst verzoegert, damit der Pick vor der Kanon-Then-Resolution passiert.
    resetEffMock({ deferEnsureLoaded: true })
    const picked = {
      provider_connection_id: 'conn-openai-1',
      model_id: 'gpt-4o-mini',
      source: 'explicit',
    }

    const w = mount(Home, { global: { plugins: [makeI18n()], stubs } })
    // onMounted hat ensureLoaded (pending) + loadStatus angestossen; Pick VOR Resolution.
    const picker = w.findComponent(aiPickerStub)
    picker.vm.$emit('update:modelValue', picked)
    await flushPromises()

    // Jetzt erst Kanon-Ensure aufloesen -> .then prueft modelOverridden und überschreibt NICHT.
    expect(effMock.resolveEnsureLoaded).not.toBeNull()
    effMock.resolveEnsureLoaded!()
    await flushPromises()

    // selectedModel bleibt der explizite Pick, nicht der Kanon-Default.
    expect(picker.props('modelValue')).toEqual(picked)
    expect(picker.props('modelValue')).not.toEqual(kanonAiRef)

    // modelOverridden===true: workspaceDefaultHint wird NICHT gerendert.
    expect(w.html()).not.toContain('WORKSPACE_DEFAULT_HINT')

    // Picker-Pick ist transient — setGlobalSelection nicht beruehrt.
    expect(effMock.setGlobalSelection).not.toHaveBeenCalled()
  })
})

function installLocalStorageSafe() { vi.stubGlobal('localStorage', localStorageMock) }
