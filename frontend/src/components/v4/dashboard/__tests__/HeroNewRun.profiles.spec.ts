import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

// Simulation-API: stabile Presets, kein Ollama-Fehler
vi.mock('../../../../api/simulation', () => ({
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: {
      ollama: [],
      presets: [{ name: 'preset-a', label: 'Preset A' }],
      current_default: 'preset-a',
      default_provider: 'ollama',
      ollama_reachable: false,
      ollama_error: null,
      neo4j_reachable: true,
      neo4j_error: null,
    },
  }),
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

  it('rendert LLM-Profile aus API im Dropdown', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const select = w.find<HTMLSelectElement>('select#hero-model')
    expect(select.exists()).toBe(true)

    const optionValues = Array.from(select.element.options).map(o => o.value)
    expect(optionValues).toContain('profile:abc')
    expect(optionValues).toContain('profile:xyz')
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
    const select = w.find<HTMLSelectElement>('select#hero-model')
    await select.setValue('profile:abc')
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
