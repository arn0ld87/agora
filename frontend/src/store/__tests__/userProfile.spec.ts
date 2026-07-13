/**
 * userProfile-Store — Vitest-Smokes (Onboarding Slice 2).
 *
 * Tests:
 *  1. ensureLoaded() lädt Profil + Onboarding genau einmal (In-Flight-Dedupe).
 *  2. ensureLoaded() ist idempotent nach erfolgreichem Laden (kein zweiter Call).
 *  3. Fehlerpfad: kein Lockout — loaded=true, onboardingRequired=false.
 *  4. refresh() erzwingt einen neuen Load.
 *  5. updateProfile()/uploadAvatar()/deleteAvatar() aktualisieren `profile`.
 *  6. completeStep()/complete()/dismiss()/reopen() aktualisieren `onboarding.state`.
 *  8. Avatar-Blob-Preview: lädt nach Profil-Load + nach Upload neu und
 *     revoked die alte Object-URL, bevor die neue erzeugt wird.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api/profile', () => ({
  getProfile: vi.fn(),
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
  fetchAvatarBlob: vi.fn(),
  getOnboardingStatus: vi.fn(),
  completeOnboardingStep: vi.fn(),
  completeOnboarding: vi.fn(),
  dismissOnboarding: vi.fn(),
  reopenOnboarding: vi.fn(),
}))

import {
  completeOnboarding,
  completeOnboardingStep,
  deleteAvatar,
  dismissOnboarding,
  fetchAvatarBlob,
  getOnboardingStatus,
  getProfile,
  reopenOnboarding,
  updateProfile,
  uploadAvatar,
} from '../../api/profile'
import { useUserProfileStore } from '../userProfile'
import type {
  OnboardingState,
  OnboardingStatusResponse,
  UserProfile,
  UserProfileUpdateRequest,
} from '../../contracts/userProfileContract'

type MockFn = ReturnType<typeof vi.fn>
const _getProfile = getProfile as unknown as MockFn
const _updateProfile = updateProfile as unknown as MockFn
const _uploadAvatar = uploadAvatar as unknown as MockFn
const _deleteAvatar = deleteAvatar as unknown as MockFn
const _fetchAvatarBlob = fetchAvatarBlob as unknown as MockFn
const _getOnboardingStatus = getOnboardingStatus as unknown as MockFn
const _completeOnboardingStep = completeOnboardingStep as unknown as MockFn
const _completeOnboarding = completeOnboarding as unknown as MockFn
const _dismissOnboarding = dismissOnboarding as unknown as MockFn
const _reopenOnboarding = reopenOnboarding as unknown as MockFn

function makeProfile(overrides: Partial<UserProfile> = {}): UserProfile {
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
    ...overrides,
  }
}

function makeOnboardingState(overrides: Partial<OnboardingState> = {}): OnboardingState {
  return {
    status: 'in_progress',
    operating_mode: null,
    current_step: 'welcome',
    completed_steps: [],
    created_at: '2026-07-11T00:00:00Z',
    updated_at: '2026-07-11T00:00:00Z',
    ...overrides,
  }
}

function makeUpdateRequest(overrides: Partial<UserProfileUpdateRequest> = {}): UserProfileUpdateRequest {
  return {
    display_name: 'Neuer Name',
    username: null,
    role: null,
    organisation: null,
    language: null,
    timezone: null,
    report_language: null,
    theme: null,
    privacy_mode: null,
    ...overrides,
  }
}

function makeOnboardingStatus(
  overrides: Partial<OnboardingStatusResponse> = {},
): OnboardingStatusResponse {
  return {
    state: makeOnboardingState(),
    requirements: {
      profile_valid: false,
      chat_model_configured: false,
      embedding_configured: false,
      embedding_source: 'none',
    },
    onboarding_required: true,
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('useUserProfileStore', () => {
  it('Test 1: ensureLoaded() lädt Profil + Onboarding genau einmal (In-Flight-Dedupe)', async () => {
    const profile = makeProfile()
    const status = makeOnboardingStatus()
    _getProfile.mockResolvedValue(profile)
    _getOnboardingStatus.mockResolvedValue(status)

    const store = useUserProfileStore()
    // Zwei parallele Aufrufe dürfen nur EINEN API-Roundtrip auslösen.
    await Promise.all([store.ensureLoaded(), store.ensureLoaded()])

    expect(_getProfile).toHaveBeenCalledTimes(1)
    expect(_getOnboardingStatus).toHaveBeenCalledTimes(1)
    expect(store.profile).toEqual(profile)
    expect(store.onboarding.state).toEqual(status.state)
    expect(store.onboarding.requirements).toEqual(status.requirements)
    expect(store.onboardingRequired).toBe(true)
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('Test 2: ensureLoaded() ist nach erfolgreichem Laden idempotent', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const store = useUserProfileStore()
    await store.ensureLoaded()
    await store.ensureLoaded()

    expect(_getProfile).toHaveBeenCalledTimes(1)
    expect(_getOnboardingStatus).toHaveBeenCalledTimes(1)
  })

  it('Test 3: Fehlerpfad sperrt die App nicht (loaded=true, onboardingRequired=false)', async () => {
    _getProfile.mockRejectedValue(new Error('Backend offline'))
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const store = useUserProfileStore()
    await store.ensureLoaded()

    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
    expect(store.onboardingRequired).toBe(false)
    expect(store.error).toBe('Backend offline')
  })

  it('Test 4: refresh() erzwingt einen neuen Load-Zyklus', async () => {
    _getProfile.mockResolvedValue(makeProfile())
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())

    const store = useUserProfileStore()
    await store.ensureLoaded()
    await store.refresh()

    expect(_getProfile).toHaveBeenCalledTimes(2)
    expect(_getOnboardingStatus).toHaveBeenCalledTimes(2)
  })

  it('Test 5: updateProfile()/uploadAvatar()/deleteAvatar() aktualisieren `profile`', async () => {
    const store = useUserProfileStore()

    const updated = makeProfile({ display_name: 'Neuer Name' })
    _updateProfile.mockResolvedValue(updated)
    await store.updateProfile(makeUpdateRequest())
    expect(store.profile).toEqual(updated)

    const withAvatar = makeProfile({
      display_name: 'Neuer Name',
      avatar_ref: 'avatar-0123456789abcdef0123456789abcdef.png',
    })
    _uploadAvatar.mockResolvedValue(withAvatar)
    await store.uploadAvatar(new File(['x'], 'a.png', { type: 'image/png' }))
    expect(store.profile?.avatar_ref).toBe('avatar-0123456789abcdef0123456789abcdef.png')

    const withoutAvatar = makeProfile({ display_name: 'Neuer Name', avatar_ref: null })
    _deleteAvatar.mockResolvedValue(withoutAvatar)
    await store.deleteAvatar()
    expect(store.profile?.avatar_ref).toBeNull()
  })

  it('Test 6: completeStep()/complete()/dismiss()/reopen() aktualisieren `onboarding.state`', async () => {
    const store = useUserProfileStore()
    store.onboarding.onboardingRequired = true

    const afterWelcome = makeOnboardingState({ current_step: 'profile', completed_steps: ['welcome'] })
    _completeOnboardingStep.mockResolvedValue(afterWelcome)
    await store.completeStep('welcome', 'local')
    expect(store.onboarding.state).toEqual(afterWelcome)

    const completed = makeOnboardingState({ status: 'completed', current_step: 'summary' })
    _completeOnboarding.mockResolvedValue(completed)
    await store.complete()
    expect(store.onboarding.state).toEqual(completed)
    expect(store.onboardingRequired).toBe(false)

    const dismissed = makeOnboardingState({ status: 'dismissed' })
    _dismissOnboarding.mockResolvedValue(dismissed)
    await store.dismiss()
    expect(store.onboarding.state).toEqual(dismissed)
    expect(store.onboardingRequired).toBe(false)

    const reopened = makeOnboardingState({ status: 'in_progress' })
    _reopenOnboarding.mockResolvedValue(reopened)
    await store.reopen()
    expect(store.onboarding.state).toEqual(reopened)
    expect(store.onboardingRequired).toBe(true)
  })

  it('Test 7: Fehlgeschlagene Mutation wirft und setzt `error`', async () => {
    const store = useUserProfileStore()
    _updateProfile.mockRejectedValue(new Error('Validierungsfehler'))

    await expect(
      store.updateProfile(makeUpdateRequest({ display_name: '' })),
    ).rejects.toThrow('Validierungsfehler')
    expect(store.error).toBe('Validierungsfehler')
  })

  it('Test 8: Avatar-Blob-Preview lädt nach Profil-Load und nach Upload neu, revoked alte Object-URL', async () => {
    let objectUrlCounter = 0
    const createObjectUrlSpy = vi
      .spyOn(URL, 'createObjectURL')
      .mockImplementation(() => `blob:mock-${++objectUrlCounter}`)
    const revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)

    const avatarBlobA = new Blob(['a'], { type: 'image/png' })
    const avatarBlobB = new Blob(['b'], { type: 'image/png' })

    const profileWithAvatar = makeProfile({
      avatar_ref: 'avatar-0123456789abcdef0123456789abcdef.png',
    })
    _getProfile.mockResolvedValue(profileWithAvatar)
    _getOnboardingStatus.mockResolvedValue(makeOnboardingStatus())
    _fetchAvatarBlob.mockResolvedValueOnce(avatarBlobA)

    const store = useUserProfileStore()
    await store.ensureLoaded()

    // Nach Profil-Load: Blob wurde geladen, Object-URL gesetzt.
    expect(_fetchAvatarBlob).toHaveBeenCalledTimes(1)
    expect(store.avatarObjectUrl).toBe('blob:mock-1')
    expect(revokeObjectUrlSpy).not.toHaveBeenCalled()

    // Upload: neue avatar_ref → Blob wird neu geladen, alte Object-URL revoked.
    const profileWithNewAvatar = makeProfile({
      avatar_ref: 'avatar-fedcba9876543210fedcba9876543210.webp',
    })
    _uploadAvatar.mockResolvedValue(profileWithNewAvatar)
    _fetchAvatarBlob.mockResolvedValueOnce(avatarBlobB)

    await store.uploadAvatar(new File(['b'], 'b.webp', { type: 'image/webp' }))

    expect(_fetchAvatarBlob).toHaveBeenCalledTimes(2)
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:mock-1')
    expect(store.avatarObjectUrl).toBe('blob:mock-2')

    // Delete: avatar_ref wird null → Preview wird revoked und geleert.
    _deleteAvatar.mockResolvedValue(makeProfile({ avatar_ref: null }))
    await store.deleteAvatar()

    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:mock-2')
    expect(store.avatarObjectUrl).toBeNull()
    // Kein Avatar mehr gesetzt → kein dritter fetchAvatarBlob-Call nötig.
    expect(_fetchAvatarBlob).toHaveBeenCalledTimes(2)

    createObjectUrlSpy.mockRestore()
    revokeObjectUrlSpy.mockRestore()
  })
})
