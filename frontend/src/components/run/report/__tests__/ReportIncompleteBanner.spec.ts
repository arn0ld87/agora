import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ReportIncompleteBanner from '../ReportIncompleteBanner.vue'
import { reportData } from '@/composables/run/report/__tests__/reportFixtures'
import { i18n } from './helpers'

function banner(report: ReturnType<typeof reportData> | null) {
  return mount(ReportIncompleteBanner, { props: { report }, global: { plugins: [i18n] } })
}

describe('ReportIncompleteBanner', () => {
  it('fehlt bei einem sauberen, fertigen Bericht und ohne Bericht', () => {
    expect(banner(reportData()).find('[data-testid="report-banner"]').exists()).toBe(false)
    expect(banner(null).find('[data-testid="report-banner"]').exists()).toBe(false)
  })

  it('nennt fehlende Abschnitte namentlich und Degradationen mit Komponente und detail; blocking ist hervorgehoben', () => {
    const w = banner(
      reportData({
        status: 'incomplete',
        missing_sections: ['Akteure', 'Szenarien'],
        run_degradations: [
          { component: 'simulation_positioning', reason: 'zu_wenig_stimmen', detail: '3 von 12 Stimmen beziehen Stellung', severity: 'warning' },
          { component: 'run_cancellation', reason: 'abgebrochen', detail: 'Nach Abbruch fehlen Abschnitte 4 und 5', severity: 'blocking' },
        ],
      }),
    )
    const el = w.get('[data-testid="report-banner"]')
    expect(el.attributes('role')).toBe('status')
    expect(el.get('h2').text()).toBe('Unvollständig: Was fehlt')
    expect(w.get('[data-testid="report-banner-missing"]').findAll('li').map((l) => l.text())).toEqual(['Akteure', 'Szenarien'])
    const items = w.get('[data-testid="report-banner-degradations"]').findAll('li')
    expect(items).toHaveLength(2)
    expect(items[0]!.text()).toContain('Zu wenige Stimmen beziehen Stellung zur Streitfrage')
    expect(items[0]!.text()).toContain('3 von 12 Stimmen beziehen Stellung')
    expect(items[0]!.attributes('data-severity')).toBe('warning')
    expect(items[1]!.text()).toContain('Blockierend')
    expect(items[1]!.text()).toContain('Nach Abbruch fehlen Abschnitte 4 und 5')
    expect(items[1]!.classes()).toContain('rr-banner__item--blocking')
    // Der Zustand steht als Text; „fertig“ kommt nirgends vor.
    expect(el.text()).not.toMatch(/fertig/i)
  })

  it('Unvollständig ohne jede Einzelangabe sagt das ehrlich', () => {
    const w = banner(reportData({ status: 'incomplete' }))
    expect(w.get('[data-testid="report-banner-nodetail"]').text()).toContain('keine einzelnen Abschnitte')
  })

  it('ein fertiger Bericht mit Einschränkungen bekommt das Band mit Hinweisen, nicht als „Unvollständig“', () => {
    const w = banner(
      reportData({ run_degradations: [{ component: 'persona_generation', reason: 'fallback', detail: '', severity: 'warning' }] }),
    )
    expect(w.get('h2').text()).toBe('Hinweise zum Bericht: Was fehlt')
    // Ohne detail steht der Grund.
    expect(w.get('[data-testid="report-banner-degradations"]').text()).toContain('fallback')
  })
})
