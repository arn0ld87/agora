import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
const post = vi.hoisted(() => vi.fn())
const patch = vi.hoisted(() => vi.fn())
const del = vi.hoisted(() => vi.fn())
vi.mock('../index', () => ({ default: { get, post, patch, delete: del } }))

import { ApiError } from '../envelope'
import {
  EmbeddingMigrationRunningError,
  GraphBuildInProgressError,
  GraphDuplicateUnavailableError,
  GraphEditConflictError,
  GraphEditEmbeddingFailedError,
  GraphEditInputError,
  GraphLockedError,
  createEntity,
  createRelation,
  deleteEntity,
  deleteRelation,
  duplicateGraph,
  getGraphDuplicateRun,
  getGraphLock,
  mergeEntities,
  updateEntity,
  updateRelation,
} from '../graphEdit'

const UUID_A = '11111111-1111-4111-8111-111111111111'
const UUID_B = '22222222-2222-4222-8222-222222222222'
const UUID_REQ = '33333333-3333-4333-8333-333333333333'

const node = { uuid: UUID_A, name: 'Stadtrat' }
const edge = { uuid: UUID_B, name: 'LEITET', source_node_uuid: UUID_A, target_node_uuid: UUID_B }

beforeEach(() => {
  for (const fn of [get, post, patch, del]) fn.mockReset()
})

function apiError(status: number, code: string, body: Record<string, unknown> = {}) {
  return new ApiError({
    code,
    status,
    message: 'Meldung',
    originalResponse: { success: false, code, error: 'Meldung', ...body },
  })
}

describe('getGraphLock', () => {
  it('liest den Sperrzustand durch das Schema', async () => {
    get.mockResolvedValue({
      success: true,
      data: { graph_id: 'g1', locked: true, used_by: [{ simulation_id: 'sim_1', status: 'running' }] },
    })
    const lock = await getGraphLock('g1')
    expect(get).toHaveBeenCalledWith('/api/graph/g1/lock')
    expect(lock.locked).toBe(true)
    expect(lock.used_by[0].simulation_id).toBe('sim_1')
  })

  it('meldet einen Vertragsbruch statt still weiterzurendern', async () => {
    get.mockResolvedValue({ success: true, data: { graph_id: 'g1', locked: 'ja' } })
    await expect(getGraphLock('g1')).rejects.toThrow(/Vertragsbruch/)
  })
})

