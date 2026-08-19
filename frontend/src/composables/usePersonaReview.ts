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
  type ProfileQualityResponse,
  type ProfileQualitySummary,
  type ProfileRecord,
} from '../api/simulation'

export type IssueSeverity = 'error' | 'warning' | 'info'

export interface IssueSeverityEntry {
  severity: IssueSeverity
  message?: string
  [key: string]: unknown
}

export interface UsePersonaReviewReturn {
  reviewEnabled: Ref<boolean>
  summary: Ref<ProfileQualitySummary | null>
  globalIssues: Ref<IssueSeverityEntry[]>
  hasGlobalIssues: ComputedRef<boolean>
  issuesByUsername: Map<string, IssueSeverityEntry[]>
  isLoading: Ref<boolean>
  error: Ref<string | null>
  getIssuesFor: (username: string) => IssueSeverityEntry[]
  highestSeverityFor: (username: string) => IssueSeverity | null
  refreshQuality: (simulationId: string) => Promise<ProfileQualityResponse | null>
  approve: (simulationId: string, username: string, notes?: string) => Promise<ProfileRecord | undefined>
  reject: (simulationId: string, username: string, reason?: string) => Promise<ProfileRecord | undefined>
  regenerate: (simulationId: string, username: string, hint?: string) => Promise<ProfileRecord | undefined>
  editProfile: (simulationId: string, username: string, data: Partial<ProfileRecord>) => Promise<ProfileRecord | undefined>
}

const SEVERITY_RANK: Record<IssueSeverity, number> = { error: 3, warning: 2, info: 1 }

export function usePersonaReview(): UsePersonaReviewReturn {
  const reviewEnabled = ref(false)
  const summary = ref<ProfileQualitySummary | null>(null)
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

  // reason: ProfileQualityResponse (src/api/simulation.ts) only declares
  // `simulation_id`/`profiles` explicitly and falls back to an index signature
  // of `unknown` for everything else — it does not describe the
  // summary/global_issues/review_enabled/personas shape the backend actually
  // sends here (verified against no other typed consumer of these fields).
  // That's a pre-existing gap in the (out-of-scope) API type, not something
  // this composable should paper over with a cast — so the fields are read
  // through explicit runtime narrowing instead.
  function applyReport(payload: ProfileQualityResponse): void {
    // summary ist ein OBJEKT mit Zaehlern (total/approved/pending/…),
    // kein Text — siehe persona_quality_service.py::_build_summary. Der
    // frueher hier deklarierte `string` war eine Typluege, die nur
    // niemandem aufgefallen ist, weil bisher keine Ansicht den Wert liest.
    summary.value = payload.summary ?? null
    globalIssues.value = (payload.global_issues ?? []) as IssueSeverityEntry[]
    reviewEnabled.value = !!payload.review_enabled
    issuesByUsername.clear()
    const personas = Array.isArray(payload.personas) ? payload.personas : []
    for (const entry of personas) {
      const username = typeof entry.username === 'string' ? entry.username : ''
      if (!username) continue
      issuesByUsername.set(username, (entry.issues ?? []) as IssueSeverityEntry[])
    }
  }

  async function refreshQuality(simulationId: string): Promise<ProfileQualityResponse | null> {
    if (!simulationId) return null
    isLoading.value = true
    error.value = null
    try {
      const res = await getSimulationProfilesQuality(simulationId)
      if (!res.success) {
        error.value = res.error || 'Quality-Report konnte nicht geladen werden.'
        return null
      }
      applyReport(res.data)
      return res.data
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
    const res = await approveSimulationProfile(simulationId, username, notes)
    if (!res.success) {
      throw new Error(res.error || 'Approve fehlgeschlagen.')
    }
    return res.data
  }

  async function reject(
    simulationId: string,
    username: string,
    reason?: string
  ): Promise<ProfileRecord | undefined> {
    const res = await rejectSimulationProfile(simulationId, username, reason)
    if (!res.success) {
      throw new Error(res.error || 'Reject fehlgeschlagen.')
    }
    return res.data
  }

  async function regenerate(
    simulationId: string,
    username: string,
    hint?: string
  ): Promise<ProfileRecord | undefined> {
    const res = await regenerateSimulationProfile(simulationId, username, hint)
    if (!res.success) {
      throw new Error(res.error || 'Regenerate fehlgeschlagen.')
    }
    return res.data
  }

  async function editProfile(
    simulationId: string,
    username: string,
    data: Partial<ProfileRecord>
  ): Promise<ProfileRecord | undefined> {
    const res = await editSimulationProfile(simulationId, username, data)
    if (!res.success) {
      throw new Error(res.error || 'Edit fehlgeschlagen.')
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
