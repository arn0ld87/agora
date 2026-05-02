/**
 * Confidence-Utilities — Sub-Slice 16a (Refs #173)
 *
 * Ausgelagert aus ConfidenceBadge.vue + Step4Report.vue,
 * damit beide Komponenten die Logik importieren können ohne
 * zirkulaere Abhaengigkeiten.
 */

export type ConfidenceBucket = 'low' | 'medium' | 'high' | 'verified'

/**
 * Berechnet das Confidence-Label aus einem Score-Wert.
 * Schwellen: verified >=0.85 | high >=0.75 | medium >=0.45 | low <0.45
 */
export function deriveLabel(score: number): ConfidenceBucket {
  if (score >= 0.85) return 'verified'
  if (score >= 0.75) return 'high'
  if (score >= 0.45) return 'medium'
  return 'low'
}

export interface AuditEntry {
  source?: string
  snippet?: string
  [k: string]: unknown
}

export interface SectionConfidenceResult {
  score: number
  label: ConfidenceBucket
  auditTrail: AuditEntry[]
}

interface ClaimLike {
  confidence_score?: number
  audit_trail?: unknown[]
}

/**
 * Berechnet das aggregierte Confidence-Resultat fuer eine Section.
 * - score: arithmetisches Mittel der confidence_score-Werte (4 Dezimalstellen)
 * - label: abgeleitet via deriveLabel
 * - auditTrail: alle audit_trail-Eintraege flach gesammelt (additiv, ohne Duplikate-Filter)
 */
export function aggregateSectionConfidence(section: unknown): SectionConfidenceResult {
  const sec = section as { claims?: ClaimLike[] } | null | undefined
  const claims = Array.isArray(sec?.claims) ? sec!.claims : []
  if (claims.length === 0) {
    return { score: 0, label: 'low', auditTrail: [] }
  }
  const scoreSum = claims.reduce(
    (acc, c) => acc + (typeof c?.confidence_score === 'number' ? c.confidence_score : 0),
    0
  )
  const score = Math.round((scoreSum / claims.length) * 10000) / 10000
  const auditTrail = claims.flatMap(c =>
    Array.isArray(c?.audit_trail) ? (c.audit_trail as AuditEntry[]) : []
  )
  return { score, label: deriveLabel(score), auditTrail }
}
