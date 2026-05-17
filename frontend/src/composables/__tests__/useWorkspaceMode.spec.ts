import { describe, it, expect } from 'vitest'
import { useWorkspaceMode } from '../useWorkspaceMode'

describe('useWorkspaceMode', () => {
  describe('Default-Modus: split', () => {
    it('viewMode ist initial split', () => {
      const { viewMode } = useWorkspaceMode()

      expect(viewMode.value).toBe('split')
    })

    it('leftPanelStyle ist { width: "50%", opacity: 1 } im split-Modus', () => {
      const { leftPanelStyle } = useWorkspaceMode()

      expect(leftPanelStyle.value).toEqual({ width: '50%', opacity: 1 })
    })

    it('rightPanelStyle ist { width: "50%", opacity: 1 } im split-Modus', () => {
      const { rightPanelStyle } = useWorkspaceMode()

      expect(rightPanelStyle.value).toEqual({ width: '50%', opacity: 1 })
    })
  })

  describe('initialMode: graph', () => {
    it('leftPanelStyle ist FULL (100%/1)', () => {
      const { leftPanelStyle } = useWorkspaceMode('graph')

      expect(leftPanelStyle.value).toEqual({ width: '100%', opacity: 1 })
    })

    it('rightPanelStyle ist HIDDEN (0%/0)', () => {
      const { rightPanelStyle } = useWorkspaceMode('graph')

      expect(rightPanelStyle.value).toEqual({ width: '0%', opacity: 0 })
    })
  })

  describe('initialMode: workbench', () => {
    it('leftPanelStyle ist HIDDEN (0%/0)', () => {
      const { leftPanelStyle } = useWorkspaceMode('workbench')

      expect(leftPanelStyle.value).toEqual({ width: '0%', opacity: 0 })
    })

    it('rightPanelStyle ist FULL (100%/1)', () => {
      const { rightPanelStyle } = useWorkspaceMode('workbench')

      expect(rightPanelStyle.value).toEqual({ width: '100%', opacity: 1 })
    })
  })

  describe('toggleMaximize', () => {
    it('von split → toggleMaximize("graph") → viewMode wird graph', () => {
      const { viewMode, toggleMaximize } = useWorkspaceMode('split')

      toggleMaximize('graph')

      expect(viewMode.value).toBe('graph')
    })

    it('von graph → toggleMaximize("graph") → zurück zu split', () => {
      const { viewMode, toggleMaximize } = useWorkspaceMode('split')

      toggleMaximize('graph')
      toggleMaximize('graph')

      expect(viewMode.value).toBe('split')
    })

    it('von split → toggleMaximize("workbench") → viewMode wird workbench', () => {
      const { viewMode, toggleMaximize } = useWorkspaceMode('split')

      toggleMaximize('workbench')

      expect(viewMode.value).toBe('workbench')
    })

    it('Panel-Styles reagieren reaktiv auf toggleMaximize', () => {
      const { leftPanelStyle, rightPanelStyle, toggleMaximize } = useWorkspaceMode('split')

      toggleMaximize('graph')

      expect(leftPanelStyle.value).toEqual({ width: '100%', opacity: 1 })
      expect(rightPanelStyle.value).toEqual({ width: '0%', opacity: 0 })
    })
  })

  describe('Object.freeze-Invariante', () => {
    it('leftPanelStyle im split-Modus ist eingefroren', () => {
      const { leftPanelStyle } = useWorkspaceMode('split')

      expect(Object.isFrozen(leftPanelStyle.value)).toBe(true)
    })

    it('leftPanelStyle im graph-Modus ist eingefroren', () => {
      const { leftPanelStyle } = useWorkspaceMode('graph')

      expect(Object.isFrozen(leftPanelStyle.value)).toBe(true)
    })

    it('Mutation von leftPanelStyle.value.width schlägt fehl oder wird ignoriert', () => {
      const { leftPanelStyle } = useWorkspaceMode('split')

      try {
        ;(leftPanelStyle.value as any).width = '1%'
      } catch {
        // strict-mode wirft — das ist korrekt
      }

      expect(leftPanelStyle.value.width).not.toBe('1%')
    })
  })

  describe('workspaceModes', () => {
    it('enthält alle drei Modi', () => {
      const { workspaceModes } = useWorkspaceMode()

      expect(workspaceModes.map((m) => m.value)).toEqual(['graph', 'split', 'workbench'])
    })

    it('negativer Case: workspaceModes enthält keinen unbekannten Mode', () => {
      const { workspaceModes } = useWorkspaceMode()

      const values = workspaceModes.map((m) => m.value)
      expect(values).not.toContain('fullscreen')
    })
  })
})
