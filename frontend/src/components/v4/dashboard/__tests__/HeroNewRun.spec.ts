import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

vi.mock('../../../../api/llmProfiles', () => ({
  fetchLlmProfiles: vi.fn().mockResolvedValue([]),
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

  it('Warning-Badge erscheint bei num_agents < 30, verschwindet bei 30', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(HeroNewRun, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()

    const slider = w.find<HTMLInputElement>('input#hero-num-agents')

    // Slider auf 25 → Badge sichtbar
    await slider.setValue(25)
    await flushPromises()
    expect(w.find('.hero-warning').exists()).toBe(true)

    // Slider auf 30 → Badge weg
    await slider.setValue(30)
    await flushPromises()
    expect(w.find('.hero-warning').exists()).toBe(false)
  })
})
