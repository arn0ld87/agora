/**
 * Tests für useApiAuth — Composable für transparente Ticket-Auth mit Auto-Refresh.
 *
 * Smoke-Fix Welle 2, Slice 03 (P1-Befund #4).
 *
 * Getestete Contracts:
 * 1. fetchTicket holt initialen Ticket und cacht ihn (kein Doppel-Fetch).
 * 2. withFreshTicket holt Ticket und ruft fn auf.
 * 3. withFreshTicket refresht bei 401 und retried einmal.
 * 4. withFreshTicket propagiert zweiten 401.
 * 5. fetchTicket gibt gecachtes Ticket zurück (kein zweiter POST).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useApiAuth } from '../useApiAuth'

// ---------------------------------------------------------------------------
// Mock für service (Axios-Instanz aus api/index)
// ---------------------------------------------------------------------------

const mockPost = vi.fn()

vi.mock('../../api/index', () => ({
  default: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/** Erzeugt eine erfolgreiche POST /api/auth/ticket Antwort. */
function makeTicketResponse(ticket = 'v1.test-ticket', expOffsetS = 60) {
  return {
    data: {
      ticket,
      exp: Math.floor(Date.now() / 1000) + expOffsetS,
      scope: 'sse:sim_test',
    },
  }
}

/** Erzeugt einen 401-Fehler, wie Axios ihn wirft. */
function make401Error() {
  return Object.assign(new Error('Unauthorized'), { response: { status: 401 } })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useApiAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useApiAuth._clearCache()
  })

  afterEach(() => {
    useApiAuth._clearCache()
  })

  // -------------------------------------------------------------------------
  // 1. fetchTicket: initialer Fetch + Cache
  // -------------------------------------------------------------------------

  it('fetchTicket holt initialen Ticket via POST /api/auth/ticket', async () => {
    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.initial'))

    const ticket = await useApiAuth.fetchTicket('sse:sim_123')

    expect(mockPost).toHaveBeenCalledOnce()
    expect(mockPost).toHaveBeenCalledWith('/api/auth/ticket', { scope: 'sse:sim_123', ttl_seconds: 60 })
    expect(ticket).toBe('v1.initial')
  })

  it('fetchTicket gibt gecachtes Ticket zurück ohne zweiten POST', async () => {
    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.cached'))

    const first = await useApiAuth.fetchTicket('sse:sim_cached')
    const second = await useApiAuth.fetchTicket('sse:sim_cached')

    expect(mockPost).toHaveBeenCalledOnce()
    expect(first).toBe('v1.cached')
    expect(second).toBe('v1.cached')
  })

  it('fetchTicket holt neues Ticket nach _clearCache', async () => {
    mockPost
      .mockResolvedValueOnce(makeTicketResponse('v1.first'))
      .mockResolvedValueOnce(makeTicketResponse('v1.second'))

    await useApiAuth.fetchTicket('sse:sim_refetch')
    useApiAuth._clearCache('sse:sim_refetch')
    const second = await useApiAuth.fetchTicket('sse:sim_refetch')

    expect(mockPost).toHaveBeenCalledTimes(2)
    expect(second).toBe('v1.second')
  })

  // -------------------------------------------------------------------------
  // 2. withFreshTicket: happy path
  // -------------------------------------------------------------------------

  it('withFreshTicket holt initialen Ticket und ruft fn auf', async () => {
    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.fresh'))

    const fn = vi.fn().mockResolvedValue('result-value')
    const result = await useApiAuth.withFreshTicket('sse:sim_happy', fn)

    expect(mockPost).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith('v1.fresh')
    expect(result).toBe('result-value')
  })

  // -------------------------------------------------------------------------
  // 3. withFreshTicket: Refresh bei 401, einmaliger Retry
  // -------------------------------------------------------------------------

  it('withFreshTicket refresht bei 401 und retried einmal', async () => {
    // Zwei separate Scopes, damit kein Cache-Konflikt mit anderen Tests.
    const scope = 'sse:sim_retry_once'

    mockPost
      .mockResolvedValueOnce(makeTicketResponse('v1.old-ticket'))   // initialer Fetch
      .mockResolvedValueOnce(makeTicketResponse('v1.new-ticket'))   // Refresh nach 401

    const fn = vi
      .fn()
      .mockRejectedValueOnce(make401Error())      // erstes fn(): 401
      .mockResolvedValueOnce('retry-result')       // zweites fn(): Erfolg

    const result = await useApiAuth.withFreshTicket(scope, fn)

    // Zwei POST-Calls: einer initial, einer für Refresh
    expect(mockPost).toHaveBeenCalledTimes(2)
    // fn zweimal aufgerufen: einmal mit altem, einmal mit neuem Ticket
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn).toHaveBeenNthCalledWith(1, 'v1.old-ticket')
    expect(fn).toHaveBeenNthCalledWith(2, 'v1.new-ticket')
    expect(result).toBe('retry-result')
  })

  // -------------------------------------------------------------------------
  // 4. withFreshTicket: zweiter 401 wird propagiert
  // -------------------------------------------------------------------------

  it('withFreshTicket propagiert zweiten 401', async () => {
    const scope = 'sse:sim_double_401'

    mockPost
      .mockResolvedValueOnce(makeTicketResponse('v1.first'))
      .mockResolvedValueOnce(makeTicketResponse('v1.second'))

    const error401 = make401Error()
    const fn = vi
      .fn()
      .mockRejectedValueOnce(error401)    // erstes fn(): 401
      .mockRejectedValueOnce(error401)    // zweites fn(): 401 wieder

    await expect(useApiAuth.withFreshTicket(scope, fn)).rejects.toThrow('Unauthorized')

    expect(fn).toHaveBeenCalledTimes(2)
    expect(mockPost).toHaveBeenCalledTimes(2)
  })

  // -------------------------------------------------------------------------
  // 5. withFreshTicket: Nicht-401-Fehler werden direkt propagiert (kein Retry)
  // -------------------------------------------------------------------------

  it('withFreshTicket propagiert Nicht-401-Fehler ohne Retry', async () => {
    const scope = 'sse:sim_500'

    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.ok'))

    const fn = vi.fn().mockRejectedValueOnce(new Error('Internal Server Error'))

    await expect(useApiAuth.withFreshTicket(scope, fn)).rejects.toThrow('Internal Server Error')

    // Kein Refresh-Fetch
    expect(mockPost).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledOnce()
  })

  // -------------------------------------------------------------------------
  // 6. In-Flight-Deduplizierung: 2× parallel fetchTicket(scope) → 1× POST
  //    Copilot-Followup PR #466: concurrent callers für denselben Scope
  //    dürfen keinen zweiten POST auslösen.
  // -------------------------------------------------------------------------

  it('2× parallele fetchTicket(scope) resultieren in genau 1× POST /api/auth/ticket', async () => {
    const scope = 'sse:sim_parallel'

    // mockPost resolved nur einmal — wenn ein zweiter POST käme, würde er undefined zurückgeben
    // und fetchTicket mit „no ticket"-Fehler abbrechen.
    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.shared'))

    const [t1, t2] = await Promise.all([
      useApiAuth.fetchTicket(scope),
      useApiAuth.fetchTicket(scope),
    ])

    expect(mockPost).toHaveBeenCalledOnce()
    expect(t1).toBe('v1.shared')
    expect(t2).toBe('v1.shared')
  })

  // -------------------------------------------------------------------------
  // 7. ttlSeconds wird an POST /api/auth/ticket weitergegeben
  //    Copilot-Followup PR #466 (stream.ts:49).
  // -------------------------------------------------------------------------

  it('fetchTicket sendet ttlSeconds als ttl_seconds im POST-Body', async () => {
    mockPost.mockResolvedValueOnce(makeTicketResponse('v1.custom-ttl'))

    await useApiAuth.fetchTicket('sse:sim_ttl', 120)

    expect(mockPost).toHaveBeenCalledWith('/api/auth/ticket', { scope: 'sse:sim_ttl', ttl_seconds: 120 })
  })
})
