import { describe, expect, it } from 'vitest'
import {
  INTERVIEW_PROMPT_PREFIX,
  buildConversations,
  buildGroupConversation,
  conversationIdForGroup,
  conversationIdForPersona,
  parseConversationId,
  stripInterviewPrefix,
} from '../conversations'
import type { InterviewHistoryItem } from '@/contracts/interviewContract'

function item(over: Partial<InterviewHistoryItem> & { agent_id: number }): InterviewHistoryItem {
  return {
    response: 'Antwort',
    prompt: `${INTERVIEW_PROMPT_PREFIX}Frage`,
    timestamp: '2026-10-07T10:00:00',
    platform: 'reddit',
    ...over,
  } as InterviewHistoryItem
}

describe('stripInterviewPrefix', () => {
  it('schneidet den festen Backend-Präfix ab', () => {
    expect(stripInterviewPrefix(`${INTERVIEW_PROMPT_PREFIX}Was denken Sie?`)).toBe('Was denken Sie?')
    expect(stripInterviewPrefix(`${INTERVIEW_PROMPT_PREFIX} Was denken Sie?`)).toBe('Was denken Sie?')
  })

  it('lässt unbekannten Text unverändert', () => {
    expect(stripInterviewPrefix('Was denken Sie?')).toBe('Was denken Sie?')
    expect(stripInterviewPrefix('')).toBe('')
  })
})

describe('conversationId', () => {
  it('bildet und liest beide Formate', () => {
    expect(conversationIdForPersona(3)).toBe('persona-3')
    expect(conversationIdForGroup('ab_1')).toBe('group-ab_1')
    expect(parseConversationId('persona-12')).toEqual({ kind: 'persona', agentId: 12 })
    expect(parseConversationId('group-ab_1')).toEqual({ kind: 'group', groupId: 'ab_1' })
  })

  it('verwirft alles andere', () => {
    for (const bad of ['', 'persona-', 'persona-x', 'persona--1', 'group-', 'group-a b', 'foo', undefined, null]) {
      expect(parseConversationId(bad as string | null | undefined), String(bad)).toBeNull()
    }
  })
})

describe('buildConversations', () => {
  it('gruppiert je Persona, chronologisch, mit abgeschnittenem Präfix', () => {
    const convs = buildConversations([
      item({ agent_id: 1, timestamp: '2026-10-07T10:05:00', prompt: `${INTERVIEW_PROMPT_PREFIX}Zweite`, response: 'B' }),
      item({ agent_id: 2, timestamp: '2026-10-07T10:01:00', prompt: 'Eigene Frage', response: 'X' }),
      item({ agent_id: 1, timestamp: '2026-10-07T10:00:00', prompt: `${INTERVIEW_PROMPT_PREFIX}Erste`, response: 'A' }),
    ])
    expect(convs.map((c) => c.conversationId)).toEqual(['persona-1', 'persona-2'])
    const first = convs[0]
    expect(first.agentId).toBe(1)
    expect(first.count).toBe(2)
    expect(first.lastTimestamp).toBe('2026-10-07T10:05:00')
    expect(first.turns.map((t) => [t.question, t.answer])).toEqual([
      ['Erste', 'A'],
      ['Zweite', 'B'],
    ])
    expect(convs[1].turns[0].question).toBe('Eigene Frage')
  })

  it('sortiert Gespräche nach jüngster Aktivität absteigend', () => {
    const convs = buildConversations([
      item({ agent_id: 5, timestamp: '2026-10-07T09:00:00' }),
      item({ agent_id: 6, timestamp: '2026-10-07T11:00:00' }),
    ])
    expect(convs.map((c) => c.agentId)).toEqual([6, 5])
  })

  it('führt zusätzliche Sitzungszüge mit Fehler mit und rät keine Gruppen', () => {
    const convs = buildConversations(
      [item({ agent_id: 1, prompt: `${INTERVIEW_PROMPT_PREFIX}Gleiche Frage` }), item({ agent_id: 2, prompt: `${INTERVIEW_PROMPT_PREFIX}Gleiche Frage` })],
      [{ agentId: 1, turn: { question: 'Neu', answer: null, timestamp: '2026-10-07T12:00:00', platform: null, error: 'Zeitüberschreitung' } }],
    )
    expect(convs.every((c) => c.conversationId.startsWith('persona-'))).toBe(true)
    const one = convs.find((c) => c.agentId === 1)!
    expect(one.turns).toHaveLength(2)
    expect(one.turns[1]).toMatchObject({ question: 'Neu', answer: null, error: 'Zeitüberschreitung' })
  })

  it('ohne Verlauf keine Gespräche', () => {
    expect(buildConversations([])).toEqual([])
  })
})

describe('buildGroupConversation', () => {
  it('führt Antworten und Fehler je Persona', () => {
    const g = buildGroupConversation({
      groupId: 'g1',
      question: 'Frage an alle',
      askedAt: '2026-10-07T12:00:00',
      answers: [
        { agentId: 1, answer: 'Ja', error: null, timestamp: '2026-10-07T12:00:05', platform: 'reddit' },
        { agentId: 2, answer: null, error: 'Fehlgeschlagen', timestamp: '2026-10-07T12:00:06', platform: 'reddit' },
      ],
    })
    expect(g.conversationId).toBe('group-g1')
    expect(g.agentIds).toEqual([1, 2])
    expect(g.count).toBe(2)
    expect(g.lastTimestamp).toBe('2026-10-07T12:00:06')
  })
})
