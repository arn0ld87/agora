/**
 * Claims und Belege eines Berichts (Etappe 5, #1804, Bauplan 4.6), rein und
 * ohne Vue. Eingabe ist die vertragsgeprüfte `EvidenceMap`; nichts wird
 * geraten:
 *
 *  - `deriveClaimSections`  Claims je Abschnitt, zu jedem Claim seine Belege aus
 *                           dem Evidence-Index (Bindung, Confidence, Quellenart).
 *                           Hypothesen und Datenlücken stehen getrennt von Claims.
 *  - `findClaim`            Claim über `?claim=`.
 *  - `deriveChecks`         Prüfhinweise: Binding-/Gate-Probleme des Berichts
 *                           (`unbound_evidence_refs`, `unverified_statements`,
 *                           `gate_decision_log`, `degradation_log`). Sie sind nie
 *                           eine Datenlücke.
 *
 * Ein Beleg, dessen `evidence_id` nicht im Index steht, kann der Vertrag nicht
 * zulassen (`EvidenceMapSchema.superRefine`); er wird hier nicht stillschweigend
 * verworfen, sondern in `missingEvidence` gezählt.
 */
import type {
  ClaimEvidenceBinding,
  ConfidenceLabel,
  EvidenceDegradation,
  EvidenceMap,
  EvidenceRecord,
  EvidenceSourceKind,
  ReportSectionDataGap,
  ReportSectionHypothesis,
  ReportSectionUnverifiedStatement,
} from '@/contracts/reportContract'

export interface ClaimEvidenceView {
  evidenceId: string
  record: EvidenceRecord
  binding: ClaimEvidenceBinding
}

export interface ClaimView {
  claimId: string
  text: string
  confidenceLabel: ConfidenceLabel
  confidenceScore: number
  sectionIndex: number
  sectionTitle: string
  evidence: ClaimEvidenceView[]
  /** Quellenarten der Belege, einmal je Art, in fester Reihenfolge. */
  kinds: EvidenceSourceKind[]
  /** Belege mit `supports_claim === true`. */
  supporting: number
  /** Bindungen ohne Eintrag im Index (laut Vertrag ausgeschlossen, sonst sichtbar). */
  missingEvidence: number
}

export interface SectionClaims {
  sectionIndex: number
  sectionTitle: string
  claims: ClaimView[]
  hypotheses: ReportSectionHypothesis[]
  dataGaps: ReportSectionDataGap[]
}

/** Feste Reihenfolge der Quellenarten (Dokument, Graph, Simulation, Interview, Web, abgeleitet). */
export const SOURCE_KIND_ORDER: readonly EvidenceSourceKind[] = [
  'seed_corpus',
  'graph_relation',
  'agent_action',
  'agent_quote',
  'web_source',
  'inferred',
]

function orderKinds(kinds: Iterable<EvidenceSourceKind>): EvidenceSourceKind[] {
  const set = new Set(kinds)
  return SOURCE_KIND_ORDER.filter((k) => set.has(k))
}

export function deriveClaimSections(map: EvidenceMap): SectionClaims[] {
  return map.sections.map((section) => {
    const claims = section.claims.map((claim): ClaimView => {
      const evidence: ClaimEvidenceView[] = []
      let missing = 0
      for (const binding of claim.evidence) {
        const record = map.evidence_index[binding.evidence_id]
        if (record) evidence.push({ evidenceId: binding.evidence_id, record, binding })
        else missing += 1
      }
      return {
        claimId: claim.claim_id,
        text: claim.claim_text,
        confidenceLabel: claim.confidence_label,
        confidenceScore: claim.confidence_score,
        sectionIndex: section.section_index,
        sectionTitle: section.section_title,
        evidence,
        kinds: orderKinds(evidence.map((e) => e.record.source_kind)),
        supporting: claim.evidence.filter((b) => b.supports_claim === true).length,
        missingEvidence: missing,
      }
    })
    return {
      sectionIndex: section.section_index,
      sectionTitle: section.section_title,
      claims,
      hypotheses: [...section.hypotheses, ...section.hypotheses_appendix],
      dataGaps: section.data_gaps,
    }
  })
}

export function findClaim(sections: readonly SectionClaims[], claimId: string | null): ClaimView | null {
  if (!claimId) return null
  for (const s of sections) {
    const hit = s.claims.find((c) => c.claimId === claimId)
    if (hit) return hit
  }
  return null
}

/** Belege eines Claims nach Quellenart gruppiert, in fester Reihenfolge. */
export function groupEvidenceByKind(
  evidence: readonly ClaimEvidenceView[],
): Array<{ kind: EvidenceSourceKind; items: ClaimEvidenceView[] }> {
  return SOURCE_KIND_ORDER.map((kind) => ({
    kind,
    items: evidence.filter((e) => e.record.source_kind === kind),
  })).filter((g) => g.items.length > 0)
}

export interface UnboundRefsNote {
  sectionIndex: number
  sectionTitle: string
  refs: string[]
}

export interface UnverifiedNote {
  sectionIndex: number
  sectionTitle: string
  statements: ReportSectionUnverifiedStatement[]
}

export interface ReportChecks {
  unbound: UnboundRefsNote[]
  unverified: UnverifiedNote[]
  gateDecisions: EvidenceDegradation[]
  degradations: EvidenceDegradation[]
  /** Anzahl der Einzelhinweise (für den Titel des Blocks). */
  total: number
}

export function deriveChecks(map: EvidenceMap): ReportChecks {
  const unbound: UnboundRefsNote[] = []
  const unverified: UnverifiedNote[] = []
  for (const s of map.sections) {
    if (s.unbound_evidence_refs.length > 0) {
      unbound.push({ sectionIndex: s.section_index, sectionTitle: s.section_title, refs: s.unbound_evidence_refs })
    }
    if (s.unverified_statements.length > 0) {
      unverified.push({
        sectionIndex: s.section_index,
        sectionTitle: s.section_title,
        statements: s.unverified_statements,
      })
    }
  }
  const total =
    unbound.reduce((n, u) => n + u.refs.length, 0) +
    unverified.reduce((n, u) => n + u.statements.length, 0) +
    map.gate_decision_log.length +
    map.degradation_log.length
  return {
    unbound,
    unverified,
    gateDecisions: map.gate_decision_log,
    degradations: map.degradation_log,
    total,
  }
}
