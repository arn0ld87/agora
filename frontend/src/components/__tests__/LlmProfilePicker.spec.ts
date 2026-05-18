/**
 * LlmProfilePicker — Vitest-Spec (LPP-01).
 *
 * 1. renders fallback option — leerer Store → select hat option value="" mit fallbackLabel.
 * 2. renders profiles when loaded — 2 Profile → 3 options total.
 * 3. emits null when fallback chosen — option value="" → emit null (nicht "").
 * 4. emits profile id when profile chosen — option value="prof-123" → emit "prof-123".
 * 5. disabled prop disables select.
 * 6. shows loading state — store.loading=true → loading-Text sichtbar.
 * 7. shows error state — store.error="boom" → error-Banner sichtbar.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createI18n } from 'vue-i18n'
import { useLlmProfilesStore } from '../../store/llmProfiles'

// Mock fetchLlmProfiles so onMounted fetch() never hits the network.
vi.mock('../../api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn().mockResolvedValue([]),
  createLlmProfile: vi.fn(),
  updateLlmProfile: vi.fn(),
  deleteLlmProfile: vi.fn(),
  setDefaultLlmProfile: vi.fn(),
}))

import LlmProfilePicker from '../llm/LlmProfilePicker.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      llmProfilePicker: {
        label: 'LLM-Profil (optional)',
        serverDefault: 'Server-Standard (aktives Profil)',
        loading: 'Profile laden…',
        error: 'Profile konnten nicht geladen werden.',
        defaultSuffix: 'default',
      },
    },
    en: {},
  },
})

function makePinia(overrides: {
  profiles?: Array<{ id: string; name: string; model_name: string; is_default: boolean; provider: string; base_url: string; api_key: null | string; created_at: string; updated_at: string }>
  loading?: boolean
  error?: string | null
} = {}) {
  return createTestingPinia({
    createSpy: vi.fn,
    initialState: {
      llmProfiles: {
        profiles: overrides.profiles ?? [],
        loading: overrides.loading ?? false,
        saving: false,
        error: overrides.error ?? null,
      },
    },
  })
}

const PROFILE_A = {
  id: 'prof-123',
  name: 'GPT-4o',
  model_name: 'gpt-4o',
  is_default: false,
  provider: 'openai' as const,
  base_url: 'https://api.openai.com/v1',
  api_key: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const PROFILE_B = {
  id: 'prof-456',
  name: 'Gemini Flash',
  model_name: 'gemini-2.0-flash',
  is_default: true,
  provider: 'gemini' as const,
  base_url: 'https://generativelanguage.googleapis.com/v1beta',
  api_key: null,
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LlmProfilePicker', () => {
  it('1. renders fallback option — leerer Store → select hat option value="" mit fallbackLabel', async () => {
    const pinia = makePinia()
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null },
      global: { plugins: [i18n, pinia] },
    })
    await flushPromises()

    const options = wrapper.findAll('option')
    expect(options).toHaveLength(1)
    expect(options[0].attributes('value')).toBe('')
    expect(options[0].text()).toBe('Server-Standard (aktives Profil)')

    // No emit on initial render.
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()

    wrapper.unmount()
  })

  it('2. renders profiles when loaded — 2 Profile → 3 options total', async () => {
    const pinia = makePinia({ profiles: [PROFILE_A, PROFILE_B] })
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null },
      global: { plugins: [i18n, pinia] },
    })
    await flushPromises()

    const options = wrapper.findAll('option')
    expect(options).toHaveLength(3)
    expect(options[0].attributes('value')).toBe('')
    expect(options[1].attributes('value')).toBe('prof-123')
    expect(options[2].attributes('value')).toBe('prof-456')

    wrapper.unmount()
  })

  it('3. emits null when fallback chosen — option value="" → emit null', async () => {
    const pinia = makePinia({ profiles: [PROFILE_A] })
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: 'prof-123' },
      global: { plugins: [i18n, pinia] },
    })
    await flushPromises()

    const select = wrapper.find('select')
    // Simulate selecting the empty/fallback option.
    await select.setValue('')
    await select.trigger('change')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    // Must emit null, not the empty string.
    expect(emitted![emitted!.length - 1][0]).toBeNull()

    wrapper.unmount()
  })

  it('4. emits profile id when profile chosen', async () => {
    const pinia = makePinia({ profiles: [PROFILE_A] })
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null },
      global: { plugins: [i18n, pinia] },
    })
    await flushPromises()

    const select = wrapper.find('select')
    await select.setValue('prof-123')
    await select.trigger('change')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1][0]).toBe('prof-123')

    wrapper.unmount()
  })

  it('5. disabled prop disables select', async () => {
    const pinia = makePinia()
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null, disabled: true },
      global: { plugins: [i18n, pinia] },
    })
    await flushPromises()

    const select = wrapper.find('select')
    expect(select.attributes('disabled')).toBeDefined()

    wrapper.unmount()
  })

  it('6. shows loading state — store.loading=true → loading-Text sichtbar', async () => {
    const pinia = makePinia({ loading: true })
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null },
      global: { plugins: [i18n, pinia] },
    })
    // Manually patch loading after pinia init so computed re-runs.
    const store = useLlmProfilesStore()
    store.$patch({ loading: true })
    await flushPromises()

    expect(wrapper.text()).toContain('Profile laden…')

    wrapper.unmount()
  })

  it('7. shows error state — store.error set → error-Banner sichtbar', async () => {
    const pinia = makePinia({ error: 'boom' })
    const wrapper = mount(LlmProfilePicker, {
      props: { modelValue: null },
      global: { plugins: [i18n, pinia] },
    })
    const store = useLlmProfilesStore()
    store.$patch({ error: 'boom' })
    await flushPromises()

    const alert = wrapper.find('[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('Profile konnten nicht geladen werden.')

    wrapper.unmount()
  })
})
