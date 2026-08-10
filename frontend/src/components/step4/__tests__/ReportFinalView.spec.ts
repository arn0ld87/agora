/**
 * ReportFinalView — Evidence-Export bleibt sichtbar (Issue #1188).
 *
 * Vorher: `v-if="evidenceSections.length"` liess den Button spurlos
 * verschwinden, solange die Evidenzkarte (noch) nicht vorliegt — fuer den
 * Nutzer nicht von einem entfernten Feature unterscheidbar. Dieser Test
 * belegt den Regressionsfall: bei leerer evidenceSections-Liste bleibt der
 * Button sichtbar, ist aber deaktiviert (aria-disabled + zugaengliche
 * Beschreibung ueber aria-describedby) und loest keinen Download aus.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ReportFinalView from '../ReportFinalView.vue'
import type { ReportSection } from '../../../contracts/reportContract'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      step4: {
        next: 'Weiter',
        view: { printPdf: 'Als PDF drucken (Browser)', evidenceJson: 'Evidence JSON' },
        export: {
          evidencePending: 'Evidenzkarte wird noch erzeugt.',
          evidenceUnavailable: 'Evidenzkarte nicht verfügbar.',
        },
      },
    },
  },
})

const STUBS = {
  ReportEvidencePanel: true,
  ReportBranchControls: true,
  ReportRedTeamSection: true,
}

function mountView(evidenceSections: ReportSection[], evidenceUnavailable = false) {
  return mount(ReportFinalView, {
    props: {
      reportHtml: '<p>Testbericht</p>',
      evidenceSections,
      evidenceUnavailable,
    },
    global: { plugins: [i18n], stubs: STUBS },
  })
}

describe('ReportFinalView — Evidence-Export-Button (Issue #1188)', () => {
  it('bleibt sichtbar und deaktiviert, solange keine Evidence-Sections vorliegen', async () => {
    const wrapper = mountView([])

    const btn = wrapper.find('[data-testid="download-evidence-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-disabled')).toBe('true')
    expect(btn.attributes('aria-describedby')).toBe('evidence-export-pending-desc')

    const desc = wrapper.find('[data-testid="evidence-export-pending-desc"]')
    expect(desc.exists()).toBe(true)
    expect(desc.text()).toContain('Evidenzkarte wird noch erzeugt.')

    await btn.trigger('click')
    expect(wrapper.emitted('download-evidence')).toBeUndefined()
  })

  it('ist aktiv und loest den Download aus, sobald Evidence-Sections vorliegen', async () => {
    const wrapper = mountView([
      { section_index: 0, section_summary: 'x', data_gaps: [], claims: [] } as unknown as ReportSection,
    ])

    const btn = wrapper.find('[data-testid="download-evidence-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('aria-disabled')).toBe('false')
    expect(wrapper.find('[data-testid="evidence-export-pending-desc"]').exists()).toBe(false)

    await btn.trigger('click')
    expect(wrapper.emitted('download-evidence')).toHaveLength(1)
  })

  // Nachbesserung zum urspruenglichen Fix: nach Ausschoepfen des
  // Retry-Budgets (Step4Report.vue) ist "wird noch erzeugt" eine
  // Falschaussage — der terminale Zustand braucht einen eigenen Text.
  it('zeigt "nicht verfuegbar" statt "wird noch erzeugt", wenn das Retry-Budget ausgeschoepft ist', () => {
    const wrapper = mountView([], true)

    const btn = wrapper.find('[data-testid="download-evidence-btn"]')
    expect(btn.attributes('aria-disabled')).toBe('true')

    const desc = wrapper.find('[data-testid="evidence-export-pending-desc"]')
    expect(desc.exists()).toBe(true)
    expect(desc.text()).toContain('Evidenzkarte nicht verfügbar.')
    expect(desc.text()).not.toContain('wird noch erzeugt')
  })
})
