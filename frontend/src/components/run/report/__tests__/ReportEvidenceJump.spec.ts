import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import ReportEvidenceJump from '../evidence/ReportEvidenceJump.vue'
import { claimsMap, EV, NODE_UUID, recordOf } from '@/composables/run/report/__tests__/claimFixtures'
import type { ClaimEvidenceView } from '@/composables/run/report/reportClaims'
import type { EvidenceFeedState } from '@/composables/run/report/useEvidenceFeedCheck'
import { Stub } from './helpers'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } as never })
const map = claimsMap()

function view(id: string, patch: Record<string, unknown> = {}): ClaimEvidenceView {
  return { evidenceId: id, record: { ...recordOf(map, id), ...patch }, binding: { evidence_id: id, supports_claim: true } } as ClaimEvidenceView
}

async function mountJump(
  item: ClaimEvidenceView,
  over: { feedState?: EvidenceFeedState; feedPosts?: Array<{ post_id: string; body: string }> } = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'RunSimulationPost', path: '/p/:simulationId/:postId', component: Stub },
      { name: 'RunGraph', path: '/g/:simulationId', component: Stub },
      { name: 'RunInterviews', path: '/i/:simulationId', component: Stub },
    ],
  })
  await router.push('/g/sim_1')
  const wrapper = mount(ReportEvidenceJump, {
    props: {
      item,
      simulationId: 'sim_1',
      reportId: 'report_1',
      claimId: 'claim_01',
      feedState: over.feedState ?? 'ready',
      feedPosts: over.feedPosts ?? [],
    },
    global: { plugins: [router, i18n] },
  })
  await flushPromises()
  return wrapper
}

const goodPost = [{ post_id: 'twitter:12', body: 'Die Abgabe trifft uns hart, sagt Mira.' }]

describe('ReportEvidenceJump', () => {
  it('Feed: Link erst bei verifiziertem Beitrag, mit Rückweg-Query und zugänglichem Namen', async () => {
    const w = await mountJump(view(EV.post), { feedPosts: goodPost })
    const a = w.get('[data-testid="report-jump-feed"]')
    expect(a.text()).toBe('Im Feed zeigen')
    expect(a.attributes('aria-label')).toContain('Im Feed zeigen')
    expect(a.attributes('aria-label')).toContain('Agent Mira')
    expect(a.attributes('href')).toBe('/p/sim_1/twitter:12?claim=twitter:12&fromClaim=claim_01&report=report_1')
  })

  it('Feed: während des Ladens neutraler Hinweis, kein Link', async () => {
    const w = await mountJump(view(EV.post), { feedState: 'loading' })
    expect(w.find('a').exists()).toBe(false)
    expect(w.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('checking')
  })

  it('Feed: Textabweichung und fehlender Beitrag geben Hinweis statt Link', async () => {
    const mismatch = await mountJump(view(EV.post), { feedPosts: [{ post_id: 'twitter:12', body: 'Ganz anderes Thema' }] })
    expect(mismatch.find('a').exists()).toBe(false)
    expect(mismatch.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('textMismatch')
    const missing = await mountJump(view(EV.post), { feedPosts: [] })
    expect(missing.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('postMissing')
  })

  it('Feed: Ladefehler gibt Hinweis, die Komponente bleibt stehen', async () => {
    const w = await mountJump(view(EV.post), { feedState: 'error' })
    expect(w.find('a').exists()).toBe(false)
    expect(w.get('[data-testid="report-jump-note"]').text()).toContain('Feed nicht ladbar')
  })

  it('Graph: ein Link je Knoten mit ?entity=', async () => {
    const w = await mountJump(view(EV.node))
    const links = w.findAll('[data-testid="report-jump-graph"]')
    expect(links).toHaveLength(1)
    expect(links[0]!.text()).toBe('Im Graph zeigen')
    expect(links[0]!.attributes('href')).toBe(`/g/sim_1?entity=${NODE_UUID}`)
  })

  it('Graph: mehrere Knoten werden nummeriert und eindeutig benannt', async () => {
    const other = '99999999-2222-4333-8444-555555555555'
    const w = await mountJump(view(EV.node, { origin_node_uuids: [NODE_UUID, other] }))
    const links = w.findAll('[data-testid="report-jump-graph"]')
    expect(links.map((l) => l.text())).toEqual(['Im Graph zeigen (1/2)', 'Im Graph zeigen (2/2)'])
    expect(links[1]!.attributes('aria-label')).toContain('Knoten 2 von 2')
    expect(links[1]!.attributes('href')).toBe(`/g/sim_1?entity=${other}`)
  })

  it('Interview: Link auf den Interviews-Reiter', async () => {
    const w = await mountJump(view(EV.interview))
    const a = w.get('[data-testid="report-jump-interview"]')
    expect(a.text()).toBe('Interview öffnen')
    expect(a.attributes('href')).toBe('/i/sim_1')
  })

  it('inferred bekommt nie einen Link, auch mit Beitragskennung', async () => {
    const w = await mountJump(view(EV.post, { source_kind: 'inferred' }), { feedPosts: goodPost })
    expect(w.find('a').exists()).toBe(false)
    expect(w.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('inferred')
  })

  it('ohne Ziel steht der Grund (Dokument, Kante)', async () => {
    const doc = await mountJump(view(EV.doc))
    expect(doc.find('a').exists()).toBe(false)
    expect(doc.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('noTarget')
    const fact = await mountJump(view(EV.fact))
    expect(fact.get('[data-testid="report-jump-note"]').attributes('data-reason')).toBe('noEdgeId')
    expect(fact.text()).toContain('Kein Sprung')
  })
})
