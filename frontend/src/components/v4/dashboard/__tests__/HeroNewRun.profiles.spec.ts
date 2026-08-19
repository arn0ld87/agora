import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { makeI18n, makeRouter } from './dashTestHelpers'

// Slice 5.4: AiModelPicker stubben (statt ModelPicker, der in 5.4 ersetzt wurde).
vi.mock('../../forms/AiModelPicker.vue', () => ({
  default: {
    name: 'AiModelPicker',
    template: '<div class="ai-model-picker-stub" data-testid="ai-model-picker" />',
    props: ['modelValue', 'placeholder', 'mode', 'allowWorkspaceDefault', 'capabilityFilter'],
    emits: ['update:modelValue'],
  },
}))

// Slice "small-sim-floor-frontend-sync": HeroNewRun fragt beim Mount /api/status
// ab. In den Profile-Tests interessiert uns nur das Profil-Verhalten — minimaler
vi.mock('../../../../api/status', () => ({
  getSystemStatus: vi.fn().mockResolvedValue({
    success: true,
    backend: { ok: true, version: '1.0.0', auth_mode: 'open' },
    neo4j: { reachable: true },
    ollama: { reachable: false, models_available: [] },
    disk: { uploads: { path: '/tmp', total_bytes: 0, free_bytes: 0, used_pct: 0 } },
    timestamp: '2026-05-17T00:00:00Z',
  }),
}))

// LLM-Profile-API: zwei Profile
// Service-Readiness (Parität zu Home.vue, #915): Mock liefert neo4j_reachable=true
// und default_provider='openai' → servicesReady=true → canSubmit nicht blockiert.
vi.mock('../../../../api/simulation', () => ({
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: {
      default_provider: 'openai',
      ollama_reachable: true,
      neo4j_reachable: true,
      default_language: 'de',
    },
  }),
}))

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

// Phase-1 Kanon-Composable stubben: HeroNewRun initialisiert selectedModel
// onMounted aus effectiveRef. In den Profile-Tests interessiert nur das
// Profil-Verhalten — Kanon-Stub mit null/einem Stativ-Route, ensureLoaded
// resolvt, setGlobalSelection ist hier nicht aktiv (Profile gewinnt).
vi.mock('@/composables/useEffectiveModelSelection', () => {
  const stubRoute = {
    stage: null,
    provider_id: 'openai',
    model: 'gpt-4o',
    temperature: null,
    max_tokens: null,
    reasoning_effort: 'none',
    provider_options: {},
  }
  return {
    useEffectiveModelSelection: () => ({
      effectiveRef: { value: null },
      effectiveRoute: { value: stubRoute },
      loading: { value: false },
      error: { value: null },
      ensureLoaded: vi.fn().mockResolvedValue(undefined),
      setGlobalSelection: vi.fn().mockResolvedValue(undefined),
    }),
  }
})

import { setPendingUpload } from '../../../../store/pendingUpload'
import HeroNewRun from '../HeroNewRun.vue'

// localStorage-Mock (Bun-Testrunner hat kein jsdom built-in) — HeroNewRun liest
// `agora.hero.profileId` beim Mount aus window.localStorage.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => { delete store[k] }) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })
Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true })

describe('HeroNewRun — LLM-Profile (P5.5)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(setPendingUpload).mockReset()
    window.localStorage.clear()
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

  it('verwirft eine persistierte Profil-ID, die das Backend nicht mehr kennt', async () => {
    // Regression: `agora.hero.profileId` überlebt das Löschen des Profils. Die
    // tote ID darf weder als Auswahl stehen bleiben noch als `profile_id` an
    // den Sim-Start gehen — sonst bricht der Run mit "LLM-Profil nicht gefunden".
    window.localStorage.setItem('agora.hero.profileId', 'geloeschtes-profil')

    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const select = w.find<HTMLSelectElement>('select#hero-profile')
    expect(select.element.value).toBe('')
    expect(window.localStorage.getItem('agora.hero.profileId')).toBeNull()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    expect(setPendingUpload).toHaveBeenCalledWith(
      [file],
      'Wie reagiert die DACH-Region?',
      null,
      expect.anything(),
      expect.anything(),
    )
  })

  it('verwirft eine persistierte Profil-ID auch, wenn der Profilabruf scheitert', async () => {
    // Ohne Liste laesst sich die ID nicht verifizieren. Sie trotzdem zu senden
    // waere geraten — der Sim-Start braeche dann mit "LLM-Profil nicht gefunden".
    const { fetchLlmProfiles } = await import('@/api/llmProfiles')
    vi.mocked(fetchLlmProfiles).mockRejectedValueOnce(new Error('Netzwerk weg'))
    window.localStorage.setItem('agora.hero.profileId', 'abc')

    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    expect(window.localStorage.getItem('agora.hero.profileId')).toBeNull()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await w.find<HTMLTextAreaElement>('textarea#hero-requirement').setValue('Frage?')
    await flushPromises()

    await w.find('.hero-cta').trigger('click')
    await flushPromises()

    expect(setPendingUpload).toHaveBeenCalledWith(
      [file],
      'Frage?',
      null,
      expect.anything(),
      expect.anything(),
    )
  })

  it('behält eine persistierte Profil-ID, die das Backend weiterhin kennt', async () => {
    window.localStorage.setItem('agora.hero.profileId', 'abc')

    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    expect(w.find<HTMLSelectElement>('select#hero-profile').element.value).toBe('abc')
    expect(window.localStorage.getItem('agora.hero.profileId')).toBe('abc')
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
    // Issue #1234: Rundenzahl und Budget reisen in der Query, nicht im Store.
    expect(pushSpy).toHaveBeenCalledWith({
      name: 'Process',
      params: { projectId: 'new' },
      query: { maxRounds: '10' },
    })
  })
})
