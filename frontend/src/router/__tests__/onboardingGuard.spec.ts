/**
 * onboardingGuard — Vitest-Smokes (Onboarding Slice 2).
 *
 * Tests:
 *  1. Redirect zu Onboarding wenn store.onboardingRequired === true.
 *  2. Durchlass wenn onboardingRequired === false (z.B. completed/dismissed).
 *  3. Durchlass wenn Ziel selbst 'Onboarding' ist (kein Redirect-Loop).
 *  4. Durchlass wenn Ziel 'NotFound' ist.
 *  5. Durchlass bei API-Fehler (ensureLoaded() wirft) — kein Lockout.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'

vi.mock('../../api/profile', () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
  getOnboardingStatus: vi.fn(),
  completeOnboardingStep: vi.fn(),
  completeOnboarding: vi.fn(),
  dismissOnboarding: vi.fn(),
  reopenOnboarding: vi.fn(),
}))

import { getOnboardingStatus, getProfile } from '../../api/profile'
import { onboardingGuard } from '../onboardingGuard'
import type { OnboardingStatusResponse, UserProfile } from '../../contracts/userProfileContract'

type MockFn = ReturnType<typeof vi.fn>
const _getProfile = getProfile as unknown as MockFn
const _getOnboardingStatus = getOnboardingStatus as unknown as MockFn

function makeProfile(): UserProfile {
  return {
    avatar_ref: null,
    display_name: 'Alex Schneider',
    username: null,
    role: null,
    organisation: null,
    language: 'de',
    timezone: 'Europe/Berlin',
    report_language: 'de',
    theme: 'system',
    privacy_mode: 'standard',
    created_at: '2026-07-11T00:00:00Z',
    updated_at: '2026-07-11T00:00:00Z',
  }
}

function makeOnboardingStatus(onboardingRequired: boolean): OnboardingStatusResponse {
  return {
    state: {
      status: onboardingRequired ? 'in_progress' : 'completed',
      operating_mode: 'local',
      current_step: 'welcome',
      completed_steps: [],
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    },
    requirements: {
      profile_valid: !onboardingRequired,
      chat_model_configured: !onboardingRequired,
      embedding_configured: !onboardingRequired,
    },
    onboarding_required: onboardingRequired,
  }
}

function route(name: string): RouteLocationNormalized {
  return { name } as unknown as RouteLocationNormalized
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('onboardingGuard', () => {
  it('Test 1: redirectet zu Onboarding wenn onboardingRequired === true', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus(true))

    const result = await onboardingGuard(route('Dashboard'))
    expect(result).toEqual({ name: 'Onboarding' })
  })

  it('Test 2: lässt Navigation durch wenn onboardingRequired === false', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus(false))

    const result = await onboardingGuard(route('Dashboard'))
    expect(result).toBe(true)
  })

  it('Test 3: kein Redirect-Loop wenn Ziel bereits Onboarding ist', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus(true))

    const result = await onboardingGuard(route('Onboarding'))
    expect(result).toBe(true)
    // ensureLoaded() darf für die exempte Route gar nicht erst aufgerufen werden.
    expect(_getProfile).not.toHaveBeenCalled()
  })

  it('Test 4: lässt NotFound immer durch', async () => {
    _getProfile.mockResolvedValue(null)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus(true))

    const result = await onboardingGuard(route('NotFound'))
    expect(result).toBe(true)
  })

  it('Test 5: lässt Navigation durch bei API-Fehler (kein Lockout)', async () => {
    _getProfile.mockRejectedValue(new Error('Netzwerkfehler'))
    _getOnboardingStatus.mockRejectedValue(new Error('Netzwerkfehler'))

    const result = await onboardingGuard(route('Dashboard'))
    expect(result).toBe(true)
  })
})
