/**
 * usePersonaActions — Composable für Persona-Review-Aktionen (Sub-Slice 38, Refs #203).
 *
 * Extrahiert aus Step2EnvSetup.vue (Zeilen 82–214).
 *
 * Kapselt:
 *   - Approve / Reject / Regenerate / Edit-Logik
 *   - Status-Varianten-Mapping (statusVariant, issueBadgeVariant, statusLabel)
 *   - Inline-Edit-State (editingProfile, startEditingSelected, cancelEditing)
 *   - Patch-Helfer applyProfileToList
 *   - Computed hasRegeneratingPersona
 *
 * `selectedProfile` und `profiles` werden als Ref injiziert (aus useSimulationPrepare).
 * `addLog` ist ein Callback-Wrapper für `emit('add-log', ...)`.
 * `simulationId` ist eine Ref (reaktive Prop).
 * `t` kommt aus vue-i18n via `useI18n()` — damit Sprachumschaltung live greift.
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePersonaReview, type UsePersonaReviewReturn } from './usePersonaReview'
import type { ProfileRecord } from '../api/simulation'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_VARIANTS: Record<string, string> = {
  approved: 'success',
  pending: 'warn',
  rejected: 'error',
  regenerating: 'accent',
}

const SEVERITY_VARIANTS: Record<string, string> = {
  error: 'error',
  warning: 'warn',
  info: 'plasma',
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Editable working copy bound to the detail modal / inline editor. */
export interface EditingProfileState {
  username: string
  name: string
  bio: string
  persona: string
  profession: string
  country: string
  age: number | string | null
  gender: string
  mbti: string
  interested_topics: string
}

export interface UsePersonaActionsDeps {
  simulationId: Ref<string | null | undefined>
  profiles: Ref<ProfileRecord[]>
  selectedProfile: Ref<ProfileRecord | null>
  addLog: (msg: string) => void
}

