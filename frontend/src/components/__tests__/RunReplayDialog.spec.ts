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

  it('Varianten-Replay baut ai_model_ref inklusive Connection-ID', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new789', status: 'pending' })
    const wrapper = mountDialog()

    await wrapper.find('input[value="variant"]').setValue(true)
    const fields = wrapper.findAll('.variant-fields input')
    await fields[0].setValue('conn-gemini')
    await fields[1].setValue('gemini-2.5-pro')

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))

    expect(replayRunMock).toHaveBeenCalledWith('run-abc123', {
      overrides: {
        ai_model_ref: { provider_connection_id: 'conn-gemini', model_id: 'gemini-2.5-pro' },
      },
    })
  })

  it('bietet keine Felder an, die das Backend garantiert mit 400 ablehnt', async () => {
    // CodeRabbit-Fund: seed_document_id und random_seed werden serverseitig
    // mit 400 abgelehnt (kein Re-Prepare, kein Runtime-Seed-Konzept). Felder
    // dafuer im Dialog fuehren jeden Nutzer sicher in einen Fehler.
    const wrapper = mountDialog()
    await wrapper.find('input[value="variant"]').setValue(true)

    expect(wrapper.find('.variant-fields input[type="number"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Seed-Dokument-ID')
    expect(wrapper.text()).not.toContain('Zufalls-Seed')
    expect(wrapper.findAll('.variant-fields input')).toHaveLength(2)
  })

  it('sperrt den Submit bei halb ausgefuelltem Modell-Override', async () => {
    // CodeRabbit-Fund: buildOverrides verwarf ein Override mit nur einem der
    // beiden Felder still — das Replay lief dann unbemerkt auf dem Originalmodell.
    const wrapper = mountDialog()
    await wrapper.find('input[value="variant"]').setValue(true)
    await wrapper.findAll('.variant-fields input')[0].setValue('conn-gemini')

    expect(wrapper.text()).toContain('müssen beide gesetzt sein')

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()

    expect(replayRunMock).not.toHaveBeenCalled()
  })

  it('nutzt einen i18n-Key statt eines hartkodierten Fehlertexts', async () => {
    replayRunMock.mockRejectedValueOnce('kein Error-Objekt')
    const wrapper = mountDialog()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain(de.runs.dashboard.replay.unknown_error)
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
