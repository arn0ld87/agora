import { describe, expect, it } from 'vitest'
import {
  deriveHeadline,
  deriveStages,
  wallClockSeconds,
  type JobInfo,
  type ReportInfo,
  type RunWorkspaceData,
  type StageRow,
} from '../runStageState'

function job(runType: string, over: Partial<JobInfo> = {}): JobInfo {
  return {
    runId: `run_${runType}`,
    runType,
    status: 'completed',
    terminationReason: null,
    startedAt: '2026-10-05T10:00:00Z',
    completedAt: '2026-10-05T10:04:12Z',
    updatedAt: '2026-10-05T10:04:12Z',
    models: ['gpt-5.1'],
    usage: { durationSec: 10, tokens: 1000, costMicros: 410000 },
    error: null,
    ...over,
  }
}

function report(over: Partial<ReportInfo> = {}): ReportInfo {
  return {
    reportId: 'report_1',
    status: 'completed',
    missingSections: 0,
    createdAt: '2026-10-05T11:00:00Z',
    degradations: [],
    evidence: 'ok',
    ...over,
  }
}

function data(over: Partial<RunWorkspaceData> = {}): RunWorkspaceData {
  return { simulationId: 'sim_1', projectId: 'proj_1', hasGraph: true, jobs: {}, reports: [], ...over }
}

const row = (rows: StageRow[], key: StageRow['key']): StageRow => rows.find((r) => r.key === key)!

describe('deriveStages: Zustand je Stufe', () => {
  it('liefert fünf Zeilen in fester Reihenfolge, leerer Lauf = nicht gestartet', () => {
    const rows = deriveStages(data({ hasGraph: false }))
    expect(rows.map((r) => r.key)).toEqual(['graph', 'personas', 'simulation', 'report', 'interviews'])
    expect(row(rows, 'graph').state).toBe('notStarted')
    expect(row(rows, 'simulation').state).toBe('notStarted')
    expect(row(rows, 'interviews').state).toBe('notRecorded')
  })

  it.each([
    ['processing', null, 'running'],
    ['pending', null, 'queued'],
    ['paused', null, 'paused'],
    ['completed', null, 'done'],
    ['stopped', 'user_stop', 'stopped'],
    ['failed', 'process_restart', 'failed'],
    ['failed', 'error', 'failed'],
    ['failed', 'budget_tokens', 'budget'],
    ['stopped', 'budget_cost', 'budget'],
  ])('Job %s / %s -> %s', (status, reason, expected) => {
    const rows = deriveStages(
      data({ jobs: { simulation_run: job('simulation_run', { status, terminationReason: reason }) } }),
    )
    expect(row(rows, 'simulation').state).toBe(expected)
  })

  it('process_restart bleibt fehlgeschlagen und nennt den Grund', () => {
    const r = row(
      deriveStages(data({ jobs: { simulation_run: job('simulation_run', { status: 'failed', terminationReason: 'process_restart' }) } })),
      'simulation',
    )
    expect(r.terminationReason).toBe('process_restart')
    expect(r.state).not.toBe('stopped')
  })

  it('Berichtsstatus incomplete wird nie als fertig geführt', () => {
    const rows = deriveStages(
      data({
        jobs: { report_generate: job('report_generate') },
        reports: [report({ status: 'incomplete', missingSections: 2 })],
      }),
    )
    const r = row(rows, 'report')
    expect(r.state).toBe('incomplete')
    expect(r.state).not.toBe('done')
    expect(r.degradations.map((d) => d.code)).toContain('missingSections')
    expect(r.degradations.find((d) => d.code === 'missingSections')?.count).toBe(2)
  })

  it('fertiger Bericht mit fehlenden Abschnitten ist unvollständig', () => {
    const r = row(deriveStages(data({ reports: [report({ missingSections: 1 })] })), 'report')
    expect(r.state).toBe('incomplete')
  })

  it('evidence_omitted macht den Bericht mit Einschränkung, nicht fertig', () => {
    const r = row(deriveStages(data({ reports: [report({ evidence: 'omitted' })] })), 'report')
    expect(r.state).toBe('degraded')
    expect(r.degradations.map((d) => d.code)).toContain('evidenceOmitted')
  })

  it('Fallback-Personas (aus dem Bericht) machen die Personas-Stufe zu "Mit Fallback"', () => {
    const rows = deriveStages(
      data({
        jobs: { simulation_prepare: job('simulation_prepare') },
        reports: [report({ degradations: [{ component: 'persona_generation', reason: '3 Personas regelbasiert', severity: 'warning' }] })],
      }),
    )
    const p = row(rows, 'personas')
    expect(p.state).toBe('fallback')
    expect(p.degradations[0]).toMatchObject({ code: 'persona_generation', detail: '3 Personas regelbasiert' })
    expect(row(rows, 'report').degradations.map((d) => d.code)).not.toContain('persona_generation')
  })

  it('blockierende Degradation (Abbruch) macht den Bericht unvollständig', () => {
    const r = row(
      deriveStages(data({ reports: [report({ degradations: [{ component: 'run_cancellation', reason: 'x', severity: 'blocking' }] })] })),
      'report',
    )
    expect(r.state).toBe('incomplete')
  })

  it('Run-, Simulations- und Berichtsebene bleiben getrennt', () => {
    const rows = deriveStages(
      data({
        jobs: { simulation_run: job('simulation_run', { status: 'failed', terminationReason: 'error' }) },
        reports: [report()],
      }),
    )
    expect(row(rows, 'simulation').state).toBe('failed')
    expect(row(rows, 'report').state).toBe('done')
  })

  it('terminaler Job schlägt einen veralteten "generating"-Bericht', () => {
    const rows = deriveStages(
      data({
        jobs: { report_generate: job('report_generate', { status: 'stopped', terminationReason: 'user_stop' }) },
        reports: [report({ status: 'generating' })],
      }),
    )
    expect(row(rows, 'report').state).toBe('stopped')
  })

  it('aktiver Berichts-Job gewinnt', () => {
    const rows = deriveStages(
      data({ jobs: { report_generate: job('report_generate', { status: 'processing' }) }, reports: [report({ status: 'incomplete' })] }),
    )
    expect(row(rows, 'report').state).toBe('running')
  })

  it('fehlender früherer Job bei späterer Spur heißt "nicht erfasst", nicht "nicht gestartet"', () => {
    const rows = deriveStages(data({ hasGraph: false, jobs: { simulation_run: job('simulation_run') } }))
    expect(row(rows, 'graph').state).toBe('notRecorded')
    expect(row(rows, 'personas').state).toBe('notRecorded')
  })

  it('Graph ohne Job, aber mit Graph im Projekt: nicht erfasst', () => {
    expect(row(deriveStages(data({ hasGraph: true })), 'graph').state).toBe('notRecorded')
  })
})

