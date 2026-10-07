/**
 * Gespräche aus dem flachen Interview-Verlauf (#1805, Etappe 6). Rein, ohne Vue.
 *
 * Das Backend kennt kein Gesprächskonzept: es speichert Frage-Antwort-Zeilen je
 * Persona (`agent_id` = Listenposition des Profils = `persona_id` im Feed).
 * Ein Gespräch ist hier darum immer "alle Zeilen einer Persona". Gruppen
 * gibt es nur für Fragen, die in DIESER Sitzung gestellt wurden; das
 * Composable hält sie selbst. Aus dem Server-Verlauf werden keine Gruppen
 * geraten: gleiche Frage an mehrere Personas ist dort nicht von zwei
 * Einzelfragen zu unterscheiden. Verlaufseinträge aus Berichts-Interviews
 * liegen in derselben Tabelle und sind nicht zu trennen.
 */
import type { InterviewHistoryItem } from '@/contracts/interviewContract'

/**
 * Fester englischer Präfix, den das Backend jeder Frage voranstellt
 * (`INTERVIEW_PROMPT_PREFIX` in `backend/app/api/simulation_common.py`) und
 * so mitspeichert. Für die Anzeige wird er abgeschnitten.
 */
export const INTERVIEW_PROMPT_PREFIX =
  'Based on your persona, all your past memories and actions, reply directly to me with text without calling any tools:'

export function stripInterviewPrefix(prompt: string): string {
  if (!prompt.startsWith(INTERVIEW_PROMPT_PREFIX)) return prompt
  return prompt.slice(INTERVIEW_PROMPT_PREFIX.length).trimStart()
}

export interface InterviewTurn {
  question: string
  /** `null`, wenn keine Antwort kam; dann steht der Grund in `error`. */
  answer: string | null
  timestamp: string
  platform: string | null
  error?: string | null
}

/** Zusätzlicher Zug aus der laufenden Sitzung (noch nicht oder nie im Verlauf). */
export interface SessionTurn {
  agentId: number
  turn: InterviewTurn
}

export interface PersonaConversation {
  kind: 'persona'
  conversationId: string
  agentId: number
  turns: InterviewTurn[]
  lastTimestamp: string
  count: number
}

export interface GroupAnswer {
  agentId: number
  answer: string | null
  error: string | null
  timestamp: string
  platform: string | null
}

export interface GroupRecord {
  groupId: string
  question: string
  askedAt: string
  answers: GroupAnswer[]
}

export interface GroupConversation {
  kind: 'group'
  conversationId: string
  groupId: string
  question: string
  agentIds: number[]
  answers: GroupAnswer[]
  lastTimestamp: string
  count: number
}

export type ParsedConversationId =
  | { kind: 'persona'; agentId: number }
  | { kind: 'group'; groupId: string }

export function conversationIdForPersona(agentId: number): string {
  return `persona-${agentId}`
}

export function conversationIdForGroup(groupId: string): string {
  return `group-${groupId}`
}

export function parseConversationId(id: string | null | undefined): ParsedConversationId | null {
  if (!id) return null
  const persona = /^persona-(\d+)$/.exec(id)
  if (persona) return { kind: 'persona', agentId: Number(persona[1]) }
  const group = /^group-([A-Za-z0-9_-]+)$/.exec(id)
  if (group) return { kind: 'group', groupId: group[1] }
  return null
}

function time(stamp: string): number {
  const ms = Date.parse(stamp)
  return Number.isNaN(ms) ? 0 : ms
}

/** Je Persona ein Gespräch; Züge chronologisch, Gespräche nach jüngster Aktivität absteigend. */
export function buildConversations(
  history: readonly InterviewHistoryItem[],
  extra: readonly SessionTurn[] = [],
): PersonaConversation[] {
  const byAgent = new Map<number, InterviewTurn[]>()
  const push = (agentId: number, turn: InterviewTurn) => {
    const list = byAgent.get(agentId)
    if (list) list.push(turn)
    else byAgent.set(agentId, [turn])
  }
  for (const row of history) {
    push(row.agent_id, {
      question: stripInterviewPrefix(row.prompt),
      answer: row.response ?? null,
      timestamp: row.timestamp,
      platform: row.platform ?? null,
    })
  }
  for (const e of extra) push(e.agentId, e.turn)

  const out: PersonaConversation[] = []
  for (const [agentId, turns] of byAgent) {
    // Array.sort ist stabil: gleiche Zeitstempel behalten die Eingangsreihenfolge.
    const sorted = [...turns].sort((a, b) => time(a.timestamp) - time(b.timestamp))
    out.push({
      kind: 'persona',
      conversationId: conversationIdForPersona(agentId),
      agentId,
      turns: sorted,
      lastTimestamp: sorted[sorted.length - 1].timestamp,
      count: sorted.length,
    })
  }
  return out.sort((a, b) => time(b.lastTimestamp) - time(a.lastTimestamp))
}

export function buildGroupConversation(record: GroupRecord): GroupConversation {
  const stamps = [record.askedAt, ...record.answers.map((a) => a.timestamp)]
  const last = stamps.reduce((acc, s) => (time(s) >= time(acc) ? s : acc), record.askedAt)
  return {
    kind: 'group',
    conversationId: conversationIdForGroup(record.groupId),
    groupId: record.groupId,
    question: record.question,
    agentIds: record.answers.map((a) => a.agentId),
    answers: record.answers,
    lastTimestamp: last,
    count: record.answers.length,
  }
}
