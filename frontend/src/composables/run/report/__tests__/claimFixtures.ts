/** Testdaten mit Claims, Belegen und Prüfhinweisen (Etappe 5, #1804). Alles läuft durch `EvidenceMapSchema`. */
import { EvidenceMapSchema, type EvidenceMap, type EvidenceRecord } from '@/contracts/reportContract'

export const EV = {
  doc: `ev_${'a'.repeat(32)}`,
  post: `ev_${'b'.repeat(32)}`,
  node: `ev_${'c'.repeat(32)}`,
  fact: `ev_${'d'.repeat(32)}`,
  interview: `ev_${'e'.repeat(32)}`,
} as const

export const NODE_UUID = '11111111-2222-4333-8444-555555555555'

export function record(id: string, over: Record<string, unknown>): Record<string, unknown> {
  return {
    evidence_id: id,
    producer_key: `producer:${id.slice(3, 7)}`,
    type: 'seed_document',
    source: 'Dokument 1, Chunk 4',
    snippet: 'Auszug aus dem Dokument.',
    source_kind: 'seed_corpus',
    ...over,
  }
}

export function claimsMap(over: Record<string, unknown> = {}): EvidenceMap {
  return EvidenceMapSchema.parse({
    schema_version: 3,
    report_id: 'report_1',
    simulation_id: 'sim_1',
    evidence_index: {
      [EV.doc]: record(EV.doc, {}),
      [EV.post]: record(EV.post, {
        type: 'agent_action',
        source_kind: 'agent_action',
        source: 'twitter, Runde 3, Agent Mira',
        snippet: 'Die Abgabe trifft uns hart',
        quote: 'Die Abgabe trifft uns hart',
        origin_post_id: 'twitter:12',
        voice_key: 'agent:3',
      }),
      [EV.node]: record(EV.node, {
        type: 'entity_summary',
        source_kind: 'graph_relation',
        source: 'Graph: Verband Süd',
        snippet: 'Verband Süd vertritt 40 Betriebe.',
        origin_node_uuids: [NODE_UUID],
      }),
      [EV.fact]: record(EV.fact, {
        type: 'graph_fact',
        source_kind: 'graph_relation',
        source: 'Graph: Kante',
        snippet: 'Verband Süd lehnt Abgabe ab.',
      }),
      [EV.interview]: record(EV.interview, {
        type: 'agent_interview',
        source_kind: 'agent_quote',
        source: 'Interview Agent 3',
        snippet: 'Wir würden die Abgabe nicht tragen.',
        persona_stakeholder_group: 'Verbände',
        voice_key: 'agent:3',
      }),
    },
    sections: [
      {
        section_index: 1,
        section_title: 'Risiken der Abgabe',
        section_summary: 'Zusammenfassung',
        claims: [
          {
            claim_id: 'claim_01',
            claim_text: 'Die Abgabe belastet kleine Betriebe.',
            confidence_label: 'medium',
            confidence_score: 0.6,
            evidence: [
              { evidence_id: EV.doc, supports_claim: true },
              { evidence_id: EV.post, supports_claim: true },
              { evidence_id: EV.fact, supports_claim: false },
            ],
          },
          {
            claim_id: 'claim_02',
            claim_text: 'Verbände lehnen die Abgabe geschlossen ab.',
            confidence_label: 'low',
            confidence_score: 0.3,
            evidence: [{ evidence_id: EV.interview, supports_claim: true }],
          },
        ],
        hypotheses: [
          {
            hypothesis_id: 'hypothesis_01',
            hypothesis_text: 'Große Betriebe passen sich schneller an.',
            rationale: 'Mehr Rücklagen vorhanden.',
          },
        ],
        data_gaps: [
          { gap_id: 'gap_01', claim_text: 'Umsatzzahlen der Betriebe fehlen.', gap_reason: 'Nicht in den Quellen' },
        ],
        unbound_evidence_refs: [`ev_${'f'.repeat(32)}`],
        unverified_statements: [{ statement_text: 'Die Abgabe sinkt 2027.', verdict: 'unverified', reason: 'kein Beleg gefunden' }],
      },
      {
        section_index: 2,
        section_title: 'Akteure',
        section_summary: 'Zusammenfassung',
        claims: [
          {
            claim_id: 'claim_03',
            claim_text: 'Verband Süd vertritt viele Betriebe.',
            confidence_label: 'low',
            confidence_score: 0.35,
            evidence: [{ evidence_id: EV.node, supports_claim: true }],
          },
        ],
      },
    ],
    gate_decision_log: [
      { section_index: 1, claim_id: 'claim_09', violation: 'missing_support', action: 'dropped', detail: 'ohne Beleg entfernt' },
    ],
    ...over,
  })
}

export function recordOf(map: EvidenceMap, id: string): EvidenceRecord {
  const rec = map.evidence_index[id]
  if (!rec) throw new Error(`Beleg fehlt: ${id}`)
  return rec
}