describe('deriveStages: genau ein nächster Schritt', () => {
  it('jede Zeile trägt genau einen Schritt mit Ziel oder Grund', () => {
    for (const d of [
      data({ hasGraph: false }),
      data({ jobs: { simulation_run: job('simulation_run') }, reports: [report()] }),
      data({ projectId: null }),
    ]) {
      for (const r of deriveStages(d)) {
        expect(['start', 'resume', 'view']).toContain(r.next.kind)
        expect(Boolean(r.next.to) !== Boolean(r.next.disabledReason)).toBe(true)
      }
    }
  })

  it('Ziele nutzen Route-Namen mit Params', () => {
    const rows = deriveStages(
      data({
        jobs: {
          graph_build: job('graph_build'),
          simulation_prepare: job('simulation_prepare'),
          simulation_run: job('simulation_run'),
        },
        reports: [report()],
      }),
    )
    expect(row(rows, 'graph').next).toMatchObject({ kind: 'view', to: { name: 'RunGraph', params: { simulationId: 'sim_1' } } })
    expect(row(rows, 'personas').next.to).toEqual({ name: 'StepEnvSetup', params: { projectId: 'proj_1' } })
    expect(row(rows, 'simulation').next.to).toEqual({ name: 'RunSimulationFeed', params: { simulationId: 'sim_1' } })
    expect(row(rows, 'report').next).toMatchObject({ kind: 'view', to: { name: 'StepReport', params: { reportId: 'report_1' } } })
    expect(row(rows, 'interviews').next.to).toEqual({ name: 'RunInterviewsLegacy', params: { simulationId: 'sim_1' } })
  })

  it('gestoppte Simulation: Fortsetzen; nicht gestartet: Starten', () => {
    const stopped = deriveStages(
      data({ jobs: { simulation_run: job('simulation_run', { status: 'stopped', terminationReason: 'user_stop' }) } }),
    )
    expect(row(stopped, 'simulation').next).toMatchObject({ kind: 'resume', to: { name: 'StepSimulation' } })
    expect(row(deriveStages(data({ hasGraph: false })), 'simulation').next.kind).toBe('start')
  })

  it('Bericht ohne Bericht: deaktiviert vor der Simulation, Starten danach', () => {
    const before = row(deriveStages(data({ hasGraph: false })), 'report').next
    expect(before).toMatchObject({ kind: 'start', to: null, disabledReason: 'afterSimulation' })
    const after = row(deriveStages(data({ jobs: { simulation_run: job('simulation_run') } })), 'report').next
    expect(after).toMatchObject({ kind: 'start', to: { name: 'StepSimulation' } })
  })

  it('ohne Projekt sind Personas deaktiviert mit Grund', () => {
    const p = row(deriveStages(data({ projectId: null })), 'personas').next
    expect(p.to).toBeNull()
    expect(p.disabledReason).toBe('noProject')
  })
})

