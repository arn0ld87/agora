import { beforeEach, describe, expect, it, vi } from 'vitest'

const post = vi.hoisted(() => vi.fn())
vi.mock('../index', () => ({ default: { post } }))

import { ApiError } from '../envelope'
import { askPersonas, getInterviewHistory } from '../interviews'

beforeEach(() => post.mockReset())

describe('askPersonas', () => {
  it('sendet die Batch-Form und liefert Antworten je Eintrag, Teilfehler bleiben erhalten', async () => {
    post.mockResolvedValue({
      success: true,
      data: {
        success: true,
        result: {
          results: {
            reddit_1: { agent_id: 1, platform: 'reddit', prompt: 'p', response: 'A', timestamp: 't1' },
            reddit_2: { agent_id: 2, platform: 'reddit', error: 'Zeitüberschreitung' },
          },
        },
      },
    })
    const out = await askPersonas('sim_1', [
      { agentId: 1, prompt: 'Frage' },
      { agentId: 2, prompt: 'Frage', platform: 'twitter' },
    ], { timeout: 90 })

    expect(post).toHaveBeenCalledWith('/api/simulation/interview/batch', {
      simulation_id: 'sim_1',
      interviews: [
        { agent_id: 1, prompt: 'Frage' },
        { agent_id: 2, prompt: 'Frage', platform: 'twitter' },
      ],
      timeout: 90,
    })
    expect(out).toEqual([
      { agentId: 1, platform: 'reddit', prompt: 'p', response: 'A', timestamp: 't1', error: null },
      { agentId: 2, platform: 'reddit', prompt: null, response: null, timestamp: null, error: 'Zeitüberschreitung' },
    ])
  })

  it('reicht den ApiError des Interceptors (success:false bei HTTP 200) unverändert durch', async () => {
    post.mockRejectedValueOnce(
      new ApiError({ code: 'budget_exceeded', status: 200, message: 'Token-Budget überschritten' }),
    )
    const err = await askPersonas('sim_1', [{ agentId: 1, prompt: 'x' }]).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect([(err as ApiError).code, (err as ApiError).status, (err as ApiError).message]).toEqual([
      'budget_exceeded',
      200,
      'Token-Budget überschritten',
    ])
  })

  it('macht eine Zod-Verletzung sichtbar', async () => {
    post.mockResolvedValue({ success: true, data: { result: {} } })
    await expect(askPersonas('sim_1', [{ agentId: 1, prompt: 'x' }])).rejects.toThrow(/Vertragsbruch interview\/batch/)
  })

  it('reicht Transportfehler unverändert durch', async () => {
    // Der Interceptor (api/index.ts) liefert den Fehler fertig als ApiError; hier zählt, dass nichts umgedeutet wird.
    post.mockRejectedValueOnce(new Error('Netz weg'))
    await expect(askPersonas('sim_1', [{ agentId: 1, prompt: 'x' }])).rejects.toThrow('Netz weg')
  })
})

describe('getInterviewHistory', () => {
  it('sendet Filter und liefert die Zeilen', async () => {
    post.mockResolvedValue({
      success: true,
      data: { count: 1, history: [{ agent_id: '4', response: 'R', prompt: 'P', timestamp: 't', platform: 'reddit' }] },
    })
    const rows = await getInterviewHistory('sim_1', { agentId: 4, platform: 'reddit', limit: 50 })
    expect(post).toHaveBeenCalledWith('/api/simulation/interview/history', {
      simulation_id: 'sim_1',
      agent_id: 4,
      platform: 'reddit',
      limit: 50,
    })
    expect(rows[0].agent_id).toBe(4)
  })

  it('wirft bei Vertragsbruch und reicht den Interceptor-Fehler durch', async () => {
    post.mockResolvedValueOnce({ success: true, data: { history: [{ agent_id: 1 }] } })
    await expect(getInterviewHistory('sim_1')).rejects.toThrow(/Vertragsbruch interview\/history/)
    post.mockRejectedValueOnce(new ApiError({ code: 'unknown_error', status: 200, message: 'kaputt' }))
    await expect(getInterviewHistory('sim_1')).rejects.toThrow('kaputt')
  })
})
