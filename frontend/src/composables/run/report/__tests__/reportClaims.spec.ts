import { describe, expect, it } from 'vitest'
import { deriveChecks, deriveClaimSections, findClaim, groupEvidenceByKind } from '../reportClaims'
import { claimsMap, EV } from './claimFixtures'

describe('deriveClaimSections', () => {
  const sections = deriveClaimSections(claimsMap())

  it('Claims je Abschnitt mit Confidence, Belegen und Quellenarten in fester Reihenfolge', () => {
    expect(sections.map((s) => s.sectionIndex)).toEqual([1, 2])
    const c1 = sections[0]!.claims[0]!
    expect(c1.claimId).toBe('claim_01')
    expect(c1.confidenceLabel).toBe('medium')
    expect(c1.evidence.map((e) => e.evidenceId)).toEqual([EV.doc, EV.post, EV.fact])
    expect(c1.supporting).toBe(2)
    expect(c1.kinds).toEqual(['seed_corpus', 'graph_relation', 'agent_action'])
    expect(c1.sectionTitle).toBe('Risiken der Abgabe')
    expect(c1.missingEvidence).toBe(0)
  })

  it('Hypothesen und Datenlücken stehen getrennt von den Claims', () => {
    const s = sections[0]!
    expect(s.claims.map((c) => c.claimId)).toEqual(['claim_01', 'claim_02'])
    expect(s.hypotheses.map((h) => h.hypothesis_id)).toEqual(['hypothesis_01'])
    expect(s.dataGaps.map((g) => g.gap_id)).toEqual(['gap_01'])
  })

  it('findClaim löst über die Kennung auf, sonst null', () => {
    expect(findClaim(sections, 'claim_03')?.sectionIndex).toBe(2)
    expect(findClaim(sections, 'claim_99')).toBeNull()
    expect(findClaim(sections, null)).toBeNull()
  })

  it('groupEvidenceByKind gruppiert in fester Reihenfolge', () => {
    const groups = groupEvidenceByKind(sections[0]!.claims[0]!.evidence)
    expect(groups.map((g) => [g.kind, g.items.length])).toEqual([
      ['seed_corpus', 1],
      ['graph_relation', 1],
      ['agent_action', 1],
    ])
  })
})

describe('deriveChecks', () => {
  it('sammelt Binding-/Gate-Probleme mit Abschnitt und zählt sie', () => {
    const checks = deriveChecks(claimsMap())
    expect(checks.unbound).toHaveLength(1)
    expect(checks.unbound[0]!.sectionTitle).toBe('Risiken der Abgabe')
    expect(checks.unverified[0]!.statements).toHaveLength(1)
    expect(checks.gateDecisions).toHaveLength(1)
    expect(checks.total).toBe(3)
  })

  it('ein Bericht ohne Hinweise zählt 0', () => {
    const map = claimsMap({ gate_decision_log: [] })
    const clean = { ...map, sections: map.sections.map((s) => ({ ...s, unbound_evidence_refs: [], unverified_statements: [] })) }
    expect(deriveChecks(clean).total).toBe(0)
  })
})
