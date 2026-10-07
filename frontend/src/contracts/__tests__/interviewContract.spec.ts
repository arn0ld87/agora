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
