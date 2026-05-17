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

import { computed, ref, type ComputedRef, type Ref } from 'vue'

export type WorkspaceMode = 'graph' | 'split' | 'workbench'

export interface WorkspaceModeOption {
  value: WorkspaceMode
  label: string
}

export interface PanelStyle {
  readonly width: string
  readonly opacity: number
}

export interface UseWorkspaceModeReturn {
  viewMode: Ref<WorkspaceMode>
  workspaceModes: WorkspaceModeOption[]
  leftPanelStyle: ComputedRef<PanelStyle>
  rightPanelStyle: ComputedRef<PanelStyle>
  toggleMaximize: (target: WorkspaceMode) => void
}

export const WORKSPACE_MODES: WorkspaceModeOption[] = [
  { value: 'graph', label: 'Graph' },
  { value: 'split', label: 'Split' },
  { value: 'workbench', label: 'Workbench' },
]

const FULL: PanelStyle = Object.freeze({ width: '100%', opacity: 1 })
const HALF: PanelStyle = Object.freeze({ width: '50%', opacity: 1 })
const HIDDEN: PanelStyle = Object.freeze({ width: '0%', opacity: 0 })

export function useWorkspaceMode(initialMode: WorkspaceMode = 'split'): UseWorkspaceModeReturn {
  const viewMode = ref<WorkspaceMode>(initialMode)

  const leftPanelStyle = computed<PanelStyle>(() => {
    if (viewMode.value === 'graph') return FULL
    if (viewMode.value === 'workbench') return HIDDEN
    return HALF
  })

  const rightPanelStyle = computed<PanelStyle>(() => {
    if (viewMode.value === 'workbench') return FULL
    if (viewMode.value === 'graph') return HIDDEN
    return HALF
  })

  /** Toggle behaviour: clicking the maximize button on a panel that's already
   *  maximized snaps back to split — matches the existing UX. */
  function toggleMaximize(target: WorkspaceMode): void {
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
