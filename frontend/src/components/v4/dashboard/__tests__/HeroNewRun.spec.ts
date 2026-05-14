import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

vi.mock('../../../../api/simulation', () => ({
  getAvailableModels: vi.fn().mockResolvedValue({
    success: true,
    data: {
      ollama: [{ name: 'qwen2.5:32b', label: 'Qwen 2.5 32B' }],
      presets: [{ name: 'preset-a', label: 'Preset A' }],
      current_default: 'qwen2.5:32b',
      default_provider: 'ollama',
      ollama_reachable: true,
      ollama_error: null,
      neo4j_reachable: true,
      neo4j_error: null,
    },
  }),
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
    )
    expect(pushSpy).toHaveBeenCalledWith({ name: 'Process', params: { projectId: 'new' } })
  })
})
