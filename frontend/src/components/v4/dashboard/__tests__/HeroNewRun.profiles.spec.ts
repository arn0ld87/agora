import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

// Slice A2: ModelPicker stubben, damit die Hero-Tests ohne Pinia laufen.
vi.mock('../../forms/ModelPicker.vue', () => ({
  default: {
    name: 'ModelPicker',
    template: '<div class="model-picker-stub" data-testid="model-picker" />',
    props: ['modelValue', 'placeholder', 'disabled'],
    emits: ['update:modelValue'],
  },
}))

// LLM-Profile-API: zwei Profile
vi.mock('../../../../api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn().mockResolvedValue([
    {
      id: 'abc',
      name: 'Mein GPT-4o',
      provider: 'openai',
      base_url: 'https://api.openai.com/v1',
      model_name: 'gpt-4o',
      api_key: 'sk-test',
      is_default: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'xyz',
      name: 'Lokales Llama',
      provider: 'ollama',
      base_url: 'http://localhost:11434',
      model_name: 'llama3.3',
      api_key: '',
      is_default: false,
      created_at: '2026-01-02T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    },
  ]),
}))

vi.mock('../../../../store/pendingUpload', () => ({
  setPendingUpload: vi.fn(),
}))

import { setPendingUpload } from '../../../../store/pendingUpload'
import HeroNewRun from '../HeroNewRun.vue'

describe('HeroNewRun — LLM-Profile (P5.5)', () => {
  beforeEach(() => {
    vi.mocked(setPendingUpload).mockReset()
  })

  it('rendert LLM-Profile aus API im Profile-Dropdown', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const select = w.find<HTMLSelectElement>('select#hero-profile')
    expect(select.exists()).toBe(true)

    const optionValues = Array.from(select.element.options).map(o => o.value)
    // Slice A2: Profile-IDs ohne `profile:`-Prefix; leerer Wert deaktiviert das Profile.
    expect(optionValues).toContain('')
    expect(optionValues).toContain('abc')
    expect(optionValues).toContain('xyz')
  })

  it('übergibt llmProfileId an setPendingUpload bei Profile-Auswahl', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const pushSpy = vi.spyOn(router, 'push')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    // Datei setzen
    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    // Fragestellung setzen
    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    // Profil 'abc' auswählen
    const select = w.find<HTMLSelectElement>('select#hero-profile')
    await select.setValue('abc')
    await flushPromises()

    // Starten
    const btn = w.find('.hero-cta')
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    await flushPromises()

    expect(setPendingUpload).toHaveBeenCalledWith(
      [file],
      'Wie reagiert die DACH-Region?',
      'abc',
      30,
      10,
    )
    expect(pushSpy).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
  })
})
