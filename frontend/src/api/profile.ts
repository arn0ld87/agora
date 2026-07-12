/**
 * User-Profile & Onboarding — API-Client (Onboarding Slice 2).
 *
 * Envelope-Handling wie in api/llmProfiles.ts: `unwrapAndParse` liest
 * `response.data` (den Envelope-Body) aus und validiert strict per Zod.
 * Die `{"profile": ...}`/`{"state": ...}`-Hüllen sind keine eigenen
 * Pydantic-Modelle im Backend — die lokalen Wrapper-Schemas hier bilden
 * nur die tatsächliche Endpunkt-Antwortform ab, nicht den Contract selbst.
 */
import { z } from 'zod'
import service from './index'
import { ApiError, isApiError } from './envelope'
import { unwrapAndParse } from './parse'
import {
  OnboardingStateSchema,
  OnboardingStatusResponseSchema,
  OnboardingStepUpdateRequestSchema,
  UserProfileSchema,
  UserProfileUpdateRequestSchema,
  type OnboardingState,
  type OnboardingStatusResponse,
  type OnboardingStepId,
  type OperatingMode,
  type UserProfile,
  type UserProfileUpdateRequest,
} from '../contracts/userProfileContract'

const ProfileNullableResponseSchema = z.object({ profile: UserProfileSchema.nullable() }).strict()
const ProfileResponseSchema = z.object({ profile: UserProfileSchema }).strict()
const OnboardingStateResponseSchema = z.object({ state: OnboardingStateSchema }).strict()

export async function getProfile(): Promise<UserProfile | null> {
  const res = await service.get('/api/profile')
  return unwrapAndParse(res, ProfileNullableResponseSchema).profile
}

export async function updateProfile(req: UserProfileUpdateRequest): Promise<UserProfile> {
  const body = UserProfileUpdateRequestSchema.parse(req)
  const res = await service.put('/api/profile', body)
  return unwrapAndParse(res, ProfileResponseSchema).profile
}

export async function uploadAvatar(file: File): Promise<UserProfile> {
  const form = new FormData()
  form.append('file', file)
  const res = await service.post('/api/profile/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return unwrapAndParse(res, ProfileResponseSchema).profile
}

export async function deleteAvatar(): Promise<UserProfile | null> {
  const res = await service.delete('/api/profile/avatar')
  return unwrapAndParse(res, ProfileNullableResponseSchema).profile
}

/**
 * Lädt die Avatar-Datei als Blob über den authentifizierten `service`-Client
 * (Auth-Header via Interceptor, s. api/index.ts). Das ist der primäre
 * Anzeigepfad: Aufrufer erzeugen daraus per `URL.createObjectURL` eine
 * Object-URL fürs `<img>`-Tag. Jeder Fehler (kein Avatar gesetzt, 401, …)
 * liefert `null` — Aufrufer fallen dann auf den Initialen-Fallback zurück.
 */
export async function fetchAvatarBlob(): Promise<Blob | null> {
  try {
    const res = await service.get('/api/profile/avatar', { responseType: 'blob' })
    return res instanceof Blob ? res : null
  } catch {
    return null
  }
}

/**
 * Baut die Avatar-Bild-URL als Pfad-Referenz (Cache-Buster über
 * `avatar_ref`). Interner Hilfs-Helper — NICHT mehr der primäre Anzeigepfad
 * (siehe `fetchAvatarBlob`), da ein direktes `<img src>` im
 * token-geschützten Modus (`AGORA_AUTH_TOKEN` gesetzt) keinen Auth-Header
 * mitschicken kann und mit 401 fehlschlägt.
 */
export function avatarUrl(avatarRef: string | null | undefined): string | null {
  if (!avatarRef) return null
  const base = import.meta.env.VITE_API_BASE_URL || ''
  return `${base}/api/profile/avatar?v=${encodeURIComponent(avatarRef)}`
}

export async function getOnboardingStatus(): Promise<OnboardingStatusResponse> {
  const res = await service.get('/api/onboarding')
  return unwrapAndParse(res, OnboardingStatusResponseSchema)
}

export async function completeOnboardingStep(
  step: OnboardingStepId,
  operatingMode?: OperatingMode | null,
): Promise<OnboardingState> {
  const body = OnboardingStepUpdateRequestSchema.parse({
    step,
    operating_mode: operatingMode ?? null,
  })
  const res = await service.put('/api/onboarding/step', body)
  return unwrapAndParse(res, OnboardingStateResponseSchema).state
}

/**
 * Wire-Format-Anpassung: `POST /api/onboarding/complete` liefert bei 409
 * `{"success": false, "code": "onboarding_incomplete", "missing": [...]}` —
 * `missing` liegt TOP-LEVEL im Envelope, es gibt kein `details`-Feld. Der
 * globale Interceptor (api/index.ts) kennt nur `details`/`error`/`code`, das
 * `missing`-Array würde sonst verworfen. Diese lokale Normalisierung liest
 * `missing` aus dem rohen Envelope (`ApiError.originalResponse`) und spiegelt
 * es nach `details.missing`, damit Aufrufer einheitlich `err.details?.missing`
 * lesen können, ohne den globalen Wrapper anzufassen.
 */
function _normalizeOnboardingIncompleteError(err: unknown): unknown {
  if (!isApiError(err) || err.code !== 'onboarding_incomplete') return err
  const raw = err.originalResponse as { missing?: unknown } | null | undefined
  const missing = Array.isArray(raw?.missing) ? raw.missing.map(String) : undefined
  if (!missing) return err
  return new ApiError({
    code: err.code,
    status: err.status,
    message: err.message,
    details: { ...err.details, missing },
    originalResponse: err.originalResponse,
  })
}

export async function completeOnboarding(): Promise<OnboardingState> {
  try {
    const res = await service.post('/api/onboarding/complete')
    return unwrapAndParse(res, OnboardingStateResponseSchema).state
  } catch (err) {
    throw _normalizeOnboardingIncompleteError(err)
  }
}

export async function dismissOnboarding(): Promise<OnboardingState> {
  const res = await service.post('/api/onboarding/dismiss')
  return unwrapAndParse(res, OnboardingStateResponseSchema).state
}

export async function reopenOnboarding(): Promise<OnboardingState> {
  const res = await service.post('/api/onboarding/reopen')
  return unwrapAndParse(res, OnboardingStateResponseSchema).state
}
