/**
 * Sprünge aus Belegen an ihren Ursprung (Etappe 5, #1804, Bauplan 4.6), rein und
 * ohne Vue. Nichts wird geraten: ein Sprung entsteht nur aus einer Kennung, die
 * der Beleg selbst trägt (`origin_post_id`, `origin_node_uuids`, `voice_key`).
 *
 *   agent_action      `origin_post_id` -> Feed-Beitrag. Die Kennung ist nur ein
 *                     Kandidat: in etwa 8 % alter Läufe zeigt sie auf einen
 *                     anderen Beitrag. Der Sprung gilt erst, wenn der Beitrag im
 *                     Feed-Snapshot existiert UND sein Text zum Belegtext passt
 *                     (`verifyFeedJump`). Sonst kein Sprung.
 *   entity_summary    `origin_node_uuids` -> Graph-Reiter mit `?entity=<uuid>`
 *   graph_fact        keine Kantenkennung im Beleg: kein Sprung
 *   agent_interview   `voice_key` (`agent:<id>`) -> Interviews-Reiter des Laufs
 *   übrige Arten      kein Sprungziel
 *
 * Query-Namen (Entscheidung Etappe 5): `?claim=` hat in der Faden-Ansicht schon
 * eine Bedeutung, nämlich die `post_id`, die dort hervorgehoben wird (nicht die
 * `claim_id` des Berichts). Der Feed-Sprung setzt deshalb `claim=<post_id>` für die
 * Hervorhebung und trägt den Rückweg in eigenen Namen: `fromClaim=<claim_id>` und
 * optional `report=<report_id>`. Nur beide zusammen (`fromClaim`) erzeugen den Link
 * „Zurück zum Bericht".
 */
import type { RouteLocationRaw } from 'vue-router'
import type { EvidenceRecord } from '@/contracts/reportContract'

/** Routenname des Interviews-Reiters; einzige Stelle, die ihn kennt (Umstellung in der Interviews-Etappe). */
export const INTERVIEWS_ROUTE_NAME = 'RunInterviewsLegacy'

/** Warum es keinen Sprung gibt; die Oberfläche übersetzt den Schlüssel. */
export type NoJumpReason =
  | 'noPostId' // agent_action ohne eigenen Beitrag (z. B. Like) oder ohne Kennung
  | 'noNodeId' // entity_summary ohne Knotenkennung
  | 'noEdgeId' // graph_fact: keine Kantenkennung im Beleg
  | 'noVoice' // agent_interview ohne voice_key
  | 'noTarget' // Dokument, Web, Kennzahl, Kette: kein Sprungziel
  | 'inferred' // abgeleitet, nicht belegt

export type JumpTarget =
  | { kind: 'feed'; postId: string }
  | { kind: 'graph'; nodeUuids: string[] }
  | { kind: 'interview'; voiceKey: string }
  | { kind: 'none'; reason: NoJumpReason }

export function resolveEvidenceJump(record: EvidenceRecord): JumpTarget {
  if (record.source_kind === 'inferred') return { kind: 'none', reason: 'inferred' }
  switch (record.type) {
    case 'agent_action':
      return record.origin_post_id
        ? { kind: 'feed', postId: record.origin_post_id }
        : { kind: 'none', reason: 'noPostId' }
    case 'entity_summary':
      return record.origin_node_uuids && record.origin_node_uuids.length > 0
        ? { kind: 'graph', nodeUuids: [...record.origin_node_uuids] }
        : { kind: 'none', reason: 'noNodeId' }
    case 'graph_fact':
      return { kind: 'none', reason: 'noEdgeId' }
    case 'agent_interview':
      return record.voice_key
        ? { kind: 'interview', voiceKey: record.voice_key }
        : { kind: 'none', reason: 'noVoice' }
    default:
      return { kind: 'none', reason: 'noTarget' }
  }
}

// --- Textabgleich -----------------------------------------------------------

/** Mindestlänge für einen Teilstring-Vergleich; kürzere Texte müssen gleich sein. */
const MIN_CONTAINED = 8

/** Kleinschreibung, ohne Satzzeichen und Auslassungspunkte, Leerraum gestaucht. */
export function normalizeText(value: string): string {
  return value
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function contains(haystack: string, needle: string): boolean {
  if (!needle) return false
  if (needle.length < MIN_CONTAINED) return haystack === needle
  return haystack.includes(needle)
}

/** Passt der Beitragstext zum Belegtext (normalisiert, Enthaltensein in einer Richtung)? */
export function postTextMatches(body: string, record: Pick<EvidenceRecord, 'quote' | 'snippet' | 'value'>): boolean {
  const post = normalizeText(body)
  if (!post) return false
  const candidates = [record.quote, record.snippet, typeof record.value === 'string' ? record.value : null]
    .filter((c): c is string => typeof c === 'string')
    .map(normalizeText)
    .filter((c) => c.length > 0)
  return candidates.some((c) => contains(post, c) || contains(c, post))
}

export type FeedCheck = { ok: true; postId: string } | { ok: false; reason: 'postMissing' | 'textMismatch' }

/** Prüft den Kandidaten gegen den Feed-Snapshot: existiert der Beitrag und stimmt der Text? */
export function verifyFeedJump(
  postId: string,
  record: Pick<EvidenceRecord, 'quote' | 'snippet' | 'value'>,
  posts: ReadonlyArray<{ post_id: string; body: string }>,
): FeedCheck {
  const post = posts.find((p) => p.post_id === postId)
  if (!post) return { ok: false, reason: 'postMissing' }
  return postTextMatches(post.body, record) ? { ok: true, postId } : { ok: false, reason: 'textMismatch' }
}

// --- Routen -----------------------------------------------------------------

export interface JumpRouteContext {
  simulationId: string
  /** Gewählter Claim; reist als `?fromClaim=` mit und ermöglicht den Rückweg. */
  claimId: string | null
  /** Berichtsfassung; reist als `?report=` mit, damit der Rückweg dieselbe Fassung öffnet. */
  reportId: string | null
}

function carried(ctx: JumpRouteContext): Record<string, string> {
  const q: Record<string, string> = {}
  if (ctx.claimId) q['fromClaim'] = ctx.claimId
  if (ctx.reportId) q['report'] = ctx.reportId
  return q
}

export function feedRoute(postId: string, ctx: JumpRouteContext): RouteLocationRaw {
  return { name: 'RunSimulationPost', params: { simulationId: ctx.simulationId, postId }, query: { claim: postId, ...carried(ctx) } }
}

export function graphRoute(nodeUuid: string, ctx: Pick<JumpRouteContext, 'simulationId'>): RouteLocationRaw {
  return { name: 'RunGraph', params: { simulationId: ctx.simulationId }, query: { entity: nodeUuid } }
}

/** Interviews-Reiter des Laufs (Ziel aus `runTabs.ts`, bis die Interviews-Etappe eine eigene Route bringt). */
export function interviewRoute(ctx: Pick<JumpRouteContext, 'simulationId'>): RouteLocationRaw {
  return { name: INTERVIEWS_ROUTE_NAME, params: { simulationId: ctx.simulationId } }
}

/** Rückweg aus einem Feed-Beitrag in den Bericht; ohne `report` die jüngste Fassung. */
export function reportBackRoute(
  simulationId: string,
  query: { claim: string; report: string | null },
): RouteLocationRaw {
  return {
    name: 'RunReport',
    params: query.report ? { simulationId, reportId: query.report } : { simulationId },
    query: { claim: query.claim },
  }
}
