/**
 * ModelPicker.vue — Unit-Tests
 *
 * Mockt useAvailableModels, prüft:
 *   - optgroup-Render pro Provider (alphabetisch)
 *   - v-model-Emit (update:modelValue)
 *   - Loading-Zustand
 *   - Fehler-Zustand
 *   - Leer-Zustand (keine Modelle)
 *   - disabled-Prop
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'

// ---------------------------------------------------------------------------
// Mock useAvailableModels BEFORE importing ModelPicker
// ---------------------------------------------------------------------------
const mockModels = ref<import('@/composables/useAvailableModels').PickerModel[]>([])
const mockLoading = ref(false)
const mockError = ref<string | null>(null)
const mockRefresh = vi.fn()

vi.mock('@/composables/useAvailableModels', () => ({
  useAvailableModels: () => ({
    models: mockModels,
    loading: mockLoading,
    error: mockError,
    refresh: mockRefresh,
  }),
}))

import ModelPicker from '../ModelPicker.vue'

// ---------------------------------------------------------------------------
// i18n-Instanz für Tests
// ---------------------------------------------------------------------------
function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    messages: {
      de: {
        modelPicker: {
          loading: 'Lade Modelle…',
          error: 'Fehler beim Laden der Modelle',
          placeholder: 'Modell wählen…',
          noModels: 'Keine Modelle verfügbar',
        },
      },
    },
  })
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const ollamaModels: import('@/composables/useAvailableModels').PickerModel[] = [
  { provider_id: 'ollama', provider_label: 'Ollama', model_id: 'llama3.1:8b', model_label: 'LLaMA 3.1 8B', source: 'live' },
  { provider_id: 'ollama', provider_label: 'Ollama', model_id: 'zephyr:7b', model_label: 'Zephyr 7B', source: 'live' },
]

const googleModels: import('@/composables/useAvailableModels').PickerModel[] = [
  { provider_id: 'google', provider_label: 'Google Gemini', model_id: 'gemini-1.5-flash', model_label: 'Gemini 1.5 Flash', source: 'live' },
  { provider_id: 'google', provider_label: 'Google Gemini', model_id: 'gemini-2.5-pro', model_label: 'Gemini 2.5 Pro', source: 'live' },
]

// Kombiniert und vorsortiert (wie useAvailableModels es liefert)
const allModels: import('@/composables/useAvailableModels').PickerModel[] = [
  // Google Gemini (G) vor Ollama (O)
  ...googleModels,
  ...ollamaModels,
]

// ---------------------------------------------------------------------------
describe('ModelPicker', () => {
  let i18n: ReturnType<typeof makeI18n>

  beforeEach(() => {
    i18n = makeI18n()
    mockModels.value = []
    mockLoading.value = false
    mockError.value = null
    vi.clearAllMocks()
  })

  // ---------------------------------------------------------------------------
  function mountPicker(props: Record<string, unknown> = {}) {
    return mount(ModelPicker, {
      props: {
        modelValue: null,
        ...props,
      },
      global: {
        plugins: [i18n],
      },
    })
  }

  // ---------------------------------------------------------------------------
  it('zeigt Loading-Spinner während fetch', () => {
    mockLoading.value = true
    const w = mountPicker()
    expect(w.find('.model-picker__loading').exists()).toBe(true)
    expect(w.find('select').exists()).toBe(false)
  })

  it('zeigt Fehler-Nachricht bei error', () => {
    mockError.value = 'Network error'
    const w = mountPicker()
    const errEl = w.find('.model-picker__error')
    expect(errEl.exists()).toBe(true)
    expect(errEl.text()).toContain('Network error')
  })

  it('zeigt Empty-Zustand wenn keine Modelle', () => {
    mockModels.value = []
    const w = mountPicker()
    expect(w.find('.model-picker__empty').exists()).toBe(true)
    expect(w.find('select').exists()).toBe(false)
  })

  // ---------------------------------------------------------------------------
  it('rendert <optgroup> pro Provider in korrekter Reihenfolge', () => {
    mockModels.value = allModels
    const w = mountPicker()

    const groups = w.findAll('optgroup')
    expect(groups).toHaveLength(2)
    // Google Gemini kommt vor Ollama (alphabetisch)
    expect(groups[0].attributes('label')).toBe('Google Gemini')
    expect(groups[1].attributes('label')).toBe('Ollama')
  })

  it('rendert korrekte Optionen pro Provider', () => {
    mockModels.value = allModels
    const w = mountPicker()

    const groups = w.findAll('optgroup')
    const googleOptions = groups[0].findAll('option')
    expect(googleOptions).toHaveLength(2)
    expect(googleOptions[0].text()).toBe('Gemini 1.5 Flash')
    expect(googleOptions[1].text()).toBe('Gemini 2.5 Pro')

    const ollamaOptions = groups[1].findAll('option')
    expect(ollamaOptions).toHaveLength(2)
    expect(ollamaOptions[0].text()).toBe('LLaMA 3.1 8B')
    expect(ollamaOptions[1].text()).toBe('Zephyr 7B')
  })

  it('rendert Placeholder als erste leere Option', () => {
    mockModels.value = allModels
    const w = mountPicker()
    const firstOption = w.find('option')
    expect(firstOption.attributes('value')).toBe('')
    expect(firstOption.text()).toBe('Modell wählen…')
  })

  it('rendert benutzerdefinierten Placeholder', () => {
    mockModels.value = allModels
    const w = mountPicker({ placeholder: 'Bitte wählen' })
    const firstOption = w.find('option')
    expect(firstOption.text()).toBe('Bitte wählen')
  })

  // ---------------------------------------------------------------------------
  it('emittiert update:modelValue mit korrektem {provider_id, model_id} beim Wechsel', async () => {
    mockModels.value = allModels
    const w = mountPicker()

    const select = w.find('select')
    await select.setValue('google::gemini-2.5-pro')

    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual({ provider_id: 'google', model_id: 'gemini-2.5-pro' })
  })

  it('emittiert null wenn leere Option gewählt', async () => {
    mockModels.value = allModels
    const w = mountPicker({ modelValue: { provider_id: 'google', model_id: 'gemini-2.5-pro' } })

    const select = w.find('select')
    await select.setValue('')

    const emitted = w.emitted('update:modelValue')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBeNull()
  })

  // ---------------------------------------------------------------------------
  it('reflektiert modelValue korrekt als selected-Option', () => {
    mockModels.value = allModels
    const w = mountPicker({ modelValue: { provider_id: 'ollama', model_id: 'zephyr:7b' } })

    const select = w.find<HTMLSelectElement>('select')
    expect(select.element.value).toBe('ollama::zephyr:7b')
  })

  // ---------------------------------------------------------------------------
  it('deaktiviert <select> wenn disabled=true', () => {
    mockModels.value = allModels
    const w = mountPicker({ disabled: true })

    const select = w.find('select')
    expect(select.element.disabled).toBe(true)
  })

  it('<select> ist aktiv wenn disabled=false (default)', () => {
    mockModels.value = allModels
    const w = mountPicker()

    const select = w.find('select')
    expect(select.element.disabled).toBe(false)
  })

  // ---------------------------------------------------------------------------
  it('zeigt Fehler-State nicht wenn error null und loading false', () => {
    mockModels.value = allModels
    const w = mountPicker()

    expect(w.find('.model-picker__error').exists()).toBe(false)
    expect(w.find('.model-picker__loading').exists()).toBe(false)
  })
})
