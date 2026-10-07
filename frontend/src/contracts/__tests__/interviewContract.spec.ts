import { describe, expect, it } from 'vitest'
import {
  InterviewBatchDataSchema,
  InterviewHistoryDataSchema,
} from '../interviewContract'

describe('interviewContract', () => {
  it('liest die Batch-Form samt Teilfehler und normalisiert agent_id', () => {
    const parsed = InterviewBatchDataSchema.parse({
      success: true,
      interviews_count: 2,
      mode: 'direct',
      result: {
        results: {
          reddit_1: { agent_id: 1, platform: 'reddit', prompt: 'p', response: 'A', timestamp: 't', extra: 1 },
          reddit_2: { agent_id: '2', platform: 'reddit', error: 'kaputt' },
        },
      },
      timestamp: 't',
    })
    expect(parsed.result.results.reddit_2.agent_id).toBe(2)
    expect(parsed.result.results.reddit_2.error).toBe('kaputt')
    expect((parsed.result.results.reddit_1 as Record<string, unknown>).extra).toBe(1)
  })

  it('verwirft eine Batch-Antwort ohne results', () => {
    expect(InterviewBatchDataSchema.safeParse({ success: true, result: {} }).success).toBe(false)
  })

  it('liest den Verlauf und verwirft Zeilen ohne prompt/timestamp', () => {
    const ok = InterviewHistoryDataSchema.safeParse({
      count: 1,
      history: [{ agent_id: 3, response: 'R', prompt: 'P', timestamp: 't', platform: 'reddit' }],
    })
    expect(ok.success).toBe(true)
    const bad = InterviewHistoryDataSchema.safeParse({ count: 1, history: [{ agent_id: 3, response: 'R' }] })
    expect(bad.success).toBe(false)
  })
})

describe('InterviewBudgetExceeded contract', () => {
  it('hält die Zod-Felder deckungsgleich mit dem generierten Pydantic-Schema', async () => {
    const { InterviewBudgetExceededSchema } = await import('../interviewContract')
    const jsonSchema = (await import('../../../../schemas/interview-budget-exceeded.schema.json')).default
    expect(Object.keys(InterviewBudgetExceededSchema.shape).sort()).toEqual(Object.keys(jsonSchema.properties).sort())
    expect(InterviewBudgetExceededSchema.shape.dimension.options).toEqual(jsonSchema.properties.dimension.enum)
    expect(InterviewBudgetExceededSchema.shape.termination_reason.options).toEqual(
      jsonSchema.properties.termination_reason.enum,
    )
  })

  it('setzt persisted_count auf 0, wenn das Feld fehlt, und lehnt einen Body ohne Zahlen ab', async () => {
    const { InterviewBudgetExceededSchema } = await import('../interviewContract')
    const body = { error: 'voll', termination_reason: 'budget_calls', dimension: 'calls', observed: 3, threshold: 3 }
    expect(InterviewBudgetExceededSchema.parse(body).persisted_count).toBe(0)
    expect(InterviewBudgetExceededSchema.safeParse({ error: 'voll' }).success).toBe(false)
  })
})
