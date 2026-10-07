import { beforeEach, describe, expect, it, vi } from 'vitest'

const get = vi.hoisted(() => vi.fn())
const post = vi.hoisted(() => vi.fn())
const patch = vi.hoisted(() => vi.fn())
const del = vi.hoisted(() => vi.fn())
vi.mock('../index', () => ({ default: { get, post, patch, delete: del } }))

import { ApiError } from '../envelope'
import {
  PersonaSetConflictError,
  PersonaSetLockedError,
  addPersonaSetEntry,
  createPersonaSet,
  deletePersonaSet,
  deletePersonaSetEntries,
  deletePersonaSetEntry,
  duplicatePersonaSet,
  getPersonaSet,
  getPersonaSetQuality,
  isPersonaSetConflictError,
  isPersonaSetLockedError,
  listPersonaSets,
  updatePersonaSet,
  updatePersonaSetEntry,
} from '../personaSets'

const TS = '2026-10-07T10:00:00'
const SUMMARY = {
  id: 's1', name: 'Satz', description: '', graph_id: null, project_id: null, entry_count: 0,
  locked: false, locked_at: null, usage_count: 0, created_at: TS, updated_at: TS, schema_version: 1,
}
const RECORD = {
  id: 's1', name: 'Satz', description: '', graph_id: null, project_id: null, entries: [],
  locked_at: null, used_by_simulation_ids: [], created_at: TS, updated_at: TS, schema_version: 1,
}
const ENTRY = {
  entry_id: 'e1', origin: 'manual', source_entity_uuid: null, created_at: TS, updated_at: TS,
  profile: {
    username: 'a', name: 'A', bio: '', persona: '', age: null, gender: null, mbti: null, country: null,
    profession: null, interested_topics: [], source_entity_type: null, persona_kind: 'individual',
    language: null, activity_level: null, time_zone: null, location: null, verified: false,
  },
}
const ok = (data: unknown) => ({ success: true, data })
const apiError = (status: number, code: string) =>
  new ApiError({ code, status, message: `Fehler ${code}` })

beforeEach(() => {
  for (const m of [get, post, patch, del]) m.mockReset()
})

describe('api/personaSets', () => {
  it('list und get parsen durch Zod', async () => {
    get.mockResolvedValueOnce(ok({ count: 1, sets: [SUMMARY] }))
    expect((await listPersonaSets()).sets[0].id).toBe('s1')
    expect(get).toHaveBeenCalledWith('/api/persona-sets')
    get.mockResolvedValueOnce(ok(RECORD))
    expect((await getPersonaSet('s 1')).id).toBe('s1')
    expect(get).toHaveBeenLastCalledWith('/api/persona-sets/s%201')
  })

  it('wirft einen Vertragsbruch bei unbekannter Antwortform', async () => {
    get.mockResolvedValueOnce(ok({ count: 1, sets: [{ ...SUMMARY, extra: 1 }] }))
    await expect(listPersonaSets()).rejects.toThrow(/Vertragsbruch/)
    get.mockResolvedValueOnce({ success: false, error: 'kaputt' })
    await expect(getPersonaSet('s1')).rejects.toThrow('kaputt')
  })

  it('create, update, duplicate, delete senden die Vertragsform', async () => {
    post.mockResolvedValueOnce(ok(RECORD))
    await createPersonaSet({ name: ' Satz ' })
    expect(post).toHaveBeenLastCalledWith('/api/persona-sets', {
      name: 'Satz', description: '', graph_id: null, project_id: null,
    })
    patch.mockResolvedValueOnce(ok(RECORD))
    await updatePersonaSet('s1', { description: 'neu' })
    expect(patch).toHaveBeenLastCalledWith('/api/persona-sets/s1', { description: 'neu' })
    post.mockResolvedValueOnce(ok(RECORD))
    await duplicatePersonaSet('s1', { name: 'Kopie' })
    expect(post).toHaveBeenLastCalledWith('/api/persona-sets/s1/duplicate', { name: 'Kopie' })
    del.mockResolvedValueOnce(ok({ removed: 's1' }))
    expect((await deletePersonaSet('s1')).removed).toBe('s1')
  })

  it('lehnt eine ungültige Anfrage vor dem Senden ab', async () => {
    await expect(updatePersonaSet('s1', {})).rejects.toThrow()
    await expect(deletePersonaSetEntries('s1', [])).rejects.toThrow()
    expect(patch).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('Qualität und Einträge', async () => {
    get.mockResolvedValueOnce(
      ok({
        set_id: 's1',
        summary: { total: 0, role_diversity: 0, mbti_diversity: 0, distinct_roles: [], distinct_mbti: [] },
        global_issues: [],
        personas: [],
      }),
    )
    expect((await getPersonaSetQuality('s1')).set_id).toBe('s1')
    expect(get).toHaveBeenLastCalledWith('/api/persona-sets/s1/quality')

    post.mockResolvedValueOnce(ok(ENTRY))
    await addPersonaSetEntry('s1', { origin: 'manual', profile: { username: 'a', name: 'A' } })
    const body = post.mock.calls.at(-1)?.[1] as { profile: { persona_kind: string } }
    expect(post.mock.calls.at(-1)?.[0]).toBe('/api/persona-sets/s1/entries')
    expect(body.profile.persona_kind).toBe('individual')

    patch.mockResolvedValueOnce(ok(ENTRY))
    await updatePersonaSetEntry('s1', 'e1', { origin: 'fallback' })
    expect(patch).toHaveBeenLastCalledWith('/api/persona-sets/s1/entries/e1', { origin: 'fallback' })

    const del1 = ok({ removed_entry_ids: ['e1'], set: SUMMARY })
    del.mockResolvedValueOnce(del1)
    expect((await deletePersonaSetEntry('s1', 'e1')).removed_entry_ids).toEqual(['e1'])
    post.mockResolvedValueOnce(del1)
    await deletePersonaSetEntries('s1', ['e1', 'e2'])
    expect(post).toHaveBeenLastCalledWith('/api/persona-sets/s1/entries/delete', { entry_ids: ['e1', 'e2'] })
  })

  it('409 persona_set_locked und 409 conflict sind unterscheidbare Fehler', async () => {
    patch.mockRejectedValueOnce(apiError(409, 'persona_set_locked'))
    const locked = await updatePersonaSetEntry('s1', 'e1', { origin: 'graph' }).catch((e: unknown) => e)
    expect(locked).toBeInstanceOf(PersonaSetLockedError)
    expect(isPersonaSetLockedError(locked)).toBe(true)
    expect(isPersonaSetConflictError(locked)).toBe(false)

    post.mockRejectedValueOnce(apiError(409, 'conflict'))
    const conflict = await addPersonaSetEntry('s1', { origin: 'manual', profile: { username: 'a', name: 'A' } }).catch(
      (e: unknown) => e,
    )
    expect(conflict).toBeInstanceOf(PersonaSetConflictError)
    expect(isPersonaSetLockedError(conflict)).toBe(false)
  })

  it('andere Fehler bleiben ApiError', async () => {
    get.mockRejectedValueOnce(apiError(404, 'not_found'))
    const err = await getPersonaSet('x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('not_found')
  })
})
