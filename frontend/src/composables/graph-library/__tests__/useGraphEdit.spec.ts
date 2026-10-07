import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const api = vi.hoisted(() => ({
  getGraphLock: vi.fn(),
  createEntity: vi.fn(),
  updateEntity: vi.fn(),
  deleteEntity: vi.fn(),
  mergeEntities: vi.fn(),
  createRelation: vi.fn(),
  updateRelation: vi.fn(),
  deleteRelation: vi.fn(),
}))

vi.mock('@/api/graphEdit', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/graphEdit')>()
  return { ...actual, ...api }
})

import { EmbeddingMigrationRunningError, GraphEditConflictError, GraphEditEmbeddingFailedError, GraphLockedError } from '@/api/graphEdit'
import { useGraphEdit } from '../useGraphEdit'
import { useGraphLock } from '../useGraphLock'

const UUID_A = '11111111-1111-4111-8111-111111111111'
const sim = { simulation_id: 'sim_1', status: 'running', project_id: 'p', branch_name: null }

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

describe('useGraphLock', () => {
  it('lädt den Zustand und unterscheidet bearbeitbar, gesperrt und Fehler', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: 'g1', locked: false, used_by: [] })
    const lock = useGraphLock('g1')
    expect(lock.status.value).toBe('unknown')
    await flush()
    expect(lock.status.value).toBe('editable')
    expect(lock.editable.value).toBe(true)

    api.getGraphLock.mockResolvedValue({ graph_id: 'g1', locked: true, used_by: [sim] })
    await lock.reload()
    expect(lock.locked.value).toBe(true)
    expect(lock.usedBy.value).toEqual([sim])

    api.getGraphLock.mockRejectedValue(new Error('offline'))
    await lock.reload()
    expect(lock.status.value).toBe('error')
    expect(lock.editable.value).toBe(false)
    expect(lock.error.value).toBe('offline')
  })

  it('ohne graph_id bleibt der Zustand unbekannt und es gibt keine Anfrage', async () => {
    const lock = useGraphLock(null)
    await flush()
    expect(lock.status.value).toBe('unknown')
    expect(api.getGraphLock).not.toHaveBeenCalled()
  })

  it('lädt neu, wenn sich die graph_id ändert, und verwirft veraltete Antworten', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: 'g1', locked: false, used_by: [] })
    const id = ref<string | null>('g1')
    const lock = useGraphLock(id)
    await flush()
    api.getGraphLock.mockResolvedValue({ graph_id: 'g2', locked: true, used_by: [sim] })
    id.value = 'g2'
    await flush()
    expect(api.getGraphLock).toHaveBeenLastCalledWith('g2')
    expect(lock.locked.value).toBe(true)
  })
})

describe('useGraphEdit', () => {
  it('liefert das geänderte Element und setzt busy zurück', async () => {
    const node = { uuid: UUID_A, name: 'A' }
    api.updateEntity.mockResolvedValue(node)
    const edit = useGraphEdit('g1')
    const out = await edit.updateEntity(UUID_A, { name: 'A' })
    expect(out).toBe(node)
    expect(api.updateEntity).toHaveBeenCalledWith('g1', UUID_A, { name: 'A' })
    expect(edit.busy.value).toBe(false)
    expect(edit.error.value).toBeNull()
  })

  it('409 graph_locked setzt den Sperrzustand sichtbar', async () => {
    api.getGraphLock.mockResolvedValue({ graph_id: 'g1', locked: false, used_by: [] })
    const lock = useGraphLock('g1')
    await flush()
    api.deleteEntity.mockRejectedValue(new GraphLockedError('gesperrt', [sim]))
    const edit = useGraphEdit('g1', lock)
    expect(await edit.deleteEntity(UUID_A)).toBeNull()
    expect(edit.error.value?.kind).toBe('locked')
    expect(lock.locked.value).toBe(true)
    expect(lock.usedBy.value).toEqual([sim])
  })

  it('ordnet Konflikt, Migration und Einbettungsfehler getrennt ein', async () => {
    const edit = useGraphEdit('g1')
    api.createEntity.mockRejectedValueOnce(new GraphEditConflictError('doppelt'))
    await edit.createEntity({ name: 'A', entity_type: 'T' })
    expect(edit.error.value).toMatchObject({ kind: 'conflict', message: 'doppelt' })

    api.createEntity.mockRejectedValueOnce(new EmbeddingMigrationRunningError('Migration'))
    await edit.createEntity({ name: 'A', entity_type: 'T' })
    expect(edit.error.value?.kind).toBe('migration_running')

    api.createEntity.mockRejectedValueOnce(new GraphEditEmbeddingFailedError('Embedding'))
    await edit.createEntity({ name: 'A', entity_type: 'T' })
    expect(edit.error.value?.kind).toBe('embedding_failed')

    api.createEntity.mockRejectedValueOnce(new Error('sonst'))
    await edit.createEntity({ name: 'A', entity_type: 'T' })
    expect(edit.error.value?.kind).toBe('other')

    api.createEntity.mockResolvedValueOnce({ uuid: UUID_A, name: 'A' })
    await edit.createEntity({ name: 'A', entity_type: 'T' })
    expect(edit.error.value).toBeNull()
  })

  it('ohne graph_id wird nichts gesendet', async () => {
    const edit = useGraphEdit(null)
    expect(await edit.deleteRelation(UUID_A)).toBeNull()
    expect(api.deleteRelation).not.toHaveBeenCalled()
    expect(edit.error.value?.kind).toBe('other')
  })
})