describe('deriveStages: vorgemerkte Startparameter (#1799)', () => {
  const startQuery = { maxRounds: '12', simulationDays: '3' }
  const plain = { name: 'StepSimulation', params: { simulationId: 'sim_1' } }

  it('Start und Fortsetzen der Simulation tragen die Startquery', () => {
    const start = row(deriveStages(data({ hasGraph: false }), startQuery), 'simulation').next
    expect(start).toMatchObject({ kind: 'start', to: { name: 'StepSimulation', query: startQuery } })
    const stopped = deriveStages(
      data({ jobs: { simulation_run: job('simulation_run', { status: 'stopped', terminationReason: 'user_stop' }) } }),
      startQuery,
    )
    expect(row(stopped, 'simulation').next.to).toMatchObject({ name: 'StepSimulation', query: startQuery })
  })

  it('der Berichtsstart über die Simulation trägt sie ebenfalls', () => {
    const rows = deriveStages(data({ jobs: { simulation_run: job('simulation_run') } }), startQuery)
    expect(row(rows, 'report').next.to).toMatchObject({ name: 'StepSimulation', query: startQuery })
  })

  it('ohne Eintrag (leere oder fehlende Query) bleibt das Ziel unverändert', () => {
    expect(row(deriveStages(data({ hasGraph: false }), {}), 'simulation').next.to).toEqual(plain)
    expect(row(deriveStages(data({ hasGraph: false })), 'simulation').next.to).toEqual(plain)
  })

  it('andere Ziele (Ansehen, Personas, Interviews) bekommen keine Query', () => {
    const rows = deriveStages(
      data({ jobs: { simulation_prepare: job('simulation_prepare'), simulation_run: job('simulation_run') } }),
      startQuery,
    )
    expect(row(rows, 'personas').next.to).not.toHaveProperty('query')
    expect(row(rows, 'simulation').next.to).not.toHaveProperty('query')
    expect(row(rows, 'interviews').next.to).not.toHaveProperty('query')
  })
})

describe('deriveHeadline', () => {
  it('laufende Stufe gewinnt', () => {
    const rows = deriveStages(
      data({
        jobs: {
          graph_build: job('graph_build', { updatedAt: '2026-10-05T12:00:00Z' }),
          simulation_run: job('simulation_run', { status: 'processing' }),
        },
      }),
    )
    expect(deriveHeadline(rows)).toEqual({ stage: 'simulation', state: 'running' })
  })

  it('sonst die zuletzt bewegte Stufe, ohne auf die Pipeline zu schließen', () => {
    const rows = deriveStages(
      data({
        jobs: {
          graph_build: job('graph_build'),
          simulation_run: job('simulation_run', { status: 'failed', terminationReason: 'error', updatedAt: '2026-10-05T13:00:00Z' }),
        },
      }),
    )
    expect(deriveHeadline(rows)).toEqual({ stage: 'simulation', state: 'failed' })
  })

  it('leerer Lauf hat keine Kopfmarke', () => {
    expect(deriveHeadline(deriveStages(data({ hasGraph: false })))).toBeNull()
  })
})

describe('wallClockSeconds', () => {
  it('Wanduhr aus Start und Ende, sonst null', () => {
    expect(wallClockSeconds({ startedAt: '2026-10-05T10:00:00Z', completedAt: '2026-10-05T10:04:12Z' })).toBe(252)
    expect(wallClockSeconds({ startedAt: '2026-10-05T10:00:00Z', completedAt: null })).toBeNull()
  })
})
