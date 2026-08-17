/**
 * ReportEvidencePanel — Hypothesen-Accordion Tests (Slice 3, Issue #495)
 *
 * Prueft:
 * - 5 sichtbare Hypothesen werden normal gerendert.
 * - hypotheses_appendix mit 3 Eintraegen: Accordion ist initial geschlossen.
 * - Counter im Summary zeigt die korrekte Anzahl der Appendix-Eintraege.
 * - Accordion-Items enthalten die erwarteten IDs.
 * - Kein Accordion bei leerer hypotheses_appendix.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportEvidencePanel from '../ReportEvidencePanel.vue'
import type { ReportSection } from '../../../contracts/reportContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      'step4.quote.openSource': 'Quelle öffnen',
    },
  },
})

const globalConfig = {
  plugins: [i18n],
}

function makeHypothesis(index: number) {
  return {
    hypothesis_id: `hypothesis_${String(index).padStart(2, '0')}`,
    hypothesis_text: `Hypothese ${index}`,
    rationale: `Begründung ${index}`,
    suggested_evidence: [],
  }
}

const mockSection: ReportSection = {
  section_index: 1,
  section_title: 'Testsection',
  section_summary: 'Zusammenfassung der Testsection',
  claims: [],
  hypotheses: [1, 2, 3, 4, 5].map(makeHypothesis),
  hypotheses_appendix: [6, 7, 8].map(makeHypothesis),
  data_gaps: [],
  structured_metadata: {},
  generation_failed: false,
  unbound_evidence_refs: [],
  unverified_statements: [],
}

describe('ReportEvidencePanel — Hypothesen-Accordion', () => {
  it('rendert 5 sichtbare Hypothesen-Cards wenn Tab aktiv', async () => {
    const wrapper = mount(ReportEvidencePanel, {
      props: {
        sections: [mockSection],
        selectedSection: 1,
      },
      global: globalConfig,
    })

    // Hypothesen-Tab klicken
    const hypothesesTab = wrapper.find('[data-testid="hypotheses-tab"]')
    expect(hypothesesTab.exists()).toBe(true)
    await hypothesesTab.trigger('click')

    const cards = wrapper.findAll('.hypothesis-card')
    expect(cards).toHaveLength(5)
  })

  it('Accordion ist initial geschlossen (kein open-Attribut)', async () => {
    const wrapper = mount(ReportEvidencePanel, {
      props: {
        sections: [mockSection],
        selectedSection: 1,
      },
      global: globalConfig,
    })

    const hypothesesTab = wrapper.find('[data-testid="hypotheses-tab"]')
    await hypothesesTab.trigger('click')

    const accordion = wrapper.find('[data-testid="hypothesis-appendix"]')
    expect(accordion.exists()).toBe(true)
    expect(accordion.attributes('open')).toBeUndefined()
  })

  it('Summary zeigt korrekte Anzahl der Appendix-Eintraege', async () => {
    const wrapper = mount(ReportEvidencePanel, {
      props: {
        sections: [mockSection],
        selectedSection: 1,
      },
      global: globalConfig,
    })

    const hypothesesTab = wrapper.find('[data-testid="hypotheses-tab"]')
    await hypothesesTab.trigger('click')

    const summary = wrapper.find('.hypothesis-appendix-summary')
    expect(summary.text()).toContain('(3)')
  })

  it('Accordion-Items enthalten die korrekten IDs', async () => {
    const wrapper = mount(ReportEvidencePanel, {
      props: {
        sections: [mockSection],
        selectedSection: 1,
      },
      global: globalConfig,
    })

    const hypothesesTab = wrapper.find('[data-testid="hypotheses-tab"]')
    await hypothesesTab.trigger('click')

    const items = wrapper.findAll('.hypothesis-appendix-item')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('hypothesis_06')
    expect(items[1].text()).toContain('hypothesis_07')
    expect(items[2].text()).toContain('hypothesis_08')
  })

  it('kein Accordion wenn hypotheses_appendix leer ist', async () => {
    const sectionNoAppendix: ReportSection = {
      ...mockSection,
      hypotheses_appendix: [],
    }

    const wrapper = mount(ReportEvidencePanel, {
      props: {
        sections: [sectionNoAppendix],
        selectedSection: 1,
      },
      global: globalConfig,
    })

    const hypothesesTab = wrapper.find('[data-testid="hypotheses-tab"]')
    await hypothesesTab.trigger('click')

    const accordion = wrapper.find('[data-testid="hypothesis-appendix"]')
    expect(accordion.exists()).toBe(false)
  })
})
