import { describe, expect, it } from 'vitest'

import { parseModelActiveEvent } from '../modelActiveContract'

describe('parseModelActiveEvent', () => {
  it('akzeptiert ein vom Backend publiziertes MiniMax-Event', () => {
    const event = {
      model: 'MiniMax-M3',
      context: 'chat',
      provider: 'minimax',
      ts: 1_752_800_000,
      extra: null,
    }

    expect(parseModelActiveEvent(event)).toEqual({ ok: true, data: event })
  })

  it('akzeptiert ein vom Backend publiziertes Google-Event', () => {
    const event = {
      model: 'gemini-3-flash-preview',
      context: 'chat_json',
      provider: 'google',
      ts: 1_752_800_001,
      extra: null,
    }

    expect(parseModelActiveEvent(event)).toEqual({ ok: true, data: event })
  })
})
