/**
 * Herkunft eines Knotens oder einer Kante (#1808, ADR-0022 §1 und §5).
 *
 * Das Merkmal sitzt an `provenance.origin`; fehlt es, ist das Element extrahiert
 * (Altbestand). Die Leseform ist absichtlich tolerant: die scharfe Form steht im
 * Bearbeitungsvertrag (`contracts/graphEditContract`), die Ansicht zeigt nur an.
 */
import type { GraphOrigin } from '@/contracts/graphEditContract'

interface WithProvenance {
  provenance?: { origin?: GraphOrigin | null } | null
}

/** `manual` oder `edited`, sonst `null` („extrahiert“). */
export function originOf(raw: unknown): GraphOrigin | null {
  if (!raw || typeof raw !== 'object') return null
  const origin = (raw as WithProvenance).provenance?.origin
  return origin === 'manual' || origin === 'edited' ? origin : null
}

/** Eine von Hand angelegte oder von Hand geänderte Kante ist gestrichelt (ADR-0022 §5). */
export function isHandMade(raw: unknown): boolean {
  return originOf(raw) !== null
}
