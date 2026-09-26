import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import { ApiError } from '../../api/envelope'
import type { RunManifest } from '../../contracts/runManifestContract'

const replayRunMock = vi.hoisted(() => vi.fn())
const getRunManifestMock = vi.hoisted(() => vi.fn())

vi.mock('../../api/runs', () => ({
  replayRun: replayRunMock,
  getRunManifest: getRunManifestMock,
}))

import RunReplayDialog from '../RunReplayDialog.vue'

const aiPickerStub = {
  name: 'AiModelPicker',
  props: ['modelValue', 'placeholder', 'mode'],
  emits: ['update:modelValue'],
  template:
    '<div data-testid="ai-model-picker-stub" '
    + '@click="$emit(\'update:modelValue\', { provider_connection_id: \'conn-gemini\', model_id: \'gemini-2.5-pro\', source: \'explicit\' })">picker</div>',
}

function baseManifest(overrides: Partial<RunManifest> = {}): RunManifest {
  return {
    schema_version: 1,
    run_id: 'run-abc123',
    replayed_from_run_id: null,
    captured_at: '2026-09-01T00:00:00Z',
    inputs: {
      seed_document_hash: null,
      seed_document_filename: null,
      simulation_config_hash: 'hash',
      graph_id: 'graph-1',
      graph_version: null,
      embedding_version: null,
    },
    versions: { agora_version: '0.9.5', schema_version: '1' },
    routing: { stages: {} },
    prompts: { entries: {} },
    seeds: { random_seed: null, simulation_id_seed: null },
    runtime: null,
    simulation: {
      platform: 'parallel',
      max_rounds: 12,
      enable_graph_memory_update: true,
      memory_update_graph_id: 'graph-1',
    },
    deviations: [],
    status: 'final',
    ...overrides,
  }
}

/**
 * Issue #763 (Ticket 6) + Issue #1684 — Replay-Dialog: Picker statt Freitext,
 * 1:1-Startparameter-Anzeige, Deviations, 409-Fehleranzeige.
 * Gegen echte de.json gemountet, damit ein fehlender i18n-Key auffällt.
 */
function mountDialog(open = true) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } })
  return mount(RunReplayDialog, {
    props: { modelValue: open, runId: 'run-abc123' },
    global: {
      plugins: [i18n],
      stubs: { AiModelPicker: aiPickerStub },
    },
  })
}

