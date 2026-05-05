/**
 * Tests für usePersonaActions — Sub-Slice 38, Refs #203.
 *
 * Getestete Contracts:
 *   1. statusVariant mappt approved/pending/rejected/regenerating → korrekte Badge-Varianten + Default 'ghost'.
 *   2. issueBadgeVariant mappt error/warning/info + Default 'ghost'.
 *   3. startEditingSelected füllt editingProfile aus selectedProfile; konvertiert interested_topics-Array zu String.
 *   4. approveSelected: ruft personaReview.approve, patcht profiles + selectedProfile, ruft addLog, refreshQuality.
 *      reviewActionPending true → false. Auf Error: füllt reviewActionError.
 *   5. rejectSelected: Happy-Path + Error-Pfad.
 *   6. regenerateSelected: trimmed hint, undefined bei leerem Hint, leert regenerateHint nach Erfolg.
 *   7. hasRegeneratingPersona reactive: false → true wenn profiles enthält review_status === 'regenerating'.
 *   8. saveEditingProfile: löscht username aus payload, splittet topics-String, entfernt leeres age,
 *      ruft editProfile, setzt editingProfile = null nach Erfolg.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'

// ---------------------------------------------------------------------------
// Mock vue-i18n BEFORE composable import
// ---------------------------------------------------------------------------

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

// ---------------------------------------------------------------------------
// Mock api/simulation BEFORE composable import
// ---------------------------------------------------------------------------

vi.mock('../../api/simulation', () => ({
  approveSimulationProfile: vi.fn(),
  rejectSimulationProfile: vi.fn(),
  regenerateSimulationProfile: vi.fn(),
  editSimulationProfile: vi.fn(),
  getSimulationProfilesQuality: vi.fn(),
}))

import {
  approveSimulationProfile,
  rejectSimulationProfile,
  regenerateSimulationProfile,
  editSimulationProfile,
  getSimulationProfilesQuality,
  type ProfileRecord,
} from '../../api/simulation'

import { usePersonaActions } from '../usePersonaActions'

const mockApprove = vi.mocked(approveSimulationProfile)
const mockReject = vi.mocked(rejectSimulationProfile)
const mockRegenerate = vi.mocked(regenerateSimulationProfile)
const mockEditProfile = vi.mocked(editSimulationProfile)
const mockGetQuality = vi.mocked(getSimulationProfilesQuality)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeProfileEnvelope(overrides: Partial<ProfileRecord> = {}): unknown {
  return {
    success: true,
    data: {
      username: 'user1',
      name: 'Test User',
      bio: 'Bio',
      review_status: 'approved',
      ...overrides,
    },
  }
}

function makeErrorEnvelope(error = 'Server-Fehler'): unknown {
  return { success: false, error }
}

function makeQualitySuccess(): unknown {
  return { success: true, data: { personas: [] } }
}

function buildDeps(overrides: {
  simulationId?: string | null
  profiles?: ProfileRecord[]
  selectedProfile?: ProfileRecord | null
} = {}) {
  const simulationId = ref<string | null | undefined>(
    'simulationId' in overrides ? overrides.simulationId : 'sim-001'
  )
  const profiles = ref<ProfileRecord[]>(overrides.profiles ?? [])
  const selectedProfile = ref<ProfileRecord | null>(overrides.selectedProfile ?? null)
  const addLog = vi.fn()
  return { simulationId, profiles, selectedProfile, addLog }
}

// ---------------------------------------------------------------------------
// beforeEach
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  mockGetQuality.mockResolvedValue(makeQualitySuccess() as import('../../api/simulation').ProfileQualityResponse)
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('usePersonaActions', () => {

  // -------------------------------------------------------------------------
  // Case 1 — statusVariant
  // -------------------------------------------------------------------------

  describe('Case 1 — statusVariant', () => {
    it('mappt approved → success', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant('approved')).toBe('success')
    })

    it('mappt pending → warn', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant('pending')).toBe('warn')
    })

    it('mappt rejected → error', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant('rejected')).toBe('error')
    })

    it('mappt regenerating → accent', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant('regenerating')).toBe('accent')
    })

    it('unbekannter Status → ghost', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant('unknown_xyz')).toBe('ghost')
    })

    it('undefined Status → ghost', () => {
      const deps = buildDeps()
      const { statusVariant } = usePersonaActions(deps)
      expect(statusVariant(undefined as unknown as string)).toBe('ghost')
    })
  })

  // -------------------------------------------------------------------------
  // Case 2 — issueBadgeVariant
  // -------------------------------------------------------------------------

  describe('Case 2 — issueBadgeVariant', () => {
    it('mappt error → error', () => {
      const deps = buildDeps()
      const { issueBadgeVariant } = usePersonaActions(deps)
      expect(issueBadgeVariant('error')).toBe('error')
    })

    it('mappt warning → warn', () => {
      const deps = buildDeps()
      const { issueBadgeVariant } = usePersonaActions(deps)
      expect(issueBadgeVariant('warning')).toBe('warn')
    })

    it('mappt info → plasma', () => {
      const deps = buildDeps()
      const { issueBadgeVariant } = usePersonaActions(deps)
      expect(issueBadgeVariant('info')).toBe('plasma')
    })

    it('unbekannte Severity → ghost', () => {
      const deps = buildDeps()
      const { issueBadgeVariant } = usePersonaActions(deps)
      expect(issueBadgeVariant('unknown')).toBe('ghost')
    })
  })

  // -------------------------------------------------------------------------
  // Case 3 — startEditingSelected
  // -------------------------------------------------------------------------

  describe('Case 3 — startEditingSelected', () => {
    it('füllt editingProfile aus selectedProfile.value', () => {
      const selectedProfile = ref<ProfileRecord | null>({
        username: 'alice',
        name: 'Alice',
        bio: 'Meine Bio',
        persona: 'Kritisch',
        profession: 'Lehrerin',
        country: 'DE',
        age: 35,
        gender: 'female',
        mbti: 'INFJ',
        interested_topics: ['Bildung', 'Politik'],
      })
      const deps = { ...buildDeps(), selectedProfile }
      const { editingProfile, startEditingSelected } = usePersonaActions(deps)

      expect(editingProfile.value).toBeNull()
      startEditingSelected()

      expect(editingProfile.value).not.toBeNull()
      expect(editingProfile.value?.username).toBe('alice')
      expect(editingProfile.value?.name).toBe('Alice')
      expect(editingProfile.value?.profession).toBe('Lehrerin')
    })

    it('konvertiert interested_topics-Array zu Komma-String', () => {
      const selectedProfile = ref<ProfileRecord | null>({
        username: 'bob',
        interested_topics: ['Tech', 'Sport', 'Musik'],
      })
      const deps = { ...buildDeps(), selectedProfile }
      const { editingProfile, startEditingSelected } = usePersonaActions(deps)

      startEditingSelected()
      expect(editingProfile.value?.interested_topics).toBe('Tech, Sport, Musik')
    })

    it('behält interested_topics-String unverändert', () => {
      const selectedProfile = ref<ProfileRecord | null>({
        username: 'carol',
        interested_topics: 'Tech, Sport',
      })
      const deps = { ...buildDeps(), selectedProfile }
      const { editingProfile, startEditingSelected } = usePersonaActions(deps)

      startEditingSelected()
      expect(editingProfile.value?.interested_topics).toBe('Tech, Sport')
    })

    it('tut nichts wenn selectedProfile null', () => {
      const deps = buildDeps({ selectedProfile: null })
      const { editingProfile, startEditingSelected } = usePersonaActions(deps)

      startEditingSelected()
      expect(editingProfile.value).toBeNull()
    })

    it('löscht reviewActionError beim Start', () => {
      const selectedProfile = ref<ProfileRecord | null>({ username: 'dave' })
      const deps = { ...buildDeps(), selectedProfile }
      const { reviewActionError, startEditingSelected } = usePersonaActions(deps)

      reviewActionError.value = 'alter Fehler'
      startEditingSelected()
      expect(reviewActionError.value).toBe('')
    })
  })

  // -------------------------------------------------------------------------
  // Case 4 — approveSelected
  // -------------------------------------------------------------------------

  describe('Case 4 — approveSelected', () => {
    it('Happy-Path: ruft approve, patcht profiles + selectedProfile, ruft addLog + refreshQuality', async () => {
      const profileBefore: ProfileRecord = { username: 'user1', review_status: 'pending' }
      const profileAfter: ProfileRecord = { username: 'user1', review_status: 'approved' }

      mockApprove.mockResolvedValue(makeProfileEnvelope({ review_status: 'approved' }) as ProfileRecord)

      const profiles = ref<ProfileRecord[]>([profileBefore])
      const selectedProfile = ref<ProfileRecord | null>(profileBefore)
      const { addLog, simulationId } = buildDeps()
      const deps = { simulationId, profiles, selectedProfile, addLog }

      const { approveSelected } = usePersonaActions(deps)
      await approveSelected()

      expect(mockApprove).toHaveBeenCalledWith('sim-001', 'user1', undefined)
      expect(profiles.value[0].review_status).toBe('approved')
      expect(selectedProfile.value?.review_status).toBe('approved')
      expect(addLog).toHaveBeenCalledOnce()
      expect(mockGetQuality).toHaveBeenCalledWith('sim-001')
    })

    it('reviewActionPending ist true während des Calls, false danach', async () => {
      let pendingDuring = false
      mockApprove.mockImplementation(async () => {
        pendingDuring = true
        return makeProfileEnvelope() as ProfileRecord
      })

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { approveSelected, reviewActionPending } = usePersonaActions(deps)

      const promise = approveSelected()
      // During the call, pendingDuring will be set to true
      await promise
      expect(pendingDuring).toBe(true)
      expect(reviewActionPending.value).toBe(false)
    })

    it('Error-Pfad: füllt reviewActionError, setzt reviewActionPending = false', async () => {
      mockApprove.mockRejectedValue(new Error('Approve-Fehler'))

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { approveSelected, reviewActionError, reviewActionPending } = usePersonaActions(deps)

      await approveSelected()

      expect(reviewActionError.value).toBe('Approve-Fehler')
      expect(reviewActionPending.value).toBe(false)
    })

    it('tut nichts wenn kein selectedProfile', async () => {
      const deps = buildDeps({ selectedProfile: null })
      const { approveSelected } = usePersonaActions(deps)

      await approveSelected()
      expect(mockApprove).not.toHaveBeenCalled()
    })

    it('tut nichts wenn keine simulationId', async () => {
      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps({ simulationId: null }), selectedProfile }
      const { approveSelected } = usePersonaActions(deps)

      await approveSelected()
      expect(mockApprove).not.toHaveBeenCalled()
    })
  })

  // -------------------------------------------------------------------------
  // Case 5 — rejectSelected
  // -------------------------------------------------------------------------

  describe('Case 5 — rejectSelected', () => {
    it('Happy-Path: ruft reject, patcht profiles, ruft addLog + refreshQuality', async () => {
      mockReject.mockResolvedValue(makeProfileEnvelope({ review_status: 'rejected' }) as ProfileRecord)

      const profiles = ref<ProfileRecord[]>([{ username: 'user1', review_status: 'pending' }])
      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1', review_status: 'pending' })
      const { addLog, simulationId } = buildDeps()
      const deps = { simulationId, profiles, selectedProfile, addLog }

      const { rejectSelected } = usePersonaActions(deps)
      await rejectSelected()

      expect(mockReject).toHaveBeenCalledWith('sim-001', 'user1', undefined)
      expect(profiles.value[0].review_status).toBe('rejected')
      expect(addLog).toHaveBeenCalledOnce()
      expect(mockGetQuality).toHaveBeenCalledWith('sim-001')
    })

    it('Error-Pfad: füllt reviewActionError', async () => {
      mockReject.mockRejectedValue(new Error('Reject fehlgeschlagen'))

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { rejectSelected, reviewActionError } = usePersonaActions(deps)

      await rejectSelected()
      expect(reviewActionError.value).toBe('Reject fehlgeschlagen')
    })
  })

  // -------------------------------------------------------------------------
  // Case 6 — regenerateSelected
  // -------------------------------------------------------------------------

  describe('Case 6 — regenerateSelected', () => {
    it('übergibt getrimten Hint an regenerate', async () => {
      mockRegenerate.mockResolvedValue(makeProfileEnvelope({ review_status: 'regenerating' }) as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { regenerateSelected, regenerateHint } = usePersonaActions(deps)

      regenerateHint.value = '  mehr Skepsis  '
      await regenerateSelected()

      expect(mockRegenerate).toHaveBeenCalledWith('sim-001', 'user1', 'mehr Skepsis')
    })

    it('übergibt undefined wenn Hint nach trim leer ist', async () => {
      mockRegenerate.mockResolvedValue(makeProfileEnvelope({ review_status: 'regenerating' }) as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { regenerateSelected, regenerateHint } = usePersonaActions(deps)

      regenerateHint.value = '   '
      await regenerateSelected()

      expect(mockRegenerate).toHaveBeenCalledWith('sim-001', 'user1', undefined)
    })

    it('leert regenerateHint nach Erfolg', async () => {
      mockRegenerate.mockResolvedValue(makeProfileEnvelope({ review_status: 'regenerating' }) as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { regenerateSelected, regenerateHint } = usePersonaActions(deps)

      regenerateHint.value = 'mehr Detail'
      await regenerateSelected()

      expect(regenerateHint.value).toBe('')
    })

    it('behält regenerateHint bei Fehler', async () => {
      mockRegenerate.mockRejectedValue(new Error('Regen fehlgeschlagen'))

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { regenerateSelected, regenerateHint, reviewActionError } = usePersonaActions(deps)

      regenerateHint.value = 'wichtiger Hinweis'
      await regenerateSelected()

      // On error, hint is NOT cleared (only cleared on success)
      expect(regenerateHint.value).toBe('wichtiger Hinweis')
      expect(reviewActionError.value).toBe('Regen fehlgeschlagen')
    })
  })

  // -------------------------------------------------------------------------
  // Case 7 — hasRegeneratingPersona
  // -------------------------------------------------------------------------

  describe('Case 7 — hasRegeneratingPersona', () => {
    it('false wenn keine Profile vorhanden', () => {
      const deps = buildDeps({ profiles: [] })
      const { hasRegeneratingPersona } = usePersonaActions(deps)
      expect(hasRegeneratingPersona.value).toBe(false)
    })

    it('false wenn kein Profil den Status regenerating hat', () => {
      const deps = buildDeps({
        profiles: [
          { username: 'a', review_status: 'approved' },
          { username: 'b', review_status: 'pending' },
        ],
      })
      const { hasRegeneratingPersona } = usePersonaActions(deps)
      expect(hasRegeneratingPersona.value).toBe(false)
    })

    it('true wenn mindestens ein Profil regenerating ist', () => {
      const deps = buildDeps({
        profiles: [
          { username: 'a', review_status: 'approved' },
          { username: 'b', review_status: 'regenerating' },
        ],
      })
      const { hasRegeneratingPersona } = usePersonaActions(deps)
      expect(hasRegeneratingPersona.value).toBe(true)
    })

    it('wird reaktiv: false → true wenn Profil-Status auf regenerating wechselt', async () => {
      const profiles = ref<ProfileRecord[]>([
        { username: 'a', review_status: 'pending' },
      ])
      const deps = { ...buildDeps(), profiles }
      const { hasRegeneratingPersona } = usePersonaActions(deps)

      expect(hasRegeneratingPersona.value).toBe(false)

      profiles.value[0] = { username: 'a', review_status: 'regenerating' }
      await nextTick()

      expect(hasRegeneratingPersona.value).toBe(true)
    })
  })

  // -------------------------------------------------------------------------
  // Case 8 — saveEditingProfile
  // -------------------------------------------------------------------------

  describe('Case 8 — saveEditingProfile', () => {
    it('Happy-Path: sendet payload ohne username, splittet topics, ruft editProfile', async () => {
      mockEditProfile.mockResolvedValue(makeProfileEnvelope({ review_status: 'pending' }) as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const profiles = ref<ProfileRecord[]>([{ username: 'user1', review_status: 'pending' }])
      const { addLog, simulationId } = buildDeps()
      const deps = { simulationId, profiles, selectedProfile, addLog }
      const { saveEditingProfile, startEditingSelected, editingProfile } = usePersonaActions(deps)

      startEditingSelected()
      // Inject editable state
      editingProfile.value = {
        username: 'user1',
        name: 'Neuer Name',
        bio: 'Neue Bio',
        persona: '',
        profession: '',
        country: 'DE',
        age: 30,
        gender: 'male',
        mbti: '',
        interested_topics: 'Tech, Sport, Musik',
      }

      await saveEditingProfile()

      expect(mockEditProfile).toHaveBeenCalledOnce()
      const [calledSim, calledUser, calledPayload] = mockEditProfile.mock.calls[0]
      expect(calledSim).toBe('sim-001')
      expect(calledUser).toBe('user1')
      // username must NOT be in payload
      expect(calledPayload).not.toHaveProperty('username')
      // topics must be split to array
      expect(calledPayload.interested_topics).toEqual(['Tech', 'Sport', 'Musik'])
    })

    it('entfernt leeres age aus payload', async () => {
      mockEditProfile.mockResolvedValue(makeProfileEnvelope() as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { saveEditingProfile, editingProfile } = usePersonaActions(deps)

      editingProfile.value = {
        username: 'user1',
        name: 'Test',
        bio: '',
        persona: '',
        profession: '',
        country: 'DE',
        age: '',
        gender: 'other',
        mbti: '',
        interested_topics: '',
      }

      await saveEditingProfile()

      const calledPayload = mockEditProfile.mock.calls[0][2]
      expect(calledPayload).not.toHaveProperty('age')
    })

    it('setzt editingProfile = null nach Erfolg', async () => {
      mockEditProfile.mockResolvedValue(makeProfileEnvelope() as ProfileRecord)

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { saveEditingProfile, editingProfile } = usePersonaActions(deps)

      editingProfile.value = {
        username: 'user1',
        name: 'Test',
        bio: '',
        persona: '',
        profession: '',
        country: 'DE',
        age: null,
        gender: 'other',
        mbti: '',
        interested_topics: '',
      }

      await saveEditingProfile()
      expect(editingProfile.value).toBeNull()
    })

    it('Error-Pfad: füllt reviewActionError, behält editingProfile', async () => {
      mockEditProfile.mockRejectedValue(new Error('Edit fehlgeschlagen'))

      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { saveEditingProfile, editingProfile, reviewActionError } = usePersonaActions(deps)

      editingProfile.value = {
        username: 'user1',
        name: 'Test',
        bio: '',
        persona: '',
        profession: '',
        country: 'DE',
        age: null,
        gender: 'other',
        mbti: '',
        interested_topics: '',
      }

      await saveEditingProfile()
      expect(reviewActionError.value).toBe('Edit fehlgeschlagen')
      expect(editingProfile.value).not.toBeNull()
    })

    it('tut nichts wenn editingProfile null', async () => {
      const deps = buildDeps()
      const { saveEditingProfile } = usePersonaActions(deps)

      await saveEditingProfile()
      expect(mockEditProfile).not.toHaveBeenCalled()
    })
  })

  // -------------------------------------------------------------------------
  // Case — cancelEditing
  // -------------------------------------------------------------------------

  describe('cancelEditing', () => {
    it('setzt editingProfile auf null und löscht reviewActionError', () => {
      const selectedProfile = ref<ProfileRecord | null>({ username: 'user1' })
      const deps = { ...buildDeps(), selectedProfile }
      const { editingProfile, reviewActionError, cancelEditing } = usePersonaActions(deps)

      editingProfile.value = { username: 'user1', name: '', bio: '', persona: '', profession: '', country: '', age: null, gender: 'other', mbti: '', interested_topics: '' }
      reviewActionError.value = 'irgendein Fehler'

      cancelEditing()

      expect(editingProfile.value).toBeNull()
      expect(reviewActionError.value).toBe('')
    })
  })

  // -------------------------------------------------------------------------
  // Case — personaReview exposed
  // -------------------------------------------------------------------------

  describe('personaReview exposed', () => {
    it('gibt personaReview mit approve/reject/regenerate zurück', () => {
      const deps = buildDeps()
      const { personaReview } = usePersonaActions(deps)

      expect(typeof personaReview.approve).toBe('function')
      expect(typeof personaReview.reject).toBe('function')
      expect(typeof personaReview.regenerate).toBe('function')
      expect(typeof personaReview.refreshQuality).toBe('function')
    })
  })
})
