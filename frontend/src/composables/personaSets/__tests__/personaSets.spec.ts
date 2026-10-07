import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listPersonaSets: vi.fn(),
  getPersonaSet: vi.fn(),
  createPersonaSet: vi.fn(),
  updatePersonaSet: vi.fn(),
  deletePersonaSet: vi.fn(),
  duplicatePersonaSet: vi.fn(),
  getPersonaSetQuality: vi.fn(),
  addPersonaSetEntry: vi.fn(),
  updatePersonaSetEntry: vi.fn(),
  deletePersonaSetEntry: vi.fn(),
  deletePersonaSetEntries: vi.fn(),
}))

vi.mock('@/api/personaSets', async () => {
  const actual = await vi.importActual<typeof import('@/api/personaSets')>('@/api/personaSets')
  return { ...actual, ...api }
})

import { PersonaSetConflictError, PersonaSetLockedError } from '@/api/personaSets'
import { usePersonaSet } from '../usePersonaSet'
import { usePersonaSets } from '../usePersonaSets'

const TS = '2026-10-07T10:00:00'
const summary = (id: string) => ({
  id, name: id, description: '', graph_id: null, project_id: null, entry_count: 0,
  locked: false, locked_at: null, usage_count: 0, created_at: TS, updated_at: TS, schema_version: 1 as const,
})
const entry = (id: string) => ({
  entry_id: id, origin: 'manual' as const, source_entity_uuid: null, created_at: TS, updated_at: TS,
  profile: {
    username: id, name: id, bio: '', persona: '', age: null, gender: null, mbti: null, country: null,
    profession: null, interested_topics: [], source_entity_type: null, persona_kind: 'individual' as const,
    language: null, activity_level: null, time_zone: null, location: null, verified: false,
  },
})
const record = (entries = [entry('e1'), entry('e2')], locked_at: string | null = null) => ({
  id: 's1', name: 'Satz', description: '', graph_id: null, project_id: null, entries,
  locked_at, used_by_simulation_ids: locked_at ? ['sim_1'] : [], created_at: TS, updated_at: TS, schema_version: 1 as const,
})

beforeEach(() => {
  for (const f of Object.values(api)) f.mockReset()
})

describe('usePersonaSets', () => {
  it('lädt die Liste und meldet den Leerzustand erst nach dem Laden', async () => {
    api.listPersonaSets.mockResolvedValue({ count: 0, sets: [] })
    const s = usePersonaSets()
    expect(s.isEmpty.value).toBe(false)
    await s.reload()
    expect(s.isEmpty.value).toBe(true)
  })

  it('führt einen Ladefehler sichtbar', async () => {
    api.listPersonaSets.mockRejectedValue(new Error('offline'))
    const s = usePersonaSets()
    await s.reload()
    expect(s.error.value).toBe('offline')
    expect(s.isEmpty.value).toBe(false)
  })

  it('legt an, dupliziert und löscht; danach wird neu geladen', async () => {
    api.listPersonaSets.mockResolvedValue({ count: 1, sets: [summary('s1')] })
    api.createPersonaSet.mockResolvedValue(record())
    api.duplicatePersonaSet.mockResolvedValue(record())
    api.deletePersonaSet.mockResolvedValue({ removed: 's1' })
    const s = usePersonaSets()
    expect(await s.create({ name: 'A' })).not.toBeNull()
    expect(await s.duplicate('s1', 'Kopie')).not.toBeNull()
    expect(await s.remove('s1')).toBe(true)
    expect(api.listPersonaSets).toHaveBeenCalledTimes(3)
    expect(s.sets.value).toHaveLength(1)
  })

  it('meldet einen Aktionsfehler samt Sperrzustand und lädt nicht neu', async () => {
    api.deletePersonaSet.mockRejectedValue(new PersonaSetLockedError('gesperrt'))
    const s = usePersonaSets()
    expect(await s.remove('s1')).toBe(false)
    expect(s.actionError.value).toBe('gesperrt')
    expect(s.lockedError.value).toBe(true)
    expect(api.listPersonaSets).not.toHaveBeenCalled()
  })
})

