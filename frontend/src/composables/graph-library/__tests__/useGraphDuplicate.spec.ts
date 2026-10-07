import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const api = vi.hoisted(() => ({
  duplicateGraph: vi.fn(),
  getGraphDuplicateRun: vi.fn(),
}))

vi.mock('@/api/graphEdit', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/graphEdit')>()
  return { ...actual, ...api }
})

import { GraphBuildInProgressError, GraphDuplicateUnavailableError } from '@/api/graphEdit'
import { useGraphDuplicate } from '../useGraphDuplicate'

const job = (over: Record<string, unknown> = {}) => ({
  run_id: 'run_dup_1',
  source_graph_id: 'g1',
  graph_id: 'g2',
  project_id: 'proj_kopie',
  status: 'pending',
  progress: 0,
  message: 'Kopie angelegt',
  error: null,
  ...over,
})

const run = (over: Record<string, unknown> = {}) => ({
  run_id: 'run_dup_1',
  run_type: 'graph_duplicate',
  status: 'processing',
  progress: 40,
  message: 'Dokumente werden kopiert',
  error: null,
  linked_ids: { source_graph_id: 'g1', graph_id: 'g2', project_id: 'proj_kopie' },
  ...over,
})

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useGraphDuplicate', () => {
  it('startet den Auftrag und zeigt Fortschritt statt einer fertigen Kopie', async () => {
    api.duplicateGraph.mockResolvedValue(job())
    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    expect(await dup.start('Kopie')).toBe(true)

    expect(api.duplicateGraph).toHaveBeenCalledWith('g1', { name: 'Kopie' })
    expect(dup.status.value).toBe('pending')
    expect(dup.running.value).toBe(true)
    expect(dup.completed.value).toBe(false)
    // Ohne terminalen Zustand gibt es keine Zieladresse.
    expect(dup.copyProjectId.value).toBeNull()
    dup.dispose()
  })

  it('verfolgt den Auftrag bis „completed“ und nennt dann das Zielprojekt', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job())
    api.getGraphDuplicateRun
      .mockResolvedValueOnce(run({ progress: 60 }))
      .mockResolvedValueOnce(run({ status: 'completed', progress: 100, message: 'Kopie ist fertig' }))

    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    await dup.start('Kopie')
    expect(dup.progress.value.percent).toBe(0)

    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(dup.progress.value.percent).toBe(60)
    expect(dup.completed.value).toBe(false)

    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(dup.status.value).toBe('completed')
    expect(dup.completed.value).toBe(true)
    expect(dup.copyProjectId.value).toBe('proj_kopie')
    expect(dup.running.value).toBe(false)
    dup.dispose()
  })

  it('pollt nach einem Endzustand nicht weiter', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job({ status: 'completed', progress: 100 }))
    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    await dup.start('Kopie')

    await vi.advanceTimersByTimeAsync(50)
    expect(api.getGraphDuplicateRun).not.toHaveBeenCalled()
    expect(dup.copyProjectId.value).toBe('proj_kopie')
    dup.dispose()
  })

  it('ein fehlgeschlagener Auftrag endet ohne Zielprojekt', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job())
    api.getGraphDuplicateRun.mockResolvedValue(
      run({ status: 'failed', progress: 30, message: 'Kopie abgebrochen', error: 'Zielprobot' }),
    )
    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    await dup.start('Kopie')
    await vi.advanceTimersByTimeAsync(10)
    await flush()

    expect(dup.failed.value).toBe(true)
    expect(dup.copyProjectId.value).toBeNull()
    dup.dispose()
  })

  it('ein Lesefehler beendet den Auftrag nicht, bleibt aber sichtbar', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job())
    api.getGraphDuplicateRun
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(run({ status: 'completed', progress: 100 }))

    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    await dup.start('Kopie')
    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(dup.error.value).not.toBeNull()
    expect(dup.running.value).toBe(true)

    await vi.advanceTimersByTimeAsync(10)
    await flush()
    expect(dup.completed.value).toBe(true)
    dup.dispose()
  })

  it('unterscheidet 409 Build läuft und 503 Kopierpfad', async () => {
    api.duplicateGraph.mockRejectedValueOnce(new GraphBuildInProgressError('wird gebaut'))
    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    expect(await dup.start('Kopie')).toBe(false)
    expect(dup.error.value?.kind).toBe('build_running')
    expect(dup.status.value).toBeNull()
    expect(dup.job.value).toBeNull()

    api.duplicateGraph.mockRejectedValueOnce(new GraphDuplicateUnavailableError('Dienst aus'))
    expect(await dup.start('Kopie')).toBe(false)
    expect(dup.error.value?.kind).toBe('unavailable')
    dup.dispose()
  })

  it('startet keinen zweiten Auftrag, während der erste läuft', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job())
    const dup = useGraphDuplicate('g1', { pollMs: 10 })
    expect(await dup.start('Kopie')).toBe(true)
    expect(await dup.start('Kopie 2')).toBe(false)
    expect(api.duplicateGraph).toHaveBeenCalledTimes(1)
    dup.dispose()
  })

  it('ohne graph_id startet nichts und meldet das', async () => {
    const dup = useGraphDuplicate(null, { pollMs: 10 })
    expect(await dup.start('Kopie')).toBe(false)
    expect(dup.error.value).not.toBeNull()
    expect(api.duplicateGraph).not.toHaveBeenCalled()
  })

  it('folgt einem Wechsel der graph_id', async () => {
    const graphId = ref<string | null>('g1')
    api.duplicateGraph.mockResolvedValue(job())
    const dup = useGraphDuplicate(graphId, { pollMs: 10 })
    await dup.start('Kopie')
    graphId.value = 'g9'
    await flush()
    expect(await dup.start('Kopie')).toBe(true)
    expect(api.duplicateGraph).toHaveBeenLastCalledWith('g9', { name: 'Kopie' })
    dup.dispose()
  })

  it('hört beim Verlassen der Ansicht mit dem Pollen auf', async () => {
    vi.useFakeTimers()
    api.duplicateGraph.mockResolvedValue(job())
    const scope = effectScope()
    const dup = scope.run(() => useGraphDuplicate('g1', { pollMs: 10 }))!
    await dup.start('Kopie')

    scope.stop()
    await vi.advanceTimersByTimeAsync(50)
    // Ohne Konsumenten läuft kein Timer weiter.
    expect(api.getGraphDuplicateRun).not.toHaveBeenCalled()
  })
})
