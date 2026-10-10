/**
 * UAT-011 — „Graphabschluss zeigt falsche Zähler" (Restteil: Retry).
 *
 * getGraphData war der einzige Graph-Endpoint ohne requestWithRetry: der
 * /data-Abruf nach dem Phase-2-Wechsel hatte genau einen Versuch. Ein
 * kurzzeitiger Transport-/Serverfehler in diesem Fenster liess graphData
 * null bleiben — die Abschlusskarte zeigte 0/0, obwohl Neo4j längst zählte.
 *
 * Fix-Vertrag: GET ist idempotent; transport-/serverseitige Fehler
 * (timeout, network, 5xx) werden begrenzt retryiert (3 Versuche, 1/2/4s
 * Backoff). Semantische Ablehnungen (success:false-Hülle, 4xx) bubbeln
 * unverzögert.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

const serviceMock = vi.hoisted(() => vi.fn())

vi.mock('../index', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../index')>()
  return { ...actual, default: serviceMock }
})

import { getGraphData } from '../graph'
import { ApiError } from '../envelope'

afterEach(() => {
  vi.useRealTimers()
  serviceMock.mockReset()
})

describe('getGraphData — begrenzter Retry (UAT-011)', () => {
  it('retryiert einen transportseitigen Fehlschlag und liefert beim zweiten Versuch', async () => {
    vi.useFakeTimers()
    serviceMock
      .mockRejectedValueOnce(
        new ApiError({ code: 'service_unavailable', status: 0, message: 'Network Error' }),
      )
      .mockResolvedValueOnce({
        success: true,
        data: { graph_id: 'g1', nodes: [], edges: [], node_count: 12, edge_count: 15 },
      })

    const promise = getGraphData('g1')
    // Erster Retry-Backoff (1000 ms) abwarten.
    await vi.advanceTimersByTimeAsync(1000)
    const response = await promise

    expect(response.success).toBe(true)
    expect(response.data.node_count).toBe(12)
    expect(serviceMock).toHaveBeenCalledTimes(2)
    expect(serviceMock.mock.calls[0][0]).toEqual({ url: '/api/graph/data/g1', method: 'get' })
  })

  it('retryiert nicht bei einer 4xx-Ablehnung', async () => {
    serviceMock.mockRejectedValueOnce(
      new ApiError({ code: 'not_found', status: 404, message: 'Graph nicht gefunden' }),
    )

    await expect(getGraphData('g1')).rejects.toMatchObject({ code: 'not_found' })
    expect(serviceMock).toHaveBeenCalledTimes(1)
  })

  it('gibt nach der begrenzten Retry-Kette (3 Versuche) auf', async () => {
    vi.useFakeTimers()
    serviceMock.mockRejectedValue(
      new ApiError({ code: 'timeout', status: 0, message: 'Zeitüberschreitung' }),
    )

    const promise = getGraphData('g1').catch((caughtError) => caughtError)
    // Gesamt-Backoff 1s + 2s überspringen; kein Versuch mehr nach dem 3.
    await vi.advanceTimersByTimeAsync(9000)
    const caughtError = await promise

    expect(caughtError).toMatchObject({ code: 'timeout' })
    expect(serviceMock).toHaveBeenCalledTimes(3)
  })
})