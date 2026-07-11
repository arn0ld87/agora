/**
 * userProfile — Pinia-Store für Benutzerprofil + resumierbares Onboarding
 * (Onboarding Slice 2).
 *
 * `ensureLoaded()` lädt Onboarding-Status + Profil genau einmal (In-Flight-
 * Dedupe über `loadPromise`). Ein API-Ausfall darf die App NIE sperren:
 * Fehlerpfad setzt `loaded = true` und `onboarding.onboardingRequired =
 * false`, damit der Router-Guard durchlässt statt zu blockieren.
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  completeOnboarding as apiCompleteOnboarding,
  completeOnboardingStep,
  deleteAvatar as apiDeleteAvatar,
  dismissOnboarding as apiDismissOnboarding,
  fetchAvatarBlob,
  getOnboardingStatus,
  getProfile,
  reopenOnboarding as apiReopenOnboarding,
  updateProfile as apiUpdateProfile,
  uploadAvatar as apiUploadAvatar,
} from '../api/profile'
import type {
  OnboardingRequirements,
  OnboardingState,
  OnboardingStepId,
  OperatingMode,
  UserProfile,
  UserProfileUpdateRequest,
} from '../contracts/userProfileContract'

interface OnboardingSlice {
  state: OnboardingState | null
  requirements: OnboardingRequirements | null
  onboardingRequired: boolean
}

function _errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback
}

export const useUserProfileStore = defineStore('userProfile', () => {
  const profile = ref<UserProfile | null>(null)
  const onboarding = ref<OnboardingSlice>({
    state: null,
    requirements: null,
    onboardingRequired: false,
  })
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  /** Object-URL des per Blob geladenen Avatars — primärer Anzeigepfad (s. api/profile.ts::fetchAvatarBlob). */
  const avatarObjectUrl = ref<string | null>(null)

  /** Bequemer Top-Level-Zugriff, u.a. für den Router-Guard. */
  const onboardingRequired = computed(() => onboarding.value.onboardingRequired)

  let loadPromise: Promise<void> | null = null

  /** Revoked die aktuelle Object-URL (falls vorhanden) — immer vor Ersatz/Wegfall aufrufen. */
  function _releaseAvatarObjectUrl(): void {
    if (avatarObjectUrl.value) {
      URL.revokeObjectURL(avatarObjectUrl.value)
      avatarObjectUrl.value = null
    }
  }

  /**
   * Lädt den Avatar als Blob neu und ersetzt die Object-URL; ohne avatar_ref
   * bleibt sie leer. Schlägt der Blob-Load fehl, bleibt die App beim
   * Initialen-Fallback — ein Avatar-Ladefehler darf nie den Profil-/
   * Onboarding-Load selbst zum Scheitern bringen.
   */
  async function _refreshAvatarPreview(): Promise<void> {
    _releaseAvatarObjectUrl()
    if (!profile.value?.avatar_ref) return
    try {
      const blob = await fetchAvatarBlob()
      if (blob) {
        avatarObjectUrl.value = URL.createObjectURL(blob)
      }
    } catch {
      // Initialen-Fallback bleibt — kein sichtbarer Fehler nötig.
    }
  }

  async function _load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [profileResult, onboardingResult] = await Promise.all([
        getProfile(),
        getOnboardingStatus(),
      ])
      profile.value = profileResult
      onboarding.value = {
        state: onboardingResult.state,
        requirements: onboardingResult.requirements,
        onboardingRequired: onboardingResult.onboarding_required,
      }
      await _refreshAvatarPreview()
    } catch (err) {
      // Fail-open: niemals die App sperren, nur sichtbaren Fehler setzen.
      error.value = _errorMessage(err, 'Profil/Onboarding konnten nicht geladen werden.')
      onboarding.value = { ...onboarding.value, onboardingRequired: false }
    } finally {
      loading.value = false
      loaded.value = true
    }
  }

  /** Lädt Profil + Onboarding-Status genau einmal; wiederholte Aufrufe sind No-Ops. */
  function ensureLoaded(): Promise<void> {
    if (loaded.value) return Promise.resolve()
    if (!loadPromise) {
      loadPromise = _load().finally(() => {
        loadPromise = null
      })
    }
    return loadPromise
  }

  /** Erzwingt einen frischen Reload (z.B. nach externem State-Change). */
  async function refresh(): Promise<void> {
    loaded.value = false
    await ensureLoaded()
  }

  async function updateProfile(req: UserProfileUpdateRequest): Promise<void> {
    error.value = null
    try {
      profile.value = await apiUpdateProfile(req)
    } catch (err) {
      error.value = _errorMessage(err, 'Profil konnte nicht gespeichert werden.')
      throw err
    }
  }

  async function uploadAvatar(file: File): Promise<void> {
    error.value = null
    try {
      profile.value = await apiUploadAvatar(file)
      await _refreshAvatarPreview()
    } catch (err) {
      error.value = _errorMessage(err, 'Avatar-Upload fehlgeschlagen.')
      throw err
    }
  }

  async function deleteAvatar(): Promise<void> {
    error.value = null
    try {
      profile.value = await apiDeleteAvatar()
      await _refreshAvatarPreview()
    } catch (err) {
      error.value = _errorMessage(err, 'Avatar konnte nicht gelöscht werden.')
      throw err
    }
  }

  async function completeStep(
    step: OnboardingStepId,
    operatingMode?: OperatingMode | null,
  ): Promise<void> {
    error.value = null
    try {
      const nextState = await completeOnboardingStep(step, operatingMode)
      onboarding.value = { ...onboarding.value, state: nextState }
    } catch (err) {
      error.value = _errorMessage(err, 'Schritt konnte nicht gespeichert werden.')
      throw err
    }
  }

  async function complete(): Promise<void> {
    error.value = null
    try {
      const nextState = await apiCompleteOnboarding()
      onboarding.value = { ...onboarding.value, state: nextState, onboardingRequired: false }
    } catch (err) {
      error.value = _errorMessage(err, 'Einrichtung konnte nicht abgeschlossen werden.')
      throw err
    }
  }

  async function dismiss(): Promise<void> {
    error.value = null
    try {
      const nextState = await apiDismissOnboarding()
      onboarding.value = { ...onboarding.value, state: nextState, onboardingRequired: false }
    } catch (err) {
      error.value = _errorMessage(err, 'Onboarding konnte nicht übersprungen werden.')
      throw err
    }
  }

  async function reopen(): Promise<void> {
    error.value = null
    try {
      const nextState = await apiReopenOnboarding()
      onboarding.value = { ...onboarding.value, state: nextState, onboardingRequired: true }
    } catch (err) {
      error.value = _errorMessage(err, 'Onboarding konnte nicht erneut geöffnet werden.')
      throw err
    }
  }

  /** Explizites Aufräumen der aktuellen Avatar-Object-URL (z.B. bei App-Teardown). */
  function disposeAvatarPreview(): void {
    _releaseAvatarObjectUrl()
  }

  return {
    profile,
    onboarding,
    onboardingRequired,
    avatarObjectUrl,
    loaded,
    loading,
    error,
    ensureLoaded,
    refresh,
    updateProfile,
    uploadAvatar,
    deleteAvatar,
    completeStep,
    complete,
    dismiss,
    reopen,
    disposeAvatarPreview,
  }
})