export interface UsePersonaActionsReturn {
  // state
  editingProfile: Ref<EditingProfileState | null>
  reviewActionPending: Ref<boolean>
  reviewActionError: Ref<string>
  regenerateHint: Ref<string>
  // helpers
  statusVariant: (status: string) => string
  statusLabel: (status: string) => string
  issueBadgeVariant: (severity: string) => string
  // actions
  startEditingSelected: () => void
  cancelEditing: () => void
  applyProfileToList: (profile: Partial<ProfileRecord> & { username?: string }) => void
  approveSelected: () => Promise<void>
  rejectSelected: () => Promise<void>
  regenerateSelected: () => Promise<void>
  saveEditingProfile: () => Promise<void>
  // computed
  hasRegeneratingPersona: ComputedRef<boolean>
  // expose review composable for refreshQuality / quality state
  personaReview: UsePersonaReviewReturn
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function usePersonaActions(deps: UsePersonaActionsDeps): UsePersonaActionsReturn {
  const { simulationId, profiles, selectedProfile, addLog } = deps
  const { t } = useI18n()
  const personaReview = usePersonaReview()

  // --- State ---

  const editingProfile = ref<EditingProfileState | null>(null)
  const reviewActionPending = ref(false)
  const reviewActionError = ref('')
  const regenerateHint = ref('')

  // ---------------------------------------------------------------------------
  // Helpers — variant / label mapping
  // ---------------------------------------------------------------------------

  function statusVariant(status: string): string {
    return STATUS_VARIANTS[status] || 'ghost'
  }

  /**
   * statusLabel calls `t` at invocation time so that runtime language switches
   * are reflected immediately without re-initialising the composable.
   */
  function statusLabel(status: string): string {
    const labels: Record<string, string> = {
      approved: 'freigegeben',
      pending: 'offen',
      rejected: 'abgelehnt',
      regenerating: t('step2.persona.regeneratingPill'),
    }
    return labels[status] || status || '—'
  }

  function issueBadgeVariant(severity: string): string {
    return SEVERITY_VARIANTS[severity] || 'ghost'
  }

  // ---------------------------------------------------------------------------
  // Inline-edit state management
  // ---------------------------------------------------------------------------

  function startEditingSelected(): void {
    if (!selectedProfile.value) return
    const src = selectedProfile.value
    editingProfile.value = {
      username: (src.username as string) ?? '',
      name: (src.name as string) || '',
      bio: (src.bio as string) || '',
      persona: (src.persona as string) || '',
      profession: (src.profession as string) || '',
      country: (src.country as string) || '',
      age: (src.age as number | null) ?? null,
      gender: (src.gender as string) || 'other',
      mbti: (src.mbti as string) || '',
      interested_topics: Array.isArray(src.interested_topics)
        ? (src.interested_topics as string[]).join(', ')
        : (src.interested_topics as string) || '',
    }
    reviewActionError.value = ''
  }

  function cancelEditing(): void {
    editingProfile.value = null
    reviewActionError.value = ''
  }

  // ---------------------------------------------------------------------------
  // Patch helper — mutates profiles list + selectedProfile in-place
  // ---------------------------------------------------------------------------

  function applyProfileToList(profile: Partial<ProfileRecord> & { username?: string }): void {
    if (!profile?.username) return
    const idx = profiles.value.findIndex((p) => p.username === profile.username)
    if (idx >= 0) {
      profiles.value.splice(idx, 1, { ...profiles.value[idx], ...profile })
    }
    if (selectedProfile.value?.username === profile.username) {
      selectedProfile.value = { ...selectedProfile.value, ...profile }
    }
  }

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  async function approveSelected(): Promise<void> {
    if (!selectedProfile.value || !simulationId.value) return
    reviewActionPending.value = true
    reviewActionError.value = ''
    try {
      const data = await personaReview.approve(simulationId.value, selectedProfile.value.username)
      if (data) applyProfileToList(data)
      addLog(`Persona freigegeben: ${selectedProfile.value.username}`)
      await personaReview.refreshQuality(simulationId.value)
    } catch (err) {
      const e = err as { message?: string }
      reviewActionError.value = e.message ?? String(err)
    } finally {
      reviewActionPending.value = false
    }
  }

  async function rejectSelected(): Promise<void> {
    if (!selectedProfile.value || !simulationId.value) return
    reviewActionPending.value = true
    reviewActionError.value = ''
    try {
      const data = await personaReview.reject(simulationId.value, selectedProfile.value.username)
      if (data) applyProfileToList(data)
      addLog(`Persona abgelehnt: ${selectedProfile.value.username}`)
      await personaReview.refreshQuality(simulationId.value)
    } catch (err) {
      const e = err as { message?: string }
      reviewActionError.value = e.message ?? String(err)
    } finally {
      reviewActionPending.value = false
    }
  }

  async function regenerateSelected(): Promise<void> {
    if (!selectedProfile.value || !simulationId.value) return
    reviewActionPending.value = true
    reviewActionError.value = ''
    try {
      const hint = regenerateHint.value.trim() || undefined
      const data = await personaReview.regenerate(simulationId.value, selectedProfile.value.username, hint)
      if (data) applyProfileToList(data)
      addLog(`Persona wird neu generiert: ${selectedProfile.value.username}`)
      regenerateHint.value = ''
      await personaReview.refreshQuality(simulationId.value)
    } catch (err) {
      const e = err as { message?: string }
      reviewActionError.value = e.message ?? String(err)
    } finally {
      reviewActionPending.value = false
    }
  }

  async function saveEditingProfile(): Promise<void> {
    if (!editingProfile.value || !simulationId.value) return
    const payload: Record<string, unknown> = { ...editingProfile.value }
    const usernameForCall = payload.username as string
    delete payload.username
    if (typeof payload.interested_topics === 'string') {
      payload.interested_topics = (payload.interested_topics as string)
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    }
    if (payload.age === '' || payload.age === null) delete payload.age
    reviewActionPending.value = true
    reviewActionError.value = ''
    try {
      const data = await personaReview.editProfile(
        simulationId.value,
        usernameForCall,
        payload as Partial<ProfileRecord>,
      )
      if (data) applyProfileToList(data)
      addLog(`Persona bearbeitet: ${usernameForCall}`)
      editingProfile.value = null
      await personaReview.refreshQuality(simulationId.value)
    } catch (err) {
      const e = err as { message?: string }
      reviewActionError.value = e.message ?? String(err)
    } finally {
      reviewActionPending.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // Computed
  // ---------------------------------------------------------------------------

  const hasRegeneratingPersona: ComputedRef<boolean> = computed(() =>
    profiles.value.some((p) => p.review_status === 'regenerating')
  )

  // ---------------------------------------------------------------------------
  // Return
  // ---------------------------------------------------------------------------

  return {
    editingProfile,
    reviewActionPending,
    reviewActionError,
    regenerateHint,
    statusVariant,
    statusLabel,
    issueBadgeVariant,
    startEditingSelected,
    cancelEditing,
    applyProfileToList,
    approveSelected,
    rejectSelected,
    regenerateSelected,
    saveEditingProfile,
    hasRegeneratingPersona,
    personaReview,
  }
}
