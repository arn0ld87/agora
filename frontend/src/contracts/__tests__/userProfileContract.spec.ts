import { describe, expect, it } from 'vitest'

import userProfileJsonSchema from '../../../../schemas/user-profile.schema.json'
import userProfileUpdateJsonSchema from '../../../../schemas/user-profile-update-request.schema.json'
import onboardingStateJsonSchema from '../../../../schemas/onboarding-state.schema.json'
import onboardingStatusResponseJsonSchema from '../../../../schemas/onboarding-status-response.schema.json'
import onboardingStepUpdateJsonSchema from '../../../../schemas/onboarding-step-update-request.schema.json'

import {
  ONBOARDING_STEP_ORDER,
  OnboardingRequirementsSchema,
  OnboardingStateSchema,
  OnboardingStatusResponseSchema,
  OnboardingStepUpdateRequestSchema,
  UserProfileSchema,
  UserProfileUpdateRequestSchema,
} from '../userProfileContract'

describe('canonical user-profile / onboarding contracts', () => {
  it('keeps Zod top-level fields aligned with generated Pydantic schemas', () => {
    expect(Object.keys(UserProfileSchema.shape).sort()).toEqual(
      Object.keys(userProfileJsonSchema.properties).sort(),
    )
    expect(Object.keys(UserProfileUpdateRequestSchema.shape).sort()).toEqual(
      Object.keys(userProfileUpdateJsonSchema.properties).sort(),
    )
    expect(Object.keys(OnboardingStateSchema.shape).sort()).toEqual(
      Object.keys(onboardingStateJsonSchema.properties).sort(),
    )
    expect(Object.keys(OnboardingStatusResponseSchema.shape).sort()).toEqual(
      Object.keys(onboardingStatusResponseJsonSchema.properties).sort(),
    )
    expect(Object.keys(OnboardingStepUpdateRequestSchema.shape).sort()).toEqual(
      Object.keys(onboardingStepUpdateJsonSchema.properties).sort(),
    )
  })

  it('mirrors the canonical ONBOARDING_STEP_ORDER from the backend enum', () => {
    expect(ONBOARDING_STEP_ORDER).toEqual(
      onboardingStateJsonSchema.properties.current_step.enum,
    )
  })

  it('accepts a canonical, fully populated UserProfile', () => {
    const result = UserProfileSchema.safeParse({
      avatar_ref: 'avatar-0123456789abcdef0123456789abcdef.png',
      display_name: 'Alex Schneider',
      username: 'alex-s',
      role: 'Maintainer',
      organisation: 'Agora',
      language: 'de',
      timezone: 'Europe/Berlin',
      report_language: 'de',
      theme: 'system',
      privacy_mode: 'standard',
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(true)
  })

  it('accepts a minimal UserProfile (only display_name + timestamps) via defaults', () => {
    const result = UserProfileSchema.safeParse({
      display_name: 'Minimal',
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.avatar_ref).toBeNull()
      expect(result.data.language).toBe('de')
      expect(result.data.timezone).toBe('Europe/Berlin')
    }
  })

  it.each(['', '   ', '\n\t'])('rejects a blank display_name: %j', (blank) => {
    const result = UserProfileSchema.safeParse({
      display_name: blank,
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(false)
  })

  it.each([
    '../../etc/passwd',
    'avatar-../../etc/passwd.png',
    'avatar-abc.png', // zu kurz, kein 32-stelliger Hex-Block
    'avatar-0123456789abcdef0123456789abcdef.svg', // svg ist nie erlaubt
    '/etc/avatar-0123456789abcdef0123456789abcdef.png',
  ])('rejects a path-traversal / non-conforming avatar_ref: %s', (avatarRef) => {
    const result = UserProfileSchema.safeParse({
      avatar_ref: avatarRef,
      display_name: 'Alex',
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(false)
  })

  it('rejects an unknown current_step literal', () => {
    const result = OnboardingStateSchema.safeParse({
      status: 'in_progress',
      current_step: 'not-a-real-step',
      completed_steps: [],
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(false)
  })

  it('rejects an unknown step in completed_steps', () => {
    const result = OnboardingStateSchema.safeParse({
      completed_steps: ['welcome', 'not-a-real-step'],
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
    })
    expect(result.success).toBe(false)
  })

  it('rejects extra/unknown keys on UserProfile (strict)', () => {
    const result = UserProfileSchema.safeParse({
      display_name: 'Alex',
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
      unexpected_field: true,
    })
    expect(result.success).toBe(false)
  })

  it('rejects extra/unknown keys on UserProfileUpdateRequest (strict)', () => {
    expect(UserProfileUpdateRequestSchema.safeParse({ avatar_ref: 'x' }).success).toBe(false)
  })

  it('rejects extra/unknown keys on OnboardingState (strict)', () => {
    const result = OnboardingStateSchema.safeParse({
      created_at: '2026-07-11T00:00:00Z',
      updated_at: '2026-07-11T00:00:00Z',
      unexpected_field: true,
    })
    expect(result.success).toBe(false)
  })

  it('accepts a canonical OnboardingStatusResponse', () => {
    const result = OnboardingStatusResponseSchema.safeParse({
      state: {
        status: 'in_progress',
        operating_mode: 'local',
        current_step: 'profile',
        completed_steps: ['welcome'],
        created_at: '2026-07-11T00:00:00Z',
        updated_at: '2026-07-11T00:00:00Z',
      },
      requirements: {
        profile_valid: false,
        chat_model_configured: false,
        embedding_configured: false,
      },
      onboarding_required: true,
    })
    expect(result.success).toBe(true)
  })

  it('rejects OnboardingRequirements with missing required fields', () => {
    expect(OnboardingRequirementsSchema.safeParse({ profile_valid: true }).success).toBe(false)
  })

  it('accepts a canonical OnboardingStepUpdateRequest with and without operating_mode', () => {
    expect(OnboardingStepUpdateRequestSchema.safeParse({ step: 'welcome' }).success).toBe(true)
    expect(
      OnboardingStepUpdateRequestSchema.safeParse({ step: 'welcome', operating_mode: 'local' })
        .success,
    ).toBe(true)
    expect(
      OnboardingStepUpdateRequestSchema.safeParse({ step: 'not-a-real-step' }).success,
    ).toBe(false)
  })
})
