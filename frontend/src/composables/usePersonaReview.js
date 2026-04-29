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

import { computed, reactive, ref } from 'vue'
import {
  approveSimulationProfile,
  editSimulationProfile,
  getSimulationProfilesQuality,
  rejectSimulationProfile,
} from '../api/simulation'

const SEVERITY_RANK = { error: 3, warning: 2, info: 1 }

export function usePersonaReview() {
  const reviewEnabled = ref(false)
  const summary = ref(null)
  const globalIssues = ref([])
  const issuesByUsername = reactive(new Map())
  const isLoading = ref(false)
  const error = ref(null)

  function getIssuesFor(username) {
    return issuesByUsername.get(username) || []
  }

  function highestSeverityFor(username) {
    const issues = getIssuesFor(username)
    let highest = null
    for (const issue of issues) {
      if (!highest || SEVERITY_RANK[issue.severity] > SEVERITY_RANK[highest]) {
        highest = issue.severity
      }
    }
    return highest
  }

  function applyReport(payload) {
    summary.value = payload?.summary || null
    globalIssues.value = payload?.global_issues || []
    reviewEnabled.value = !!payload?.review_enabled
    issuesByUsername.clear()
    for (const entry of payload?.personas || []) {
      issuesByUsername.set(entry.username, entry.issues || [])
    }
  }

  async function refreshQuality(simulationId) {
    if (!simulationId) return null
    isLoading.value = true
    error.value = null
    try {
      const res = await getSimulationProfilesQuality(simulationId)
      if (res?.success) {
        applyReport(res.data)
        return res.data
      }
      error.value = res?.error || 'Quality-Report konnte nicht geladen werden.'
      return null
    } catch (err) {
      error.value = err?.message || 'Quality-Report konnte nicht geladen werden.'
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function approve(simulationId, username, notes) {
    const res = await approveSimulationProfile(simulationId, username, notes)
    if (!res?.success) {
      throw new Error(res?.error || 'Approve fehlgeschlagen.')
    }
    return res.data
  }

  async function reject(simulationId, username, reason) {
    const res = await rejectSimulationProfile(simulationId, username, reason)
    if (!res?.success) {
      throw new Error(res?.error || 'Reject fehlgeschlagen.')
    }
    return res.data
  }

  async function editProfile(simulationId, username, data) {
    const res = await editSimulationProfile(simulationId, username, data)
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
    editProfile,
  }
}
