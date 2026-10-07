import { describe, expect, it } from 'vitest'
import {
  feedRoute,
  graphRoute,
  INTERVIEWS_ROUTE_NAME,
  interviewRoute,
  normalizeText,
  postTextMatches,
  reportBackRoute,
  resolveEvidenceJump,
  verifyFeedJump,
} from '../evidenceJumps'
import { claimsMap, EV, NODE_UUID, recordOf } from './claimFixtures'

const map = claimsMap()

describe('resolveEvidenceJump', () => {
  it('agent_action mit origin_post_id: Feed-Kandidat', () => {
    expect(resolveEvidenceJump(recordOf(map, EV.post))).toEqual({ kind: 'feed', postId: 'twitter:12' })
  })
  it('agent_action ohne origin_post_id: noPostId', () => {
    const rec = { ...recordOf(map, EV.post), origin_post_id: null }
    expect(resolveEvidenceJump(rec)).toEqual({ kind: 'none', reason: 'noPostId' })
  })
  it('entity_summary: Graph mit allen Knoten, ohne Knoten noNodeId', () => {
    expect(resolveEvidenceJump(recordOf(map, EV.node))).toEqual({ kind: 'graph', nodeUuids: [NODE_UUID] })
    expect(resolveEvidenceJump({ ...recordOf(map, EV.node), origin_node_uuids: [] })).toEqual({ kind: 'none', reason: 'noNodeId' })
    expect(resolveEvidenceJump({ ...recordOf(map, EV.node), origin_node_uuids: null })).toEqual({ kind: 'none', reason: 'noNodeId' })
  })
  it('graph_fact: noEdgeId', () => {
    expect(resolveEvidenceJump(recordOf(map, EV.fact))).toEqual({ kind: 'none', reason: 'noEdgeId' })
  })
  it('agent_interview: mit voice_key Interview, sonst noVoice', () => {
    expect(resolveEvidenceJump(recordOf(map, EV.interview))).toEqual({ kind: 'interview', voiceKey: 'agent:3' })
    expect(resolveEvidenceJump({ ...recordOf(map, EV.interview), voice_key: null })).toEqual({ kind: 'none', reason: 'noVoice' })
  })
  it('übrige Arten: noTarget', () => {
    expect(resolveEvidenceJump(recordOf(map, EV.doc))).toEqual({ kind: 'none', reason: 'noTarget' })
  })
  it('inferred bekommt nie einen Sprung, auch mit Kennung', () => {
    const rec = { ...recordOf(map, EV.post), source_kind: 'inferred' as const }
    expect(resolveEvidenceJump(rec)).toEqual({ kind: 'none', reason: 'inferred' })
  })
})

describe('Textabgleich', () => {
  it('normalizeText: Kleinschreibung, Satzzeichen und Leerraum', () => {
    expect(normalizeText('  Die  Abgabe, trifft… UNS hart! ')).toBe('die abgabe trifft uns hart')
  })
  it('Teilstring in beide Richtungen', () => {
    const rec = { quote: 'Die Abgabe trifft uns hart', snippet: '', value: null }
    expect(postTextMatches('Die Abgabe trifft uns hart, wirklich sehr.', rec)).toBe(true)
    expect(postTextMatches('trifft uns hart', { quote: 'Die Abgabe trifft uns hart', snippet: '', value: null })).toBe(true)
  })
  it('kurze Texte müssen gleich sein', () => {
    expect(postTextMatches('Ja', { quote: 'Ja!', snippet: '', value: null })).toBe(true)
    expect(postTextMatches('Ja, sicher doch, und mehr', { quote: 'Ja', snippet: '', value: null })).toBe(false)
  })
  it('Abweichung und leerer Beitrag passen nicht', () => {
    expect(postTextMatches('Ganz anderer Text im Beitrag', { quote: 'Die Abgabe trifft uns hart', snippet: '', value: null })).toBe(false)
    expect(postTextMatches('   ', { quote: 'Die Abgabe trifft uns hart', snippet: '', value: null })).toBe(false)
  })
  it('snippet und String-value zählen als Kandidaten', () => {
    expect(postTextMatches('Wir zahlen die Abgabe nicht', { quote: null, snippet: 'zahlen die Abgabe', value: null })).toBe(true)
    expect(postTextMatches('Wir zahlen die Abgabe nicht', { quote: null, snippet: '', value: 'zahlen die Abgabe' })).toBe(true)
    expect(postTextMatches('Wir zahlen die Abgabe nicht', { quote: null, snippet: '', value: 42 })).toBe(false)
  })
})

describe('verifyFeedJump', () => {
  const rec = { quote: 'Die Abgabe trifft uns hart', snippet: '', value: null }
  it('Beitrag fehlt', () => {
    expect(verifyFeedJump('twitter:12', rec, [{ post_id: 'twitter:1', body: 'x' }])).toEqual({ ok: false, reason: 'postMissing' })
  })
  it('Text passt nicht', () => {
    expect(verifyFeedJump('twitter:12', rec, [{ post_id: 'twitter:12', body: 'Völlig anderes Thema heute' }])).toEqual({
      ok: false,
      reason: 'textMismatch',
    })
  })
  it('passt', () => {
    expect(verifyFeedJump('twitter:12', rec, [{ post_id: 'twitter:12', body: 'Die Abgabe trifft uns hart.' }])).toEqual({
      ok: true,
      postId: 'twitter:12',
    })
  })
})

describe('Routen', () => {
  it('feedRoute: claim ist die post_id, Rückweg in fromClaim und report', () => {
    expect(feedRoute('twitter:12', { simulationId: 's1', claimId: 'claim_01', reportId: 'r1' })).toEqual({
      name: 'RunSimulationPost',
      params: { simulationId: 's1', postId: 'twitter:12' },
      query: { claim: 'twitter:12', fromClaim: 'claim_01', report: 'r1' },
    })
    const bare = feedRoute('twitter:12', { simulationId: 's1', claimId: null, reportId: null }) as { query: unknown }
    expect(bare.query).toEqual({ claim: 'twitter:12' })
  })
  it('graphRoute', () => {
    expect(graphRoute(NODE_UUID, { simulationId: 's1' })).toEqual({
      name: 'RunGraph',
      params: { simulationId: 's1' },
      query: { entity: NODE_UUID },
    })
  })
  it('interviewRoute nutzt den gekapselten Routennamen', () => {
    expect(interviewRoute({ simulationId: 's1' })).toEqual({ name: INTERVIEWS_ROUTE_NAME, params: { simulationId: 's1' } })
  })
  it('reportBackRoute: mit und ohne Fassung', () => {
    expect(reportBackRoute('s1', { claim: 'claim_01', report: 'r1' })).toEqual({
      name: 'RunReport',
      params: { simulationId: 's1', reportId: 'r1' },
      query: { claim: 'claim_01' },
    })
    expect(reportBackRoute('s1', { claim: 'claim_01', report: null })).toEqual({
      name: 'RunReport',
      params: { simulationId: 's1' },
      query: { claim: 'claim_01' },
    })
  })
})
