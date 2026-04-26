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

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const DEFAULT_FALLBACK = { kind: 'running', text: 'common.processing' }

export function useWorkspaceStatus({
  initial = 'processing',
  map = {},
  fallback = DEFAULT_FALLBACK,
} = {}) {
  const { t } = useI18n()
  const currentStatus = ref(initial)

  const entry = computed(() => map[currentStatus.value] ?? fallback)
  const statusKind = computed(() => entry.value.kind)
  const statusText = computed(() => t(entry.value.text))

  function updateStatus(next) {
    currentStatus.value = next
  }

  return { currentStatus, statusKind, statusText, updateStatus }
}