describe('usePersonaSet', () => {
  it('lädt den Satz und leitet isLocked aus locked_at ab', async () => {
    api.getPersonaSet.mockResolvedValue(record([], '2026-10-07T11:00:00'))
    const s = usePersonaSet('s1')
    expect(s.isLocked.value).toBe(false)
    await s.load()
    expect(s.isLocked.value).toBe(true)
  })

  it('führt einen Ladefehler sichtbar und verwirft den Satz', async () => {
    api.getPersonaSet.mockRejectedValue(new Error('404'))
    const s = usePersonaSet('s1')
    await s.load()
    expect(s.error.value).toBe('404')
    expect(s.record.value).toBeNull()
  })

  it('legt Einträge an, ändert und löscht sie (einzeln und mehrfach)', async () => {
    api.getPersonaSet.mockResolvedValue(record())
    const s = usePersonaSet(() => 's1')
    await s.load()

    api.addPersonaSetEntry.mockResolvedValue(entry('e3'))
    await s.addEntry({ origin: 'manual', profile: { username: 'e3', name: 'e3' } })
    expect(s.entries.value.map((e) => e.entry_id)).toEqual(['e1', 'e2', 'e3'])

    api.updatePersonaSetEntry.mockResolvedValue({ ...entry('e2'), origin: 'fallback' as const })
    await s.updateEntry('e2', { origin: 'fallback' })
    expect(s.entries.value[1].origin).toBe('fallback')

    api.deletePersonaSetEntry.mockResolvedValue({ removed_entry_ids: ['e1'], set: summary('s1') })
    expect(await s.deleteEntry('e1')).toBe(true)
    api.deletePersonaSetEntries.mockResolvedValue({ removed_entry_ids: ['e2', 'e3'], set: summary('s1') })
    expect(await s.deleteEntries(['e2', 'e3'])).toBe(true)
    expect(s.entries.value).toEqual([])
  })

  it('Mehrfachlöschen ist alles oder nichts: bei Fehler bleibt die Liste', async () => {
    api.getPersonaSet.mockResolvedValue(record())
    const s = usePersonaSet('s1')
    await s.load()
    api.deletePersonaSetEntries.mockRejectedValue(new Error('unbekannte Kennung'))
    expect(await s.deleteEntries(['e1', 'zz'])).toBe(false)
    expect(s.entries.value).toHaveLength(2)
    expect(s.actionError.value).toBe('unbekannte Kennung')
  })

  it('unterscheidet Konflikt (409 conflict) vom Sperrfehler', async () => {
    api.getPersonaSet.mockResolvedValue(record())
    const s = usePersonaSet('s1')
    await s.load()
    api.addPersonaSetEntry.mockRejectedValue(new PersonaSetConflictError('username doppelt'))
    await s.addEntry({ origin: 'manual', profile: { username: 'e1', name: 'x' } })
    expect(s.conflictError.value).toBe(true)
    expect(s.isLocked.value).toBe(false)
  })

  it('wird bei 409 persona_set_locked gesperrt, lädt neu und behält die Meldung', async () => {
    api.getPersonaSet.mockResolvedValue(record())
    const s = usePersonaSet('s1')
    await s.load()
    api.updatePersonaSetEntry.mockRejectedValue(new PersonaSetLockedError('gesperrt'))
    await s.updateEntry('e1', { origin: 'graph' })
    expect(s.isLocked.value).toBe(true)
    expect(s.conflictError.value).toBe(false)
    expect(s.actionError.value).toBe('gesperrt')
    expect(api.getPersonaSet).toHaveBeenCalledTimes(2)
  })

  it('lädt die Qualität und führt deren Fehler getrennt', async () => {
    const s = usePersonaSet('s1')
    api.getPersonaSetQuality.mockResolvedValueOnce({
      set_id: 's1',
      summary: { total: 0, role_diversity: 0, mbti_diversity: 0, distinct_roles: [], distinct_mbti: [] },
      global_issues: [],
      personas: [],
    })
    await s.loadQuality()
    expect(s.quality.value?.set_id).toBe('s1')
    api.getPersonaSetQuality.mockRejectedValueOnce(new Error('q kaputt'))
    await s.loadQuality()
    expect(s.quality.value).toBeNull()
    expect(s.qualityError.value).toBe('q kaputt')
  })

  it('Name/Beschreibung ändern bleibt bei gesperrtem Satz möglich', async () => {
    api.getPersonaSet.mockResolvedValue(record([], '2026-10-07T11:00:00'))
    const s = usePersonaSet('s1')
    await s.load()
    api.updatePersonaSet.mockResolvedValue({ ...record([], '2026-10-07T11:00:00'), name: 'Neu' })
    expect(await s.updateMeta({ name: 'Neu' })).toBe(true)
    expect(s.record.value?.name).toBe('Neu')
  })
})
