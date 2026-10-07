import { describe, expect, it } from 'vitest'
import router from '@/router'
import { deriveRunTabs } from '../runTabs'
import { deriveStages, type RunWorkspaceData } from '../runStageState'

const full = { simulationId: 'sim_1', projectId: 'proj_1', latestReportId: 'report_9' }

describe('deriveRunTabs', () => {
  it('sechs Reiter in fester Reihenfolge mit Route-Name und Params', () => {
    const tabs = deriveRunTabs(full)
    expect(tabs.map((t) => t.key)).toEqual(['overview', 'graph', 'personas', 'simulation', 'report', 'interviews'])
    expect(tabs.map((t) => t.to)).toEqual([
      { name: 'RunOverview', params: { simulationId: 'sim_1' } },
      { name: 'RunGraph', params: { simulationId: 'sim_1' } },
      { name: 'StepEnvSetup', params: { projectId: 'proj_1' } },
      { name: 'StepSimulationFeed', params: { simulationId: 'sim_1' } },
      { name: 'StepReport', params: { reportId: 'report_9' } },
      { name: 'RunInterviewsLegacy', params: { simulationId: 'sim_1' } },
    ])
    expect(tabs.every((t) => t.disabledReason === null)).toBe(true)
  })

  it('Personas ohne Projekt: deaktiviert mit Grund', () => {
    const t = deriveRunTabs({ ...full, projectId: null }).find((x) => x.key === 'personas')!
    expect(t).toMatchObject({ to: null, disabledReason: 'noProject' })
  })

  it('Bericht ohne Bericht: deaktiviert mit Grund', () => {
    const t = deriveRunTabs({ ...full, latestReportId: null }).find((x) => x.key === 'report')!
    expect(t).toMatchObject({ to: null, disabledReason: 'noReport' })
  })

  it('Interviews sind mit und ohne Bericht aktiv', () => {
    for (const latestReportId of [null, 'report_9']) {
      const t = deriveRunTabs({ ...full, latestReportId }).find((x) => x.key === 'interviews')!
      expect(t.to).toEqual({ name: 'RunInterviewsLegacy', params: { simulationId: 'sim_1' } })
    }
  })

  it('alle Ziele (Reiter und Stufen-Schritte) existieren im Router', () => {
    const data: RunWorkspaceData = { simulationId: 'sim_1', projectId: 'proj_1', hasGraph: false, jobs: {}, reports: [] }
    const names = [
      ...deriveRunTabs(full).map((t) => t.to?.name),
      ...deriveStages(data).map((r) => r.next.to?.name),
      'StepGraphBuild',
      'StepReport',
      'LibraryRuns',
    ].filter((n): n is string => !!n)
    for (const name of names) expect(router.hasRoute(name), name).toBe(true)
  })
})
