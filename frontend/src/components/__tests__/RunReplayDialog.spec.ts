import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'

const replayRunMock = vi.hoisted(() => vi.fn())

vi.mock('../../api/runs', () => ({
  replayRun: replayRunMock,
}))

import RunReplayDialog from '../RunReplayDialog.vue'

/**
 * Issue #763 (Ticket 6) — Replay-Dialog: identisch vs. Variante.
 * Gegen echte de.json gemountet, damit ein fehlender i18n-Key auffällt.
 */
function mountDialog(open = true) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return mount(RunReplayDialog, {
    props: { modelValue: open, runId: 'run-abc123' },
    global: { plugins: [i18n] },
  })
}

describe('RunReplayDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('startet mit Modus "identisch"', () => {
    const wrapper = mountDialog()
    const identicalRadio = wrapper.find('input[value="identical"]')
    expect((identicalRadio.element as HTMLInputElement).checked).toBe(true)
  })

  it('zeigt Varianten-Felder erst nach Umschalten', async () => {
    const wrapper = mountDialog()
    expect(wrapper.find('.variant-fields').exists()).toBe(false)

    await wrapper.find('input[value="variant"]').setValue(true)
    expect(wrapper.find('.variant-fields').exists()).toBe(true)
  })

  it('identisches Replay ruft replayRun ohne Overrides auf', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    const wrapper = mountDialog()

    await wrapper.find('button.btn--primary, [class*="primary"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(replayRunMock).toHaveBeenCalledWith('run-abc123', undefined)
  })

  it('emittet replayed mit der neuen run_id bei Erfolg', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    const wrapper = mountDialog()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))

    expect(wrapper.emitted('replayed')).toBeTruthy()
    expect(wrapper.emitted('replayed')?.[0]).toEqual(['run-new456'])
  })

  it('Varianten-Replay mit random_seed baut korrekte Overrides', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new789', status: 'pending' })
    const wrapper = mountDialog()

    await wrapper.find('input[value="variant"]').setValue(true)
    const seedInput = wrapper.find('input[type="number"]')
    await seedInput.setValue('12345')

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))

    expect(replayRunMock).toHaveBeenCalledWith('run-abc123', {
      overrides: { random_seed: 12345 },
    })
  })

  it('zeigt eine Fehlermeldung, wenn replayRun fehlschlägt', async () => {
    replayRunMock.mockRejectedValueOnce(new Error('Provider nicht verfügbar'))
    const wrapper = mountDialog()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Provider nicht verfügbar')
    expect(wrapper.emitted('replayed')).toBeFalsy()
  })
})
