/**
 * Composable for the Slice 2 persona review surface.
 *
 * Wraps the backend endpoints introduced in Slice 2.1/2.2:
 *   GET    /api/simulation/<sim>/profiles/quality
 *   PATCH  /api/simulation/<sim>/profiles/<username>
 *   POST   /api/simulation/<sim>/profiles/<username>/approve
 *   POST   /api/simulation/<sim>/profiles/<username>/reject
 *
 * Keeps a small reactive cache so persona cards and the editor drawer can read
 * status/issues without re-fetching on every render.
 */

import { computed, reactive, ref, type ComputedRef, type Ref } from 'vue'
import {
  approveSimulationProfile,
  editSimulationProfile,
  getSimulationProfilesQuality,
  rejectSimulationProfile,
  regenerateSimulationProfile,
  type ProfileRecord,
} from '../api/simulation'

// reason: the service interceptor returns the raw envelope body at runtime;
// the API type declarations claim the unwrapped type but the composable checks
// `res?.success` — we cast via `unknown` to the actual runtime shape.
interface QualityEnvelope {
  success?: boolean
  error?: string
  data?: {
    summary?: string | null
    global_issues?: IssueSeverityEntry[]
    review_enabled?: boolean
    personas?: Array<{ username: string; issues?: IssueSeverityEntry[] }>
  }
}

interface ProfileEnvelope {
  success?: boolean
  error?: string
  data?: ProfileRecord
}

export type IssueSeverity = 'error' | 'warning' | 'info'

export interface IssueSeverityEntry {
  severity: IssueSeverity
  message?: string
  [key: string]: unknown
}

export interface UsePersonaReviewReturn {
  reviewEnabled: Ref<boolean>
  summary: Ref<string | null>
  globalIssues: Ref<IssueSeverityEntry[]>
  hasGlobalIssues: ComputedRef<boolean>
  issuesByUsername: Map<string, IssueSeverityEntry[]>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  getIssuesFor: (username: string) => IssueSeverityEntry[]
  highestSeverityFor: (username: string) => IssueSeverity | null
  refreshQuality: (simulationId: string) => Promise<QualityEnvelope['data'] | null>
  approve: (simulationId: string, username: string, notes?: string) => Promise<ProfileRecord | undefined>
  reject: (simulationId: string, username: string, reason?: string) => Promise<ProfileRecord | undefined>
  regenerate: (simulationId: string, username: string, hint?: string) => Promise<ProfileRecord | undefined>
  editProfile: (simulationId: string, username: string, data: Partial<ProfileRecord>) => Promise<ProfileRecord | undefined>
}

const SEVERITY_RANK: Record<IssueSeverity, number> = { error: 3, warning: 2, info: 1 }

export function usePersonaReview(): UsePersonaReviewReturn {
  const reviewEnabled = ref(false)
  const summary = ref<string | null>(null)
  const globalIssues = ref<IssueSeverityEntry[]>([])
  const issuesByUsername = reactive(new Map<string, IssueSeverityEntry[]>())
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  function getIssuesFor(username: string): IssueSeverityEntry[] {
    return issuesByUsername.get(username) || []
  }

  function highestSeverityFor(username: string): IssueSeverity | null {
    const issues = getIssuesFor(username)
    let highest: IssueSeverity | null = null
    for (const issue of issues) {
      if (!highest || SEVERITY_RANK[issue.severity] > SEVERITY_RANK[highest]) {
        highest = issue.severity
      }
    }
    return highest
  }

  function applyReport(payload: QualityEnvelope['data']): void {
    summary.value = payload?.summary || null
    globalIssues.value = payload?.global_issues || []
    reviewEnabled.value = !!payload?.review_enabled
    issuesByUsername.clear()
    for (const entry of payload?.personas || []) {
      issuesByUsername.set(entry.username, entry.issues || [])
    }
  }

  async function refreshQuality(simulationId: string): Promise<QualityEnvelope['data'] | null> {
    if (!simulationId) return null
    isLoading.value = true
    error.value = null
    try {
      // reason: service interceptor returns raw envelope body at runtime;
      // getSimulationProfilesQuality is typed as the unwrapped type in api/simulation.ts
      const res = (await getSimulationProfilesQuality(simulationId)) as unknown as QualityEnvelope
      if (res?.success) {
        applyReport(res.data)
        return res.data ?? null
      }
      error.value = res?.error || 'Quality-Report konnte nicht geladen werden.'
      return null
    } catch (err) {
      const e = err as { message?: string }
      error.value = e?.message || 'Quality-Report konnte nicht geladen werden.'
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function approve(
    simulationId: string,
    username: string,
    notes?: string
  ): Promise<ProfileRecord | undefined> {
    // reason: service interceptor returns raw envelope body at runtime
    const res = (await approveSimulationProfile(simulationId, username, notes)) as unknown as ProfileEnvelope
    if (!res?.success) {
      throw new Error(res?.error || 'Approve fehlgeschlagen.')
    }
    return res.data
  }

  async function reject(
    simulationId: string,
    username: string,
    reason?: string
  ): Promise<ProfileRecord | undefined> {
    // reason: service interceptor returns raw envelope body at runtime
    const res = (await rejectSimulationProfile(simulationId, username, reason)) as unknown as ProfileEnvelope
    if (!res?.success) {
      throw new Error(res?.error || 'Reject fehlgeschlagen.')
    }
    return res.data
  }

  async function regenerate(
    simulationId: string,
    username: string,
    hint?: string
  ): Promise<ProfileRecord | undefined> {
    // reason: service interceptor returns raw envelope body at runtime
    const res = (await regenerateSimulationProfile(simulationId, username, hint)) as unknown as ProfileEnvelope
    if (!res?.success) {
      throw new Error(res?.error || 'Regenerate fehlgeschlagen.')
    }
    return res.data
  }

  async function editProfile(
    simulationId: string,
    username: string,
    data: Partial<ProfileRecord>
  ): Promise<ProfileRecord | undefined> {
    // reason: service interceptor returns raw envelope body at runtime
    const res = (await editSimulationProfile(simulationId, username, data)) as unknown as ProfileEnvelope
    if (!res?.success) {
      throw new Error(res?.error || 'Edit fehlgeschlagen.')
    }
    return res.data
  }

  const hasGlobalIssues = computed(() => globalIssues.value.length > 0)

  return {
    reviewEnabled,
    summary,
    globalIssues,
    hasGlobalIssues,
    issuesByUsername,
    isLoading,
    error,
    getIssuesFor,
    highestSeverityFor,
    refreshQuality,
    approve,
    reject,
    regenerate,
    editProfile,
  }
}