describe('RunReplayDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRunManifestMock.mockResolvedValue({ success: true, data: baseManifest() })
  })

  it('startet mit Modus "identisch"', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const identicalRadio = wrapper.find('input[value="identical"]')
    expect((identicalRadio.element as HTMLInputElement).checked).toBe(true)
  })

  it('zeigt Varianten-Felder erst nach Umschalten, mit Picker statt Freitext', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(wrapper.find('.variant-fields').exists()).toBe(false)

    await wrapper.find('input[value="variant"]').setValue(true)
    expect(wrapper.find('.variant-fields').exists()).toBe(true)
    expect(wrapper.findComponent(aiPickerStub).exists()).toBe(true)
    expect(wrapper.find('.variant-fields input[type="text"]').exists()).toBe(false)
  })

  it('zeigt die Original-Startparameter aus dem Manifest an', async () => {
    const wrapper = mountDialog()
    await flushPromises()

    expect(getRunManifestMock).toHaveBeenCalledWith('run-abc123')
    const params = wrapper.get('[data-testid="original-params"]')
    expect(params.text()).toContain('parallel')
    expect(params.text()).toContain('12')
  })

  it('zeigt eine Warnung, wenn das Original-Manifest keine Simulationsparameter hat', async () => {
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({ simulation: null }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    const warning = wrapper.get('[data-testid="manifest-unavailable"]')
    expect(warning.attributes('role')).toBe('alert')
    expect(wrapper.find('[data-testid="original-params"]').exists()).toBe(false)

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    expect(submitBtn?.attributes('disabled')).toBeDefined()
  })

  it('identisches Replay ruft replayRun ohne Overrides auf', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    getRunManifestMock.mockResolvedValueOnce({ success: true, data: baseManifest() })
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({ run_id: 'run-new456', deviations: [] }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.find('button.btn--primary, [class*="primary"]').trigger('click')
    await flushPromises()

    expect(replayRunMock).toHaveBeenCalledWith('run-abc123', undefined)
  })

  it('emittet replayed mit der neuen run_id bei Erfolg', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    getRunManifestMock.mockResolvedValueOnce({ success: true, data: baseManifest() })
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({ run_id: 'run-new456', deviations: [] }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('replayed')).toBeTruthy()
    expect(wrapper.emitted('replayed')?.[0]).toEqual(['run-new456'])
  })

  it('zeigt Abweichungen nach erfolgreichem Replay', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    getRunManifestMock.mockResolvedValueOnce({ success: true, data: baseManifest() })
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({
        run_id: 'run-new456',
        deviations: [
          { field: 'routing.stages.persona_generation.model', original: 'gpt-4o', replay: 'gemini-2.5-pro' },
        ],
      }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    const deviationsBlock = wrapper.get('[data-testid="deviations-list"]')
    expect(deviationsBlock.text()).toContain('routing.stages.persona_generation.model')
    expect(deviationsBlock.text()).toContain('gpt-4o')
    expect(deviationsBlock.text()).toContain('gemini-2.5-pro')
  })

  it('zeigt "keine Abweichungen", wenn identisch repliziert wurde', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new456', status: 'pending' })
    getRunManifestMock.mockResolvedValueOnce({ success: true, data: baseManifest() })
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({ run_id: 'run-new456', deviations: [] }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="deviations-list"]').text()).toContain(
      de.runs.dashboard.replay.deviations_none,
    )
  })

  it('Varianten-Replay baut ai_model_ref über den Picker', async () => {
    replayRunMock.mockResolvedValueOnce({ run_id: 'run-new789', status: 'pending' })
    getRunManifestMock.mockResolvedValueOnce({ success: true, data: baseManifest() })
    getRunManifestMock.mockResolvedValueOnce({
      success: true,
      data: baseManifest({ run_id: 'run-new789', deviations: [] }),
    })
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.find('input[value="variant"]').setValue(true)
    await wrapper.findComponent(aiPickerStub).trigger('click')

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(replayRunMock).toHaveBeenCalledWith('run-abc123', {
      overrides: {
        ai_model_ref: { provider_connection_id: 'conn-gemini', model_id: 'gemini-2.5-pro' },
      },
    })
  })

  it('sperrt den Submit im Variant-Modus ohne Modellauswahl', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.find('input[value="variant"]').setValue(true)

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    expect(submitBtn?.attributes('disabled')).toBeDefined()

    await submitBtn?.trigger('click')
    await flushPromises()
    expect(replayRunMock).not.toHaveBeenCalled()
  })

  it('nutzt einen i18n-Key statt eines hartkodierten Fehlertexts', async () => {
    replayRunMock.mockRejectedValueOnce('kein Error-Objekt')
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(de.runs.dashboard.replay.unknown_error)
  })

  it('zeigt eine Fehlermeldung, wenn replayRun fehlschlägt', async () => {
    replayRunMock.mockRejectedValueOnce(new Error('Provider nicht verfügbar'))
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Provider nicht verfügbar')
    expect(wrapper.emitted('replayed')).toBeFalsy()
  })

  it('zeigt eine verständliche Meldung für 409 manifest_missing_simulation_params', async () => {
    replayRunMock.mockRejectedValueOnce(
      new ApiError({
        code: 'manifest_missing_simulation_params',
        status: 409,
        message: 'Run run-abc123 has a manifest without captured simulation parameters …',
      }),
    )
    const wrapper = mountDialog()
    await flushPromises()

    const submitBtn = wrapper.findAll('button').find((b) => b.text().includes('Replay starten'))
    await submitBtn?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(de.runs.dashboard.replay.missing_simulation_params_error)
    expect(wrapper.emitted('replayed')).toBeFalsy()
  })
})
