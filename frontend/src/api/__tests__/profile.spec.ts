/**
 * profile — API-Client-Smokes (Onboarding Slice 2, Nachbesserung).
 *
 * Tests:
 *  1. completeOnboarding() spiegelt bei 409 "onboarding_incomplete" die
 *     TOP-LEVEL `missing`-Liste aus dem rohen Envelope nach `details.missing`.
 *  2. completeOnboarding() lässt andere Fehler unverändert durch.
 *  3. fetchAvatarBlob() gibt den Blob bei Erfolg zurück und ruft den
 *     authentifizierten service-Client mit responseType "blob" auf.
 *  4. fetchAvatarBlob() gibt bei jedem Fehler null zurück (Initialen-Fallback).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../envelope'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()

vi.mock('../index', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

import { completeOnboarding, fetchAvatarBlob } from '../profile'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('completeOnboarding — 409 onboarding_incomplete Wire-Format', () => {
  it('Test 1: spiegelt top-level `missing` aus dem rohen Envelope nach details.missing', async () => {
    const rawEnvelope = {
      success: false,
      error: 'onboarding incomplete',
      code: 'onboarding_incomplete',
      missing: ['profile_valid', 'chat_model_configured'],
    }
    mockPost.mockRejectedValue(
      new ApiError({
        code: 'onboarding_incomplete',
        status: 409,
        message: 'onboarding incomplete',
        originalResponse: rawEnvelope,
      }),
    )

    await expect(completeOnboarding()).rejects.toMatchObject({
      code: 'onboarding_incomplete',
      details: { missing: ['profile_valid', 'chat_model_configured'] },
    })
  })

  it('Test 2: lässt Fehler ohne top-level `missing` unverändert durch', async () => {
    const err = new ApiError({ code: 'unknown_error', status: 500, message: 'boom' })
    mockPost.mockRejectedValue(err)

    await expect(completeOnboarding()).rejects.toBe(err)
  })

  it('Test 2b: lässt Nicht-onboarding_incomplete-Fehler mit `missing` unangetastet', async () => {
    const err = new ApiError({
      code: 'display_name_required',
      status: 400,
      message: 'display_name required',
      originalResponse: { success: false, code: 'display_name_required', missing: ['x'] },
    })
    mockPost.mockRejectedValue(err)

    await expect(completeOnboarding()).rejects.toBe(err)
  })
})

describe('fetchAvatarBlob', () => {
  it('Test 3: gibt den Blob bei Erfolg zurück (authentifizierter service-Client, responseType blob)', async () => {
    const blob = new Blob(['x'], { type: 'image/png' })
    mockGet.mockResolvedValue(blob)

    await expect(fetchAvatarBlob()).resolves.toBe(blob)
    expect(mockGet).toHaveBeenCalledWith('/api/profile/avatar', { responseType: 'blob' })
  })

  it('Test 4: gibt bei jedem Fehler null zurück (Initialen-Fallback statt Crash)', async () => {
    mockGet.mockRejectedValue(new ApiError({ code: 'avatar_not_found', status: 404, message: 'no avatar' }))

    await expect(fetchAvatarBlob()).resolves.toBeNull()
  })
})
