/**
 * ReportReader — PR 6 (Premium-Redesign, "Bericht lesen").
 *
 * Prueft: Dreispalten-Struktur rendert (Outline/Body/Rail), ein Outline-Klick
 * schaltet den aktiven Abschnitt um, das Overlay "Neu generieren" oeffnet und
 * schliesst sich und reicht Modell/Modus ueber `update:report-route` /
 * `update:report-mode` / `regenerate` nach aussen weiter.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportReader from '../ReportReader.vue'
import ReportEvidenceRail from '../ReportEvidenceRail.vue'
import { ReportReaderTestId } from '../../../contracts/testIds'
import type { ReportOutline, ReportSection } from '../../../contracts/reportContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      step4: {
        next: 'Weiter',
        quote: { openSource: 'Quelle öffnen' },
        view: { printPdf: 'Als PDF drucken (Browser)', evidenceJson: 'Evidence JSON' },
        export: {
          evidencePending: 'Evidenzkarte wird noch erzeugt.',
          evidenceUnavailable: 'Evidenzkarte nicht verfügbar.',
        },
        reader: {
          outlineSummary: 'Zusammenfassung',
          outlineSection: 'Abschnitt {num}',
          railToggleHide: 'Belegrand ausblenden',
          railToggleShow: 'Belegrand einblenden',
          regenerate: {
            openButton: 'Neu generieren',
            title: 'Bericht neu generieren',
            description: 'Modell und Modus wählen.',
            confirmButton: 'Regenerieren',
            cancelButton: 'Abbrechen',
          },
        },
      },
    },
  },
})

const outline: ReportOutline = {
  title: 'Nexora Triage Assist',
  summary: 'Sechs Stakeholdergruppen erwarten Entlastung.',
  sections: [
    { title: 'Ausgangslage', description: 'x' },
    { title: 'Stakeholder', description: 'y' },
  ],
}

const STUBS = {
  ReportOutline: { template: '<nav><button data-stub-nav @click="$emit(\'navigate\', \'section-2\')">go</button></nav>' },
  ReportEvidenceRail: true,
  ReportBranchControls: true,
  ReportRedTeamSection: true,
  ReportModelControls: { template: '<div data-stub="model" />' },
  ReportModeControls: { template: '<div data-stub="mode" />' },
}

function mountReader() {
  return mount(ReportReader, {
    props: {
      outline,
      sectionHtml: { 1: '<p>Abschnitt eins</p>', 2: '<p>Abschnitt zwei</p>' },
      evidenceSections: [],
      evidenceIndex: {},
      redTeamFindings: [],
      reportRoute: null,
      reportMode: 'balanced',
    },
    global: { plugins: [i18n], stubs: STUBS },
  })
}

describe('ReportReader', () => {
  it('rendert die Dreispalten-Struktur (Outline, Lesespalte, Belegrand)', () => {
    const wrapper = mountReader()
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.root}"]`).exists()).toBe(true)
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.body}"]`).exists()).toBe(true)
    expect(wrapper.findComponent(ReportEvidenceRail).exists()).toBe(true)
  })

  it('rendert Zusammenfassung und alle Outline-Abschnitte in der Lesespalte', () => {
    const wrapper = mountReader()
    expect(wrapper.find('#summary').exists()).toBe(true)
    expect(wrapper.find('#section-1').text()).toContain('Abschnitt eins')
    expect(wrapper.find('#section-2').text()).toContain('Abschnitt zwei')
  })

  it('schaltet den aktiven Abschnitt um, wenn die Outline navigate emittiert', async () => {
    const wrapper = mountReader()
    await wrapper.find('[data-stub-nav]').trigger('click')
    // aktive Section steuert sectionNum an ReportEvidenceRail
    const rail = wrapper.findComponent(ReportEvidenceRail)
    expect(rail.props('sectionNum')).toBe(2)
  })

  it('blendet den Belegrand ueber den Toggle-Button aus und wieder ein', async () => {
    const wrapper = mountReader()
    const toggle = wrapper.find(`[data-testid="${ReportReaderTestId.railToggle}"]`)
    expect(wrapper.findComponent(ReportEvidenceRail).exists()).toBe(true)
    await toggle.trigger('click')
    expect(wrapper.findComponent(ReportEvidenceRail).exists()).toBe(false)
    await toggle.trigger('click')
    expect(wrapper.findComponent(ReportEvidenceRail).exists()).toBe(true)
  })

  it('Overlay "Neu generieren" ist zunaechst geschlossen, oeffnet per Klick und schliesst per Abbrechen', async () => {
    const wrapper = mountReader()
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOverlay}"]`).exists()).toBe(false)

    await wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOpen}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOverlay}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-stub="model"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="mode"]').exists()).toBe(true)

    await wrapper.find(`[data-testid="${ReportReaderTestId.regenerateClose}"]`).trigger('click')
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOverlay}"]`).exists()).toBe(false)
  })

  it('Bestaetigen im Overlay emittiert regenerate und schliesst das Overlay', async () => {
    const wrapper = mountReader()
    await wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOpen}"]`).trigger('click')
    await wrapper.find(`[data-testid="${ReportReaderTestId.regenerateConfirm}"]`).trigger('click')
    expect(wrapper.emitted('regenerate')).toHaveLength(1)
    expect(wrapper.find(`[data-testid="${ReportReaderTestId.regenerateOverlay}"]`).exists()).toBe(false)
  })

  // ---- Regression aus dem PR-6-Review (Codex) ----

  it('Regression: der Hypothesen-Zaehler der Outline zaehlt den Anhang mit', () => {
    // `hypotheses` ist auf fuenf gedeckelt, der Ueberhang steht in
    // `hypotheses_appendix` (bis 50). Der Zaehler las nur die erste Liste und
    // meldete damit systematisch zu wenig.
    const mkHypo = (id: string) => ({
      hypothesis_id: id,
      hypothesis_text: 't',
      rationale: 'r',
      suggested_evidence: [],
    })
    const evidenceSections = [
      {
        section_index: 1,
        section_title: 'Ausgangslage',
        section_summary: 's',
        claims: [],
        hypotheses: [mkHypo('h1'), mkHypo('h2')],
        hypotheses_appendix: [mkHypo('h3'), mkHypo('h4'), mkHypo('h5')],
        data_gaps: [],
        structured_metadata: {},
        generation_failed: false,
        unbound_evidence_refs: [],
        unverified_statements: [],
      },
    ] as unknown as ReportSection[]

    const wrapper = mount(ReportReader, {
      props: {
        outline,
        sectionHtml: { 1: '<p>Abschnitt eins</p>' },
        evidenceSections,
        evidenceIndex: {},
        redTeamFindings: [],
        reportRoute: null,
        reportMode: 'balanced',
      },
      global: {
        plugins: [i18n],
        stubs: {
          ...STUBS,
          ReportOutline: {
            props: ['hypothesesCount'],
            template: '<nav data-testid="outline-probe">{{ hypothesesCount }}</nav>',
          },
        },
      },
    })

    expect(wrapper.find('[data-testid="outline-probe"]').text()).toBe('5')
  })
})

