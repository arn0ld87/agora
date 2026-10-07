import { describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ApiError } from '@/api/envelope'
import ReportEvidencePanel from '../evidence/ReportEvidencePanel.vue'
import { claimsMap } from '@/composables/run/report/__tests__/claimFixtures'
import { mountWithReport, okApi } from './helpers'

const density = {
  success: true,
  data: {
    schema_version: 1,
    claims_total: 3,
    claims_without_support: 0,
    claims_single_support: 2,
    claims_multi_support: 1,
    claims_multi_independent: 1,
    claims_at_single_source_cap: 0,
    claims_with_action_support: 1,
    supporting_links_by_type: {},
    single_support_ratio: 0.67,
  },
}
const stance = {
  success: true,
  data: {
    contested_statement: 'Soll die Abgabe kommen?',
    applicable: true,
    voices_total: 4,
    voices_positioned: 3,
    positioning_ratio: 0.75,
    camp_distribution: { in_favour: 1, opposed: 2 },
    voices: [],
    contributions: [],
    classified_total: 5,
    classification_failed: 0,
  },
}
const omission = { artifact: 'evidence_density', reason: 'contract_violation', detail: 'x', validation_errors: ['Feld fehlt'] }

function mountPanel(artifactsApi: Record<string, unknown>, route = '/simulations/sim_1/report') {
  const api = okApi({ getReportEvidence: vi.fn().mockResolvedValue({ success: true, data: claimsMap() }) })
  return mountWithReport(ReportEvidencePanel, { artifactsApi }, { api, route })
}

describe('ReportEvidencePanel', () => {
  it('zeigt Claim-Liste je Abschnitt mit Confidence als Text, Belegzahl und Quellenarten', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    const claims = wrapper.findAll('[data-testid="report-claim"]')
    expect(claims).toHaveLength(3)
    expect(claims[0]!.text()).toContain('Confidence: mittel (60 %)')
    expect(claims[0]!.text()).toContain('3 Belege')
    expect(claims[0]!.get('[data-testid="report-claim-kinds"]').text()).toBe('Dokument, Graph, Simulation (Beitrag)')
    expect(wrapper.get('[data-testid="report-evidence-hint"]').text()).toContain('Wähle einen Claim')
    expect(wrapper.get('[data-testid="report-evidence-overview"]').text()).toContain('Dokument: 1')
  })

  it('Hypothesen und Datenlücken stehen getrennt von den Claims', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    const hyp = wrapper.get('[data-testid="report-hypotheses"]')
    const gap = wrapper.get('[data-testid="report-gaps"]')
    expect(hyp.text()).toContain('Große Betriebe passen sich schneller an.')
    expect(gap.text()).toContain('Umsatzzahlen der Betriebe fehlen.')
    expect(wrapper.findAll('[data-testid="report-claim"]').map((c) => c.text()).join()).not.toContain('Umsatzzahlen')
  })

  it('Auswahl: schreibt über selectClaim, markiert per aria-current und zeigt die Belege nach Quellenart', async () => {
    const { wrapper, ctx } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    await wrapper.findAll('[data-testid="report-claim"]')[0]!.trigger('click')
    expect(ctx.selectedClaimId.value).toBe('claim_01')
    await flushPromises()
    expect(wrapper.get('#report-claim-claim_01').attributes('aria-current')).toBe('true')
    expect(wrapper.get('#report-claim-claim_02').attributes('aria-current')).toBeUndefined()
    const groups = wrapper.findAll('[data-testid="report-evidence-group"]').map((g) => g.attributes('data-kind'))
    expect(groups).toEqual(['seed_corpus', 'graph_relation', 'agent_action'])
    const first = wrapper.findAll('[data-testid="report-evidence-item"]')[0]!
    expect(first.text()).toContain('Auszug aus dem Dokument.')
    expect(first.text()).toContain('Dokument 1, Chunk 4')
    expect(first.text()).toContain('stützt den Claim')
    await wrapper.findAll('[data-testid="report-claim"]')[0]!.trigger('click')
    expect(ctx.selectedClaimId.value).toBeNull()
  })

  it('Deep-Link: ein per selectClaim gesetzter Claim ist markiert', async () => {
    const { wrapper, ctx } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    ctx.selectClaim('claim_03')
    await flushPromises()
    expect(wrapper.get('#report-claim-claim_03').attributes('aria-current')).toBe('true')
    expect(wrapper.get('[data-testid="report-evidence-for"]').text()).toContain('claim_03')
  })

  it('Kennzahlen: Daten, nicht gespeichert (404) und artifact_omitted bleiben unterscheidbar', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue({ success: true, artifact_omitted: omission }),
      getStance: vi.fn().mockRejectedValue(new ApiError({ code: 'not_found', status: 404, message: 'nicht gefunden' })),
    })
    const omitted = wrapper.get('[data-testid="report-density-omitted"]')
    expect(omitted.attributes('role')).toBe('alert')
    expect(omitted.text()).toContain('artifact_omitted')
    expect(omitted.text()).toContain('Feld fehlt')
    expect(omitted.text()).toContain('keine Datenlücke')
    expect(wrapper.get('[data-testid="report-stance-unsaved"]').text()).toBe('Für diese Fassung nicht gespeichert.')
  })

  it('Kennzahlen mit Daten: Belegdichte und Positionierungsquote', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    expect(wrapper.get('[data-testid="report-density-data"]').text()).toContain('Claims gesamt3')
    expect(wrapper.get('[data-testid="report-stance-data"]').text()).toBe('3 von 4 Stimmen positioniert (75 %)')
    expect(wrapper.get('[data-testid="report-stance-camps"]').text()).toContain('dagegen: 2')
  })

  it('applicable=false ist ein Lauf ohne Streitfrage, kein Fehler', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue({ success: true, data: { applicable: false } }),
    })
    expect(wrapper.get('[data-testid="report-stance-not-applicable"]').text()).toBe('Lauf ohne Streitfrage')
    expect(wrapper.find('[data-testid="report-stance-failed"]').exists()).toBe(false)
  })

  it('Fehler-Envelope not_found zählt als nicht gespeichert, andere Fehler als Fehler', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue({ success: false, code: 'not_found', error: 'weg' }),
      getStance: vi.fn().mockRejectedValue(new Error('offline')),
    })
    expect(wrapper.find('[data-testid="report-density-unsaved"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="report-stance-failed"]').text()).toContain('offline')
  })

  it('Prüfhinweise: eingeklappter Block mit Zahl im Titel, Wortlaut Binding-/Gate-Problem statt Datenlücke', async () => {
    const { wrapper } = await mountPanel({
      getDensity: vi.fn().mockResolvedValue(density),
      getStance: vi.fn().mockResolvedValue(stance),
    })
    const checks = wrapper.get('[data-testid="report-checks"]')
    expect(checks.attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="report-checks-summary"]').text()).toBe('Prüfhinweise (3)')
    expect(checks.text()).toContain('Binding-/Gate-Probleme')
    expect(checks.text()).toContain('keine Datenlücken')
    expect(wrapper.get('[data-testid="report-checks-unbound"]').text()).toContain('Risiken der Abgabe')
    expect(wrapper.get('[data-testid="report-checks-unverified"]').text()).toContain('Die Abgabe sinkt 2027.')
    expect(wrapper.get('[data-testid="report-checks-gate"]').text()).toContain('claim_09')
  })
})
