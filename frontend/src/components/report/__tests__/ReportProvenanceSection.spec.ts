/**
 * ReportProvenanceSection (Slice 8 — User-Bericht 2026-05-16).
 *
 * Rendert die model_attribution[]-Liste aus ReportV3 als ausklappbare
 * Tabelle. Versteckt sich automatisch, wenn keine Einträge vorliegen
 * (Backward-Compat zu alten Reports ohne Provenance-Daten).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportProvenanceSection from '../ReportProvenanceSection.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      report: {
        provenance: {
          title: 'Modell-Provenance',
          stage: 'Stage',
          provider: 'Provider',
          model: 'Modell',
          promptTokens: 'Prompt-Tokens',
          completionTokens: 'Completion-Tokens',
          latencyMs: 'Latenz',
          noMetricsHint: 'Keine Token-/Latenz-Metriken erfasst.',
        },
      },
    },
    en: {},
  },
})

const globalConfig = { plugins: [i18n] }

describe('ReportProvenanceSection (Slice 8)', () => {
  it('versteckt sich komplett bei leeren entries (Backward-Compat)', () => {
    const wrapper = mount(ReportProvenanceSection, {
      props: { entries: [] },
      global: globalConfig,
    })
    expect(wrapper.find('details').exists()).toBe(false)
  })

  it('rendert eine Zeile pro entry', () => {
    const entries = [
      { stage: 'ontology', provider: 'ollama', model_id: 'qwen2.5:32b', prompt_tokens: 1200, completion_tokens: 340, latency_ms: 2100 },
      { stage: 'report_section', provider: 'openai', model_id: 'gpt-4o' },
    ]
    const wrapper = mount(ReportProvenanceSection, {
      props: { entries },
      global: globalConfig,
    })
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    const text = wrapper.text()
    expect(text).toContain('ontology')
    expect(text).toContain('qwen2.5:32b')
    expect(text).toContain('gpt-4o')
    expect(text).toContain('Modell-Provenance')
  })

  it('zeigt em-dash bei fehlenden Token-/Latenz-Werten', () => {
    const entries = [
      { stage: 'report_section', provider: 'openai', model_id: 'gpt-4o' },
    ]
    const wrapper = mount(ReportProvenanceSection, {
      props: { entries },
      global: globalConfig,
    })
    const cells = wrapper.findAll('tbody tr:first-child td.num')
    expect(cells).toHaveLength(3)
    cells.forEach((cell) => expect(cell.text()).toBe('—'))
  })

  it('formatiert Latenz < 1000 ms als ms, sonst als s', () => {
    const entries = [
      { stage: 'a', provider: 'p', model_id: 'm1', latency_ms: 250 },
      { stage: 'b', provider: 'p', model_id: 'm2', latency_ms: 2500 },
    ]
    const wrapper = mount(ReportProvenanceSection, {
      props: { entries },
      global: globalConfig,
    })
    const text = wrapper.text()
    expect(text).toContain('250 ms')
    expect(text).toContain('2.50 s')
  })

  it('zeigt noMetricsHint, wenn keine entry Metriken hat', () => {
    const entries = [
      { stage: 'a', provider: 'p', model_id: 'm1' },
      { stage: 'b', provider: 'p', model_id: 'm2' },
    ]
    const wrapper = mount(ReportProvenanceSection, {
      props: { entries },
      global: globalConfig,
    })
    expect(wrapper.text()).toContain('Keine Token-/Latenz-Metriken erfasst.')
  })
})
