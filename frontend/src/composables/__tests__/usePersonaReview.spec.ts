/**
 * Tests für usePersonaReview — Composable für Persona-Approve/Reject/Regenerate.
 *
 * Sub-Slice 33: describe('regenerate') — neue Methode für Persona-Regenerate.
 *
 * Getestete Contracts:
 *   1. Erfolgsfall: API liefert ProfileRecord mit review_status 'regenerating',
 *      Composable returned das Profile
 *   2. Mit Hint: regenerate(sim, user, 'mehr Skepsis') ruft API mit korrektem Body
 *   3. Ohne Hint: regenerate ohne drittes Argument
 *   4. Idempotenz: zweiter Aufruf bei regenerating-Status wird toleriert (200)
 *   5. Fehler-Pfad: success=false mit Backend-Fehlermeldung
 *   6. Fehler-Pfad: success=false ohne error-Feld → Fallback-Message
 *   7. Fehler-Pfad: Netzwerkfehler (rejected Promise)
 *   8. Rückgabe-Objekt enthält regenerate neben approve und reject
 *   9. Approve/Reject Baseline-Regression
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// --- Mock des api/simulation-Moduls BEVOR der Import des Composables ---
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
  getSimulationProfilesQuality,
  type ProfileRecord,
} from '../../api/simulation'
import type { ApiEnvelope } from '../../api/envelope'
import { usePersonaReview } from '../usePersonaReview'

const mockRegenerateSimulationProfile = vi.mocked(regenerateSimulationProfile)
const mockApproveSimulationProfile = vi.mocked(approveSimulationProfile)
const mockRejectSimulationProfile = vi.mocked(rejectSimulationProfile)
const mockGetQuality = vi.mocked(getSimulationProfilesQuality)

function makeProfileEnvelope(overrides: Partial<ProfileRecord> = {}): ApiEnvelope<ProfileRecord> {
  return {
    success: true,
    data: {
      username: 'test_user',
      name: 'Test User',
      bio: 'A test persona.',
      review_status: 'regenerating',
      ...overrides,
    },
  }
}

function makeErrorEnvelope(error = 'Server-Fehler'): ApiEnvelope<ProfileRecord> {
  return {
    success: false,
    error,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: quality fetch returns empty success
  mockGetQuality.mockResolvedValue({
    success: true,
    data: { simulation_id: 'sim-001', profiles: [], personas: [] },
  })
})

describe('usePersonaReview', () => {
  describe('regenerate', () => {
    it('Erfolgsfall: API liefert ProfileRecord mit review_status regenerating, Composable returned das Profile', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'regenerating' })
      )

      const composable = usePersonaReview()
      const result = await composable.regenerate('sim-001', 'test_user')

      expect(mockRegenerateSimulationProfile).toHaveBeenCalledWith('sim-001', 'test_user', undefined)
      expect(result).toBeDefined()
      expect(result?.username).toBe('test_user')
      expect(result?.review_status).toBe('regenerating')
    })

    it('Mit Hint: regenerate ruft API mit korrektem Body-Hint', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'regenerating' })
      )

      const composable = usePersonaReview()
      await composable.regenerate('sim-001', 'skeptic_user', 'mehr Skepsis')

      expect(mockRegenerateSimulationProfile).toHaveBeenCalledWith(
        'sim-001',
        'skeptic_user',
        'mehr Skepsis'
      )
    })

    it('Ohne Hint: regenerate ruft API mit undefined als drittes Argument', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'regenerating' })
      )

      const composable = usePersonaReview()
      await composable.regenerate('sim-001', 'test_user')

      expect(mockRegenerateSimulationProfile).toHaveBeenCalledWith('sim-001', 'test_user', undefined)
    })

    it('Idempotenz: zweiter Aufruf bei regenerating-Status wird toleriert (200)', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'regenerating' })
      )

      const composable = usePersonaReview()
      const first = await composable.regenerate('sim-001', 'test_user')
      const second = await composable.regenerate('sim-001', 'test_user')

      expect(mockRegenerateSimulationProfile).toHaveBeenCalledTimes(2)
      expect(first?.review_status).toBe('regenerating')
      expect(second?.review_status).toBe('regenerating')
    })

    it('Fehler-Pfad: API liefert success=false, Composable wirft mit der Backend-Fehlermeldung', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue(
        makeErrorEnvelope('Persona nicht gefunden.')
      )

      const composable = usePersonaReview()

      await expect(composable.regenerate('sim-001', 'missing_user')).rejects.toThrow(
        'Persona nicht gefunden.'
      )
    })

    it('Fehler-Pfad: API liefert success=false ohne error-Feld, Composable wirft Fallback-Message', async () => {
      mockRegenerateSimulationProfile.mockResolvedValue({ success: false })

      const composable = usePersonaReview()

      await expect(composable.regenerate('sim-001', 'bad_user')).rejects.toThrow(
        'Regenerate fehlgeschlagen.'
      )
    })

    it('Fehler-Pfad: Netzwerkfehler (throw), Composable propagiert den Fehler', async () => {
      mockRegenerateSimulationProfile.mockRejectedValue(new Error('Network Error'))

      const composable = usePersonaReview()

      await expect(composable.regenerate('sim-001', 'net_error_user')).rejects.toThrow('Network Error')
    })

    it('Rückgabe-Objekt enthält regenerate neben approve und reject', () => {
      const composable = usePersonaReview()

      expect(typeof composable.regenerate).toBe('function')
      expect(typeof composable.approve).toBe('function')
      expect(typeof composable.reject).toBe('function')
    })
  })

  describe('approve (Baseline-Regression nach Sub-Slice 33)', () => {
    it('approve ruft approveSimulationProfile korrekt auf', async () => {
      mockApproveSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'approved' })
      )

      const composable = usePersonaReview()
      const result = await composable.approve('sim-001', 'user1', 'sieht gut aus')

      expect(mockApproveSimulationProfile).toHaveBeenCalledWith('sim-001', 'user1', 'sieht gut aus')
      expect(result?.review_status).toBe('approved')
    })
  })

  describe('reject (Baseline-Regression nach Sub-Slice 33)', () => {
    it('reject ruft rejectSimulationProfile korrekt auf', async () => {
      mockRejectSimulationProfile.mockResolvedValue(
        makeProfileEnvelope({ review_status: 'rejected' })
      )

      const composable = usePersonaReview()
      const result = await composable.reject('sim-001', 'user2', 'nicht geeignet')

      expect(mockRejectSimulationProfile).toHaveBeenCalledWith('sim-001', 'user2', 'nicht geeignet')
      expect(result?.review_status).toBe('rejected')
    })
  })
})
