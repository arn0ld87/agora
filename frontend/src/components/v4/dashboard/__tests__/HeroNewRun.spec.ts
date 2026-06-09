import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

vi.mock('../../../../api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn().mockResolvedValue([]),
}))

// Default: allow_small_sim=false → Slider-Floor 30, kein Warning-Pfad
vi.mock('../../../../api/status', () => ({
  getSystemStatus: vi.fn().mockResolvedValue({
    success: true,
    backend: { ok: true, version: '1.0.0', auth_mode: 'open', allow_small_sim: false },
    neo4j: { reachable: true },
    ollama: { reachable: false, models_available: [] },
    disk: { uploads: { path: '/tmp', total_bytes: 0, free_bytes: 0, used_pct: 0 } },
    timestamp: '2026-05-17T00:00:00Z',
  }),
}))

// Slice A2: ModelPicker stubben, damit die Hero-Tests ohne Pinia laufen.
vi.mock('../../forms/ModelPicker.vue', () => ({
  default: {
    name: 'ModelPicker',
    template: '<div class="model-picker-stub" data-testid="model-picker" />',
    props: ['modelValue', 'placeholder', 'disabled'],
    emits: ['update:modelValue'],
  },
}))

vi.mock('../../../../store/pendingUpload', () => ({
  setPendingUpload: vi.fn(),
}))

import { setPendingUpload } from '../../../../store/pendingUpload'
import HeroNewRun from '../HeroNewRun.vue'

describe('HeroNewRun', () => {
  beforeEach(() => {
    vi.mocked(setPendingUpload).mockReset()
  })

  it('rendert Drop-Zone, zwei Selects, deaktivierte CTA ohne Datei', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()
    expect(w.find('.hero-drop').exists()).toBe(true)
    expect(w.findAll('select')).toHaveLength(2)
    const btn = w.find('.hero-cta')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('CTA bleibt deaktiviert mit Datei aber ohne Requirement', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(w.find('.hero-cta').attributes('disabled')).toBeDefined()
  })

  it('aktiviert CTA und startet nach Datei + Requirement', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const pushSpy = vi.spyOn(router, 'push')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const file = new File(['x'], 'briefing.md', { type: 'text/markdown' })
    const input = w.find<HTMLInputElement>('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    const textarea = w.find<HTMLTextAreaElement>('textarea#hero-requirement')
    await textarea.setValue('Wie reagiert die DACH-Region?')
    await flushPromises()

    const btn = w.find('.hero-cta')
    expect(btn.attributes('disabled')).toBeUndefined()
    await btn.trigger('click')
    await flushPromises()

    expect(setPendingUpload).toHaveBeenCalledWith(
      [file],
      'Wie reagiert die DACH-Region?',
      null,
      30,
      10,
    )
    expect(pushSpy).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
  })

  it('num_agents Slider hat Default 30', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const slider = w.find<HTMLInputElement>('input#hero-num-agents')
    expect(slider.exists()).toBe(true)
    expect(Number(slider.element.value)).toBe(30)
  })

  it('num_rounds Slider hat Default 10', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const slider = w.find<HTMLInputElement>('input#hero-num-rounds')
    expect(slider.exists()).toBe(true)
    expect(Number(slider.element.value)).toBe(10)
  })

  it('Slider-Floor ist 30 (hart) wenn allow_small_sim=false', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const slider = w.find<HTMLInputElement>('input#hero-num-agents')
    expect(slider.attributes('min')).toBe('30')
    expect(w.find('.hero-small-sim-badge').exists()).toBe(false)
  })

  it('Slider-Floor ist 10 + SMALL_SIM-Badge wenn allow_small_sim=true', async () => {
    const { getSystemStatus } = await import('../../../../api/status')
    vi.mocked(getSystemStatus).mockResolvedValueOnce({
      success: true,
      backend: { ok: true, version: '1.0.0', auth_mode: 'open', allow_small_sim: true },
      neo4j: { reachable: true },
      ollama: { reachable: false, models_available: [] },
      disk: { uploads: { path: '/tmp', total_bytes: 0, free_bytes: 0, used_pct: 0 } },
      timestamp: '2026-05-17T00:00:00Z',
    } as unknown as Awaited<ReturnType<typeof getSystemStatus>>)

    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const slider = w.find<HTMLInputElement>('input#hero-num-agents')
    expect(slider.attributes('min')).toBe('10')
    expect(w.find('.hero-small-sim-badge').exists()).toBe(true)

    // Warning-Badge erscheint bei numAgents < 30 im Override-Mode
    await slider.setValue(25)
    await flushPromises()
    expect(w.find('.hero-warning').exists()).toBe(true)

    await slider.setValue(30)
    await flushPromises()
    expect(w.find('.hero-warning').exists()).toBe(false)
  })
})