describe('Entitäten', () => {
  it('createEntity sendet eine client_request_id (UUID) und liefert die Ansicht', async () => {
    post.mockResolvedValue({ success: true, data: node })
    const out = await createEntity('g1', { name: ' Stadtrat ', entity_type: 'Organisation' })
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/graph/g1/entities')
    expect(body.client_request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(body).toMatchObject({ name: 'Stadtrat', entity_type: 'Organisation', summary: '', aliases: [] })
    expect(out.provenance.origin).toBeNull()
  })

  it('createEntity nutzt eine mitgegebene client_request_id (Wiederholung)', async () => {
    post.mockResolvedValue({ success: true, data: node })
    await createEntity('g1', { name: 'A', entity_type: 'T', client_request_id: UUID_REQ })
    expect(post.mock.calls[0][1].client_request_id).toBe(UUID_REQ)
  })

  it('weist ungültige Eingaben vor dem Senden ab', async () => {
    await expect(createEntity('g1', { name: '  ', entity_type: 'T' })).rejects.toBeInstanceOf(GraphEditInputError)
    await expect(updateEntity('g1', UUID_A, {})).rejects.toBeInstanceOf(GraphEditInputError)
    expect(post).not.toHaveBeenCalled()
    expect(patch).not.toHaveBeenCalled()
  })

  it('updateEntity, deleteEntity, mergeEntities', async () => {
    patch.mockResolvedValue({ success: true, data: node })
    expect((await updateEntity('g1', UUID_A, { summary: 'neu' })).uuid).toBe(UUID_A)
    expect(patch).toHaveBeenCalledWith(`/api/graph/g1/entities/${UUID_A}`, { summary: 'neu' })

    del.mockResolvedValue({ success: true, data: { uuid: UUID_A, removed_relation_count: 2 } })
    expect((await deleteEntity('g1', UUID_A)).removed_relation_count).toBe(2)
    expect(del).toHaveBeenCalledWith(`/api/graph/g1/entities/${UUID_A}`)

    post.mockResolvedValue({
      success: true,
      data: { target: node, merged_source_uuids: [UUID_B], rewired_relation_count: 1, dropped_relation_count: 0 },
    })
    const merged = await mergeEntities('g1', { target_uuid: UUID_A, source_uuids: [UUID_B] })
    expect(post).toHaveBeenLastCalledWith('/api/graph/g1/entities/merge', { target_uuid: UUID_A, source_uuids: [UUID_B] })
    expect(merged.merged_source_uuids).toEqual([UUID_B])
  })
})

describe('Beziehungen', () => {
  it('createRelation, updateRelation, deleteRelation', async () => {
    post.mockResolvedValue({ success: true, data: edge })
    await createRelation('g1', { source_uuid: UUID_A, target_uuid: UUID_B, name: 'LEITET', fact: 'A leitet B' })
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/graph/g1/relations')
    expect(body.client_request_id).toBeTruthy()

    patch.mockResolvedValue({ success: true, data: edge })
    await updateRelation('g1', UUID_B, { fact: 'neu' })
    expect(patch).toHaveBeenCalledWith(`/api/graph/g1/relations/${UUID_B}`, { fact: 'neu' })

    del.mockResolvedValue({ success: true, data: { uuid: UUID_B } })
    expect((await deleteRelation('g1', UUID_B)).uuid).toBe(UUID_B)
  })
})

describe('typisierte Fehler', () => {
  it('409 graph_locked trägt used_by', async () => {
    patch.mockRejectedValue(
      apiError(409, 'graph_locked', { used_by: [{ simulation_id: 'sim_9', status: 'running' }] }),
    )
    const err = await updateEntity('g1', UUID_A, { name: 'X' }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(GraphLockedError)
    expect((err as GraphLockedError).usedBy.map((u) => u.simulation_id)).toEqual(['sim_9'])
  })

  it('409 graph_locked ohne lesbares used_by ergibt eine leere Liste', async () => {
    del.mockRejectedValue(apiError(409, 'graph_locked', { used_by: 'kaputt' }))
    const err = await deleteEntity('g1', UUID_A).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(GraphLockedError)
    expect((err as GraphLockedError).usedBy).toEqual([])
  })

  it('409 graph_edit_conflict, 409 embedding_migration_running, 503', async () => {
    post.mockRejectedValueOnce(apiError(409, 'graph_edit_conflict'))
    expect(await createEntity('g1', { name: 'A', entity_type: 'T' }).catch((e: unknown) => e)).toBeInstanceOf(
      GraphEditConflictError,
    )
    post.mockRejectedValueOnce(apiError(409, 'embedding_migration_running'))
    expect(await createEntity('g1', { name: 'A', entity_type: 'T' }).catch((e: unknown) => e)).toBeInstanceOf(
      EmbeddingMigrationRunningError,
    )
    post.mockRejectedValueOnce(apiError(503, 'service_unavailable'))
    expect(await createEntity('g1', { name: 'A', entity_type: 'T' }).catch((e: unknown) => e)).toBeInstanceOf(
      GraphEditEmbeddingFailedError,
    )
  })

  it('Transportfehler ohne Status 503 bleiben unverändert', async () => {
    const offline = apiError(0, 'service_unavailable')
    post.mockRejectedValue(offline)
    expect(await createEntity('g1', { name: 'A', entity_type: 'T' }).catch((e: unknown) => e)).toBe(offline)
  })

  it('andere Fehler (404) bleiben ApiError', async () => {
    const nf = apiError(404, 'not_found')
    del.mockRejectedValue(nf)
    expect(await deleteRelation('g1', UUID_B).catch((e: unknown) => e)).toBe(nf)
  })
})

const job = {
  run_id: 'run_dup_1',
  source_graph_id: 'g1',
  graph_id: 'g2',
  project_id: 'proj_kopie',
  status: 'pending',
  progress: 0,
  message: 'Kopie angelegt',
  error: null,
}

describe('duplicateGraph', () => {
  it('legt einen Kopierauftrag an und liefert den Job, keine fertige Kopie', async () => {
    post.mockResolvedValue({ success: true, data: job })
    const out = await duplicateGraph('g1', { name: 'Kopie' })
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/api/graph/g1/duplicate')
    expect(body.client_request_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(body).toMatchObject({ name: 'Kopie' })
    // `completed` wäre eine Behauptung, die der Server noch nicht gedeckt hat.
    expect(out.status).toBe('pending')
    expect(out.graph_id).toBe('g2')
  })

  it('nutzt eine mitgegebene client_request_id (Wiederholung ergibt denselben Auftrag)', async () => {
    post.mockResolvedValue({ success: true, data: job })
    await duplicateGraph('g1', { name: 'Kopie', client_request_id: UUID_REQ })
    expect(post.mock.calls[0][1].client_request_id).toBe(UUID_REQ)
  })

  it('weist einen leeren Namen vor dem Senden ab', async () => {
    await expect(duplicateGraph('g1', { name: '   ' })).rejects.toBeInstanceOf(GraphEditInputError)
    expect(post).not.toHaveBeenCalled()
  })

  it('meldet einen Vertragsbruch der Antwort statt eine Kopie zu behaupten', async () => {
    post.mockResolvedValue({ success: true, data: { ...job, status: 'fast_fertig' } })
    await expect(duplicateGraph('g1', { name: 'Kopie' })).rejects.toThrow(/Vertragsbruch/)
  })

  it('409 graph_build_in_progress und 409 embedding_migration_running sind unterscheidbar', async () => {
    post.mockRejectedValueOnce(apiError(409, 'graph_build_in_progress'))
    expect(await duplicateGraph('g1', { name: 'Kopie' }).catch((e: unknown) => e)).toBeInstanceOf(
      GraphBuildInProgressError,
    )
    post.mockRejectedValueOnce(apiError(409, 'embedding_migration_running'))
    expect(await duplicateGraph('g1', { name: 'Kopie' }).catch((e: unknown) => e)).toBeInstanceOf(
      EmbeddingMigrationRunningError,
    )
  })

  it('503 heißt hier „Kopierpfad nicht verfügbar“, nicht „Einbettung fehlgeschlagen“', async () => {
    post.mockRejectedValue(apiError(503, 'service_unavailable'))
    const err = await duplicateGraph('g1', { name: 'Kopie' }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(GraphDuplicateUnavailableError)
    expect(err).not.toBeInstanceOf(GraphEditEmbeddingFailedError)
    expect((err as GraphDuplicateUnavailableError).status).toBe(503)
  })

  it('ein gesperrter Quellgraph ist kein Fehler: 409 graph_locked bleibt ApiError', async () => {
    // Duplizieren liest die Quelle nur und ist auch gesperrt erlaubt.
    const locked = apiError(409, 'graph_locked')
    post.mockRejectedValue(locked)
    expect(await duplicateGraph('g1', { name: 'Kopie' }).catch((e: unknown) => e)).toBe(locked)
  })

  it('404 bleibt ApiError', async () => {
    const nf = apiError(404, 'not_found')
    post.mockRejectedValue(nf)
    expect(await duplicateGraph('g1', { name: 'Kopie' }).catch((e: unknown) => e)).toBe(nf)
  })
})

describe('getGraphDuplicateRun', () => {
  it('liest den Auftrag aus der Run-Infrastruktur', async () => {
    get.mockResolvedValue({
      success: true,
      data: {
        run_id: 'run_dup_1',
        run_type: 'graph_duplicate',
        entity_id: 'proj_kopie',
        status: 'processing',
        progress: 42,
        message: 'Quelle wird gelesen',
        error: null,
        started_at: '2026-10-07T10:00:00',
        updated_at: '2026-10-07T10:00:05',
        linked_ids: { source_graph_id: 'g1', graph_id: 'g2', project_id: 'proj_kopie' },
      },
    })
    const run = await getGraphDuplicateRun('run_dup_1')
    expect(get).toHaveBeenCalledWith('/api/runs/run_dup_1')
    expect(run.status).toBe('processing')
    expect(run.progress).toBe(42)
    expect(run.linked_ids.project_id).toBe('proj_kopie')
  })

  it('meldet einen Vertragsbruch statt Stillstand zu zeigen', async () => {
    get.mockResolvedValue({ success: true, data: { run_id: 'run_dup_1', status: 'irgendwie' } })
    await expect(getGraphDuplicateRun('run_dup_1')).rejects.toThrow(/Vertragsbruch/)
  })

  it('ein fehlgeschlagener Auftrag behält seine Fehlermeldung', async () => {
    get.mockResolvedValue({
      success: true,
      data: {
        run_id: 'run_dup_1',
        status: 'failed',
        progress: 30,
        message: 'Kopie abgebrochen',
        error: 'Zielprojekt ließ sich nicht anlegen',
        linked_ids: { source_graph_id: 'g1', graph_id: 'g2', project_id: 'proj_kopie' },
      },
    })
    const run = await getGraphDuplicateRun('run_dup_1')
    expect(run.status).toBe('failed')
    expect(run.error).toBe('Zielprojekt ließ sich nicht anlegen')
  })
})
