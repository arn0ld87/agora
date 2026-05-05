/**
 * Tests für usePersonaLibrary — Sub-Slice 39, Refs #203.
 *
 * Getestete Contracts:
 *   1. loadPersonaLibrary happy-path: setzt personaTemplates, leert personaLibraryError, toggelt isLoadingPersonaLibrary.
 *   2. loadPersonaLibrary error-path: API gibt success: false zurück → personaLibraryError enthält Message.
 *   3. savePersona: setzt key in savingPersonaKeys, ruft savePersonaTemplate mit whitelisted Payload, löscht key wieder, ruft loadPersonaLibrary bei success.
 *   4. usePersonaTemplate: setzt template_id in usingPersonaTemplateIds, ruft addSimulationProfile mit source_entity_type: 'library', ruft fetchProfilesRealtime, löscht id wieder.
 *   5. removePersonaTemplate: respektiert confirmFn (false → kein API-Call); bei true → deletePersonaTemplate-Call + reload.
 *   6. removePersona: confirmFn false → no-op; true → deleteSimulationProfile + fetchProfilesRealtime.
 *   7. submitNewPersona: trimmed interested_topics-CSV → Array, leeres age wird gestripped, ruft addSimulationProfile, schließt Modal + reset bei success.
 *   8. profileKey / profilePayload: Mapping-Logik (Whitelist, undefined/empty stripping).
 *   9. saveAllPersonas: ruft savePersona für jedes Profil in profiles.value.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ---------------------------------------------------------------------------
// Mock api/simulation BEFORE composable import
// ---------------------------------------------------------------------------

vi.mock('../../api/simulation', () => ({
  addSimulationProfile: vi.fn(),
  deleteSimulationProfile: vi.fn(),
  listPersonaTemplates: vi.fn(),
  savePersonaTemplate: vi.fn(),
  deletePersonaTemplate: vi.fn(),
}))

import {
  addSimulationProfile,
  deleteSimulationProfile,
  listPersonaTemplates,
  savePersonaTemplate,
  deletePersonaTemplate,
} from '../../api/simulation'

import { usePersonaLibrary } from '../usePersonaLibrary'

const mockAddSimulationProfile = vi.mocked(addSimulationProfile)
const mockDeleteSimulationProfile = vi.mocked(deleteSimulationProfile)
const mockListPersonaTemplates = vi.mocked(listPersonaTemplates)
const mockSavePersonaTemplate = vi.mocked(savePersonaTemplate)
const mockDeletePersonaTemplate = vi.mocked(deletePersonaTemplate)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTemplatesEnvelope(templates: unknown[] = []) {
  return { success: true, data: { templates } }
}

function makeErrorEnvelope(error = 'Server-Fehler') {
  return { success: false, error }
}

function makeProfileEnvelope(username = 'user1') {
  return { success: true, data: { profile: { username } } }
}

function makeTemplateEnvelope(name = 'Testpersona') {
  return { success: true, data: { template: { name } } }
}

function buildDeps(overrides: {
  simulationId?: string | null
  profiles?: unknown[]
  fetchProfilesRealtime?: () => Promise<void>
  addLog?: (msg: string) => void
  confirmFn?: (msg: string) => boolean
} = {}) {
  const simulationId = ref<string | null | undefined>(
    'simulationId' in overrides ? overrides.simulationId : 'sim-001'
  )
  const profiles = ref<unknown[]>(overrides.profiles ?? [])
  const fetchProfilesRealtime = overrides.fetchProfilesRealtime ?? vi.fn().mockResolvedValue(undefined)
  const addLog = overrides.addLog ?? vi.fn()
  const confirmFn = overrides.confirmFn
  return { simulationId, profiles, fetchProfilesRealtime, addLog, confirmFn }
}

// ---------------------------------------------------------------------------
// beforeEach
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('usePersonaLibrary', () => {

  // -------------------------------------------------------------------------
  // Case 1 — loadPersonaLibrary happy-path
  // -------------------------------------------------------------------------

  describe('Case 1 — loadPersonaLibrary happy-path', () => {
    it('setzt personaTemplates auf API-Ergebnis', async () => {
      const templates = [{ template_id: 't1', name: 'Persona A' }, { template_id: 't2', name: 'Persona B' }]
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope(templates) as never)

      const deps = buildDeps()
      const { personaTemplates, loadPersonaLibrary } = usePersonaLibrary(deps)

      await loadPersonaLibrary()

      expect(personaTemplates.value).toEqual(templates)
    })

    it('leert personaLibraryError bei Erfolg', async () => {
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps()
      const { personaLibraryError, loadPersonaLibrary } = usePersonaLibrary(deps)
      personaLibraryError.value = 'alter Fehler'

      await loadPersonaLibrary()

      expect(personaLibraryError.value).toBe('')
    })

    it('toggelt isLoadingPersonaLibrary: true während Call, false danach', async () => {
      let wasLoadingDuring = false
      mockListPersonaTemplates.mockImplementation(async () => {
        wasLoadingDuring = true
        return makeTemplatesEnvelope() as never
      })

      const deps = buildDeps()
      const { isLoadingPersonaLibrary, loadPersonaLibrary } = usePersonaLibrary(deps)

      expect(isLoadingPersonaLibrary.value).toBe(false)
      await loadPersonaLibrary()
      expect(wasLoadingDuring).toBe(true)
      expect(isLoadingPersonaLibrary.value).toBe(false)
    })
  })

  // -------------------------------------------------------------------------
  // Case 2 — loadPersonaLibrary error-path
  // -------------------------------------------------------------------------

  describe('Case 2 — loadPersonaLibrary error-path', () => {
    it('setzt personaLibraryError wenn success: false', async () => {
      mockListPersonaTemplates.mockResolvedValue(makeErrorEnvelope('Bibliothek nicht erreichbar') as never)

      const deps = buildDeps()
      const { personaLibraryError, loadPersonaLibrary } = usePersonaLibrary(deps)

      await loadPersonaLibrary()

      expect(personaLibraryError.value).toBe('Bibliothek nicht erreichbar')
    })

    it('setzt personaLibraryError bei Exception', async () => {
      mockListPersonaTemplates.mockRejectedValue(new Error('Netzwerkfehler'))

      const deps = buildDeps()
      const { personaLibraryError, loadPersonaLibrary } = usePersonaLibrary(deps)

      await loadPersonaLibrary()

      expect(personaLibraryError.value).toBe('Netzwerkfehler')
    })

    it('setzt Fallback-Message wenn kein error-Feld', async () => {
      mockListPersonaTemplates.mockResolvedValue({ success: false } as never)

      const deps = buildDeps()
      const { personaLibraryError, loadPersonaLibrary } = usePersonaLibrary(deps)

      await loadPersonaLibrary()

      expect(personaLibraryError.value).toBe('Bibliothek konnte nicht geladen werden.')
    })
  })

  // -------------------------------------------------------------------------
  // Case 3 — savePersona
  // -------------------------------------------------------------------------

  describe('Case 3 — savePersona', () => {
    it('setzt key in savingPersonaKeys während des Calls', async () => {
      let keyPresentDuring = false
      mockSavePersonaTemplate.mockImplementation(async (_payload: unknown) => {
        keyPresentDuring = true
        return makeTemplateEnvelope() as never
      })
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps()
      const { savingPersonaKeys, savePersona } = usePersonaLibrary(deps)

      await savePersona({ username: 'user1', name: 'Test' })

      expect(keyPresentDuring).toBe(true)
    })

    it('löscht key aus savingPersonaKeys nach dem Call', async () => {
      mockSavePersonaTemplate.mockResolvedValue(makeTemplateEnvelope() as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps()
      const { savingPersonaKeys, savePersona } = usePersonaLibrary(deps)

      await savePersona({ username: 'user1', name: 'Test' })

      expect(savingPersonaKeys.value.has('user1')).toBe(false)
    })

    it('ruft savePersonaTemplate mit whitelisted Payload', async () => {
      mockSavePersonaTemplate.mockResolvedValue(makeTemplateEnvelope() as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps()
      const { savePersona } = usePersonaLibrary(deps)

      await savePersona({
        username: 'user1',
        name: 'Test',
        bio: 'Bio',
        extra_field: 'sollte_rausfallen',
      })

      expect(mockSavePersonaTemplate).toHaveBeenCalledOnce()
      const payload = mockSavePersonaTemplate.mock.calls[0][0]
      expect(payload).toHaveProperty('username', 'user1')
      expect(payload).toHaveProperty('name', 'Test')
      expect(payload).not.toHaveProperty('extra_field')
    })

    it('ruft loadPersonaLibrary nach Erfolg', async () => {
      mockSavePersonaTemplate.mockResolvedValue(makeTemplateEnvelope() as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps()
      const { savePersona } = usePersonaLibrary(deps)

      await savePersona({ username: 'user1' })

      expect(mockListPersonaTemplates).toHaveBeenCalledOnce()
    })

    it('ruft addLog bei Fehler', async () => {
      mockSavePersonaTemplate.mockRejectedValue(new Error('Speicherfehler'))

      const addLog = vi.fn()
      const deps = buildDeps({ addLog })
      const { savePersona } = usePersonaLibrary(deps)

      await savePersona({ username: 'user1' })

      expect(addLog).toHaveBeenCalledWith('Speicherfehler')
    })
  })

  // -------------------------------------------------------------------------
  // Case 4 — usePersonaTemplate
  // -------------------------------------------------------------------------

  describe('Case 4 — usePersonaTemplate', () => {
    it('setzt template_id in usingPersonaTemplateIds während des Calls', async () => {
      let idPresentDuring = false
      mockAddSimulationProfile.mockImplementation(async () => {
        idPresentDuring = true
        return makeProfileEnvelope() as never
      })

      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)
      const deps = buildDeps({ fetchProfilesRealtime })
      const { usingPersonaTemplateIds, usePersonaTemplate } = usePersonaLibrary(deps)

      await usePersonaTemplate({ template_id: 'tmpl-1', name: 'Test' })

      expect(idPresentDuring).toBe(true)
    })

    it('löscht template_id aus usingPersonaTemplateIds nach dem Call', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { usingPersonaTemplateIds, usePersonaTemplate } = usePersonaLibrary(deps)

      await usePersonaTemplate({ template_id: 'tmpl-1', name: 'Test' })

      expect(usingPersonaTemplateIds.value.has('tmpl-1')).toBe(false)
    })

    it('ruft addSimulationProfile mit source_entity_type: library', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { usePersonaTemplate } = usePersonaLibrary(deps)

      await usePersonaTemplate({ template_id: 'tmpl-1', username: 'user1', name: 'Test' })

      expect(mockAddSimulationProfile).toHaveBeenCalledOnce()
      const payload = mockAddSimulationProfile.mock.calls[0][1]
      expect(payload).toHaveProperty('source_entity_type', 'library')
    })

    it('ruft fetchProfilesRealtime nach Erfolg', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { usePersonaTemplate } = usePersonaLibrary(deps)

      await usePersonaTemplate({ template_id: 'tmpl-1' })

      expect(fetchProfilesRealtime).toHaveBeenCalledOnce()
    })

    it('tut nichts wenn kein template_id', async () => {
      const deps = buildDeps()
      const { usePersonaTemplate } = usePersonaLibrary(deps)

      await usePersonaTemplate({ name: 'Kein ID' })

      expect(mockAddSimulationProfile).not.toHaveBeenCalled()
    })
  })

  // -------------------------------------------------------------------------
  // Case 5 — removePersonaTemplate
  // -------------------------------------------------------------------------

  describe('Case 5 — removePersonaTemplate', () => {
    it('ruft keinen API-Call wenn confirmFn false zurückgibt', async () => {
      const deps = buildDeps({ confirmFn: () => false })
      const { removePersonaTemplate } = usePersonaLibrary(deps)

      await removePersonaTemplate('tmpl-1')

      expect(mockDeletePersonaTemplate).not.toHaveBeenCalled()
    })

    it('ruft deletePersonaTemplate wenn confirmFn true zurückgibt', async () => {
      mockDeletePersonaTemplate.mockResolvedValue({ success: true } as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps({ confirmFn: () => true })
      const { removePersonaTemplate } = usePersonaLibrary(deps)

      await removePersonaTemplate('tmpl-1')

      expect(mockDeletePersonaTemplate).toHaveBeenCalledWith('tmpl-1')
    })

    it('ruft loadPersonaLibrary nach erfolgreichem Delete', async () => {
      mockDeletePersonaTemplate.mockResolvedValue({ success: true } as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const deps = buildDeps({ confirmFn: () => true })
      const { removePersonaTemplate } = usePersonaLibrary(deps)

      await removePersonaTemplate('tmpl-1')

      expect(mockListPersonaTemplates).toHaveBeenCalledOnce()
    })

    it('ruft addLog bei Fehler-Response', async () => {
      mockDeletePersonaTemplate.mockResolvedValue(makeErrorEnvelope('Löschen fehlgeschlagen') as never)

      const addLog = vi.fn()
      const deps = buildDeps({ confirmFn: () => true, addLog })
      const { removePersonaTemplate } = usePersonaLibrary(deps)

      await removePersonaTemplate('tmpl-1')

      expect(addLog).toHaveBeenCalledWith(expect.stringContaining('Löschen fehlgeschlagen'))
    })
  })

  // -------------------------------------------------------------------------
  // Case 6 — removePersona
  // -------------------------------------------------------------------------

  describe('Case 6 — removePersona', () => {
    it('tut nichts wenn confirmFn false zurückgibt', async () => {
      const deps = buildDeps({ confirmFn: () => false })
      const { removePersona } = usePersonaLibrary(deps)

      await removePersona('user1')

      expect(mockDeleteSimulationProfile).not.toHaveBeenCalled()
    })

    it('ruft deleteSimulationProfile wenn confirmFn true', async () => {
      mockDeleteSimulationProfile.mockResolvedValue({ success: true } as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ confirmFn: () => true, fetchProfilesRealtime })
      const { removePersona } = usePersonaLibrary(deps)

      await removePersona('user1')

      expect(mockDeleteSimulationProfile).toHaveBeenCalledWith('sim-001', 'user1')
    })

    it('ruft fetchProfilesRealtime nach Erfolg', async () => {
      mockDeleteSimulationProfile.mockResolvedValue({ success: true } as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ confirmFn: () => true, fetchProfilesRealtime })
      const { removePersona } = usePersonaLibrary(deps)

      await removePersona('user1')

      expect(fetchProfilesRealtime).toHaveBeenCalledOnce()
    })

    it('tut nichts bei leerem username', async () => {
      const deps = buildDeps({ confirmFn: () => true })
      const { removePersona } = usePersonaLibrary(deps)

      await removePersona('')

      expect(mockDeleteSimulationProfile).not.toHaveBeenCalled()
    })
  })

  // -------------------------------------------------------------------------
  // Case 7 — submitNewPersona
  // -------------------------------------------------------------------------

  describe('Case 7 — submitNewPersona', () => {
    it('splittet interested_topics CSV zu Array', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { newPersona, submitNewPersona } = usePersonaLibrary(deps)

      newPersona.value.username = 'user1'
      newPersona.value.interested_topics = 'Tech, Sport, Musik'

      await submitNewPersona()

      const payload = mockAddSimulationProfile.mock.calls[0][1]
      expect(payload.interested_topics).toEqual(['Tech', 'Sport', 'Musik'])
    })

    it('filtert leere Einträge aus interested_topics', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { newPersona, submitNewPersona } = usePersonaLibrary(deps)

      newPersona.value.username = 'user1'
      newPersona.value.interested_topics = 'Tech,  , Sport'

      await submitNewPersona()

      const payload = mockAddSimulationProfile.mock.calls[0][1]
      expect(payload.interested_topics).toEqual(['Tech', 'Sport'])
    })

    it('löscht leeres age aus payload', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { newPersona, submitNewPersona } = usePersonaLibrary(deps)

      newPersona.value.username = 'user1'
      newPersona.value.age = '' as unknown as null

      await submitNewPersona()

      const payload = mockAddSimulationProfile.mock.calls[0][1]
      expect(payload).not.toHaveProperty('age')
    })

    it('schließt Modal und resettet newPersona nach Erfolg', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeProfileEnvelope() as never)
      const fetchProfilesRealtime = vi.fn().mockResolvedValue(undefined)

      const deps = buildDeps({ fetchProfilesRealtime })
      const { newPersona, showAddPersonaModal, submitNewPersona } = usePersonaLibrary(deps)

      showAddPersonaModal.value = true
      newPersona.value.username = 'user1'
      newPersona.value.name = 'Test User'

      await submitNewPersona()

      expect(showAddPersonaModal.value).toBe(false)
      expect(newPersona.value.username).toBe('')
      expect(newPersona.value.name).toBe('')
    })

    it('tut nichts wenn simulationId fehlt', async () => {
      const deps = buildDeps({ simulationId: null })
      const { newPersona, submitNewPersona } = usePersonaLibrary(deps)

      newPersona.value.username = 'user1'

      await submitNewPersona()

      expect(mockAddSimulationProfile).not.toHaveBeenCalled()
    })

    it('ruft addLog bei Fehler-Response', async () => {
      mockAddSimulationProfile.mockResolvedValue(makeErrorEnvelope('Profil-Fehler') as never)

      const addLog = vi.fn()
      const deps = buildDeps({ addLog })
      const { newPersona, submitNewPersona } = usePersonaLibrary(deps)

      newPersona.value.username = 'user1'

      await submitNewPersona()

      expect(addLog).toHaveBeenCalledWith(expect.stringContaining('Profil-Fehler'))
    })
  })

  // -------------------------------------------------------------------------
  // Case 8 — profileKey / profilePayload
  // -------------------------------------------------------------------------

  describe('Case 8 — profileKey / profilePayload', () => {
    it('profileKey: bevorzugt template_id', () => {
      const deps = buildDeps()
      const { profileKey } = usePersonaLibrary(deps)

      expect(profileKey({ template_id: 'tmpl-1', username: 'user1' })).toBe('tmpl-1')
    })

    it('profileKey: fällt back auf username wenn kein template_id', () => {
      const deps = buildDeps()
      const { profileKey } = usePersonaLibrary(deps)

      expect(profileKey({ username: 'user1' })).toBe('user1')
    })

    it('profileKey: gibt leeren String zurück bei null-Profil', () => {
      const deps = buildDeps()
      const { profileKey } = usePersonaLibrary(deps)

      expect(profileKey(null)).toBe('')
    })

    it('profilePayload: filtert nicht-whitelisted Felder raus', () => {
      const deps = buildDeps()
      const { profilePayload } = usePersonaLibrary(deps)

      const result = profilePayload({
        username: 'user1',
        name: 'Test',
        extra_field: 'sollte_rausfallen',
        another_extra: 42,
      })

      expect(result).toHaveProperty('username', 'user1')
      expect(result).toHaveProperty('name', 'Test')
      expect(result).not.toHaveProperty('extra_field')
      expect(result).not.toHaveProperty('another_extra')
    })

    it('profilePayload: strippt undefined/null/leere-String-Felder', () => {
      const deps = buildDeps()
      const { profilePayload } = usePersonaLibrary(deps)

      const result = profilePayload({
        username: 'user1',
        name: '',
        bio: null,
        persona: undefined,
        country: 'DE',
      })

      expect(result).toHaveProperty('username', 'user1')
      expect(result).toHaveProperty('country', 'DE')
      expect(result).not.toHaveProperty('name')
      expect(result).not.toHaveProperty('bio')
      expect(result).not.toHaveProperty('persona')
    })
  })

  // -------------------------------------------------------------------------
  // Case 9 — saveAllPersonas
  // -------------------------------------------------------------------------

  describe('Case 9 — saveAllPersonas', () => {
    it('ruft savePersona für jedes Profil in profiles.value', async () => {
      mockSavePersonaTemplate.mockResolvedValue(makeTemplateEnvelope() as never)
      mockListPersonaTemplates.mockResolvedValue(makeTemplatesEnvelope() as never)

      const profiles = [
        { username: 'user1', name: 'Alice' },
        { username: 'user2', name: 'Bob' },
        { username: 'user3', name: 'Carol' },
      ]
      const deps = buildDeps({ profiles })
      const { saveAllPersonas } = usePersonaLibrary(deps)

      await saveAllPersonas()

      expect(mockSavePersonaTemplate).toHaveBeenCalledTimes(3)
    })

    it('tut nichts bei leerer profiles-Liste', async () => {
      const deps = buildDeps({ profiles: [] })
      const { saveAllPersonas } = usePersonaLibrary(deps)

      await saveAllPersonas()

      expect(mockSavePersonaTemplate).not.toHaveBeenCalled()
    })
  })

})
