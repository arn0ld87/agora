/**
 * Canonical Zod mirror of backend/app/contracts/user_profile_contract.py.
 *
 * ADR-0008: Agora ist ein Single-User-System. `UserProfile` beschreibt die
 * lokale Person und ihre Einstellungen — kein KI-Preset (siehe
 * `llmProfileContract.ts`). `OnboardingState` ist der backendseitig
 * persistierte, resumierbare Zustand des Erst-Onboardings.
 *
 * Der `completed`-Status erfordert serverseitig bestimmte `completed_steps`
 * (siehe `REQUIRED_ONBOARDING_STEPS` im Backend-Contract) — diese
 * Cross-Field-Regel wird hier bewusst NICHT nachgebaut, der Zod-Spiegel
 * validiert nur die strukturelle Form.
 */
import { z } from 'zod'

// === Literale (müssen exakt den Pydantic-Literalen entsprechen) ===
export const ProfileLanguageSchema = z.enum(['de', 'en'])
export type ProfileLanguage = z.infer<typeof ProfileLanguageSchema>

export const ProfileThemeSchema = z.enum(['system', 'light', 'dark'])
export type ProfileTheme = z.infer<typeof ProfileThemeSchema>

export const PrivacyModeSchema = z.enum(['standard', 'strict'])
export type PrivacyMode = z.infer<typeof PrivacyModeSchema>

export const OperatingModeSchema = z.enum(['local', 'hybrid', 'server'])
export type OperatingMode = z.infer<typeof OperatingModeSchema>

export const OnboardingStatusSchema = z.enum([
  'not_started',
  'in_progress',
  'dismissed',
  'completed',
])
export type OnboardingStatus = z.infer<typeof OnboardingStatusSchema>

export const OnboardingStepIdSchema = z.enum([
  'welcome',
  'profile',
  'providers',
  'chat_model',
  'embeddings',
  'privacy',
  'summary',
])
export type OnboardingStepId = z.infer<typeof OnboardingStepIdSchema>

/** Kanonische Schritt-Reihenfolge des Wizards — 1:1 zu ONBOARDING_STEP_ORDER im Backend. */
export const ONBOARDING_STEP_ORDER: readonly OnboardingStepId[] = [
  'welcome',
  'profile',
  'providers',
  'chat_model',
  'embeddings',
  'privacy',
  'summary',
] as const

// === Avatar-Referenz (Path-Traversal- und Fremdnamen-sicher per Pattern) ===
const _AVATAR_REF_PATTERN = /^avatar-[0-9a-f]{32}\.(png|jpg|webp)$/
export const AvatarRefSchema = z.string().regex(_AVATAR_REF_PATTERN)

const _USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{1,31}$/
export const UsernameSchema = z.string().regex(_USERNAME_PATTERN)

/** display_name: min/max wie im Backend + Blank-Check (Backend strippt + verwirft Leerstrings). */
const _DisplayNameSchema = z
  .string()
  .min(1)
  .max(80)
  .refine((value) => value.trim().length > 0, {
    message: 'display_name must not be blank',
  })

// === UserProfile ===
export const UserProfileSchema = z
  .object({
    avatar_ref: AvatarRefSchema.nullable().default(null),
    display_name: _DisplayNameSchema,
    username: UsernameSchema.nullable().default(null),
    role: z.string().max(120).nullable().default(null),
    organisation: z.string().max(120).nullable().default(null),
    language: ProfileLanguageSchema.default('de'),
    timezone: z.string().default('Europe/Berlin'),
    report_language: ProfileLanguageSchema.default('de'),
    theme: ProfileThemeSchema.default('system'),
    privacy_mode: PrivacyModeSchema.default('standard'),
    created_at: z.string(), // ISO-String (datetime serialisiert als str)
    updated_at: z.string(),
  })
  .strict()
export type UserProfile = z.infer<typeof UserProfileSchema>

// === UserProfileUpdateRequest (avatar_ref bewusst ausgeschlossen) ===
export const UserProfileUpdateRequestSchema = z
  .object({
    display_name: _DisplayNameSchema.nullable().default(null),
    username: UsernameSchema.nullable().default(null),
    role: z.string().max(120).nullable().default(null),
    organisation: z.string().max(120).nullable().default(null),
    language: ProfileLanguageSchema.nullable().default(null),
    timezone: z.string().nullable().default(null),
    report_language: ProfileLanguageSchema.nullable().default(null),
    theme: ProfileThemeSchema.nullable().default(null),
    privacy_mode: PrivacyModeSchema.nullable().default(null),
  })
  .strict()
export type UserProfileUpdateRequest = z.infer<typeof UserProfileUpdateRequestSchema>

// === OnboardingState ===
export const OnboardingStateSchema = z
  .object({
    status: OnboardingStatusSchema.default('not_started'),
    operating_mode: OperatingModeSchema.nullable().default(null),
    current_step: OnboardingStepIdSchema.default('welcome'),
    completed_steps: z.array(OnboardingStepIdSchema).default([]),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strict()
export type OnboardingState = z.infer<typeof OnboardingStateSchema>

// === OnboardingStepUpdateRequest ===
export const OnboardingStepUpdateRequestSchema = z
  .object({
    step: OnboardingStepIdSchema,
    operating_mode: OperatingModeSchema.nullable().default(null),
  })
  .strict()
export type OnboardingStepUpdateRequest = z.infer<typeof OnboardingStepUpdateRequestSchema>

// === OnboardingRequirements ===
export const OnboardingRequirementsSchema = z
  .object({
    profile_valid: z.boolean(),
    chat_model_configured: z.boolean(),
    embedding_configured: z.boolean(),
  })
  .strict()
export type OnboardingRequirements = z.infer<typeof OnboardingRequirementsSchema>

// === OnboardingStatusResponse (GET /api/onboarding) ===
export const OnboardingStatusResponseSchema = z
  .object({
    state: OnboardingStateSchema,
    requirements: OnboardingRequirementsSchema,
    onboarding_required: z.boolean(),
  })
  .strict()
export type OnboardingStatusResponse = z.infer<typeof OnboardingStatusResponseSchema>
