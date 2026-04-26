/**
 * EPIC-03 ST-03 — Workspace ViewMode Composable.
 *
 * Pulls the graph/split/workbench mode logic out of the five pipeline views
 * (MainView, SimulationView, SimulationRunView, ReportView, InteractionView)
 * which previously held identical 12-line copies of viewMode + the two
 * panel-style computeds + toggleMaximize.
 *
 * Usage:
 *   const { viewMode, workspaceModes, leftPanelStyle, rightPanelStyle, toggleMaximize }
 *     = useWorkspaceMode('split')   // or 'workbench' / 'graph'
 *   <WorkspaceModeSwitch :current-mode="viewMode" :modes="workspaceModes" @update:mode="viewMode = $event" />
 *   <WorkspaceSplit :left-style="leftPanelStyle" :right-style="rightPanelStyle">
 */

import { computed, ref } from 'vue'

export const WORKSPACE_MODES = [
  { value: 'graph', label: 'Graph' },
  { value: 'split', label: 'Split' },
  { value: 'workbench', label: 'Workbench' },
]

const FULL = { width: '100%', opacity: 1 }
const HALF = { width: '50%', opacity: 1 }
const HIDDEN = { width: '0%', opacity: 0 }

export function useWorkspaceMode(initialMode = 'split') {
  const viewMode = ref(initialMode)

  const leftPanelStyle = computed(() => {
    if (viewMode.value === 'graph') return FULL
    if (viewMode.value === 'workbench') return HIDDEN
    return HALF
  })

  const rightPanelStyle = computed(() => {
    if (viewMode.value === 'workbench') return FULL
    if (viewMode.value === 'graph') return HIDDEN
    return HALF
  })

  /** Toggle behaviour: clicking the maximize button on a panel that's already
   *  maximized snaps back to split — matches the existing UX. */
  function toggleMaximize(target) {
    viewMode.value = viewMode.value === target ? 'split' : target
  }

  return {
    viewMode,
    workspaceModes: WORKSPACE_MODES,
    leftPanelStyle,
    rightPanelStyle,
    toggleMaximize,
  }
}
