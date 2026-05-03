/**
 * EPIC-03 ST-02 — Workspace Status Composable.
 *
 * Removes the duplicated currentStatus/statusKind/statusText boilerplate from
 * SimulationView, SimulationRunView, ReportView and InteractionView. The
 * mapping is data-driven so each view only declares its own status →
 * (kind, i18n-key) pairs.
 *
 * Resolves i18n keys eagerly via useI18n() so the call-sites only consume
 * `statusText` directly — no extra computed wrapper needed.
 *
 * MainView is intentionally NOT migrated to this: its status is derived from
 * `currentPhase + error` rather than a single status string. SimulationRunView
 * still owns its `isPaused` overlay computeds and uses this only for the
 * underlying currentStatus ref + updateStatus setter.
 *
 * Usage:
 *   const { currentStatus, statusKind, statusText, updateStatus } =
 *     useWorkspaceStatus({
 *       initial: 'processing',
 *       map: {
 *         error:     { kind: 'error', text: 'common.error' },
 *         completed: { kind: 'done',  text: 'common.completed' },
 *       },
 *       fallback: { kind: 'running', text: 'common.processing' },
 *     })
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'

export interface StatusMapEntry {
  kind: string
  text: string
}

export interface UseWorkspaceStatusOptions {
  initial?: string
  map?: Record<string, StatusMapEntry>
  fallback?: StatusMapEntry
}

export interface UseWorkspaceStatusReturn {
  currentStatus: Ref<string>
  statusKind: ComputedRef<string>
  statusText: ComputedRef<string>
  updateStatus: (next: string) => void
}

const DEFAULT_FALLBACK: StatusMapEntry = { kind: 'running', text: 'common.processing' }

export function useWorkspaceStatus({
  initial = 'processing',
  map = {},
  fallback = DEFAULT_FALLBACK,
}: UseWorkspaceStatusOptions = {}): UseWorkspaceStatusReturn {
  const { t } = useI18n()
  const currentStatus = ref(initial)

  const entry = computed<StatusMapEntry>(() => map[currentStatus.value] ?? fallback)
  const statusKind = computed<string>(() => entry.value.kind)
  const statusText = computed<string>(() => t(entry.value.text))

  function updateStatus(next: string): void {
    currentStatus.value = next
  }

  return { currentStatus, statusKind, statusText, updateStatus }
}
