/**
 * Bibliothek der Laeufe (#1797): reine Ableitung der Zustaende, Stufen,
 * Filter und Fassungen. Die Zustaende duerfen nie zusammenfallen.
 */
import { describe, it, expect } from 'vitest'
import { deriveLibraryCounts } from '../../useLibraryCounts'
import { parseReportVersions } from '../reportVersions'
import {
  buildRunEntries,
  deriveRunState,
  deriveStages,
  filterRuns,
  parseRunsView,
  reportStatusState,
  STATE_GLYPH,
  type LibraryState,
} from '../runState'
import type { ShelfLaufJob, ShelfObject } from '@/types/shelf'

function job(runType: string, status: string, opts: { reason?: string; sim?: string; message?: string } = {}): ShelfLaufJob {
  return {
    runId: `run_${runType}_${status}`,
    runType,
    status,
    message: opts.message ?? '',
    updatedAt: '2026-10-06T10:00:00Z',
    terminationReason: opts.reason ?? null,
    linkedIds: opts.sim ? { simulation_id: opts.sim } : {},
  }
}

function lauf(id: string, jobs: ShelfLaufJob[], extra: Partial<ShelfObject> = {}): ShelfObject {
  return {
    kind: 'lauf', id, title: `Quelle ${id}`, statusLine: '', updatedAt: '2026-10-06T10:00:00Z', metaId: id,
    nextAction: null, active: null, jobs, ...extra,
  }
}

function bericht(id: string, sim: string, status: string, title = `Frage ${id}`, updatedAt = '2026-10-06T11:00:00Z'): ShelfObject {
  return {
    kind: 'bericht', id, title, statusLine: '', updatedAt, metaId: id,
    simulationId: sim, reportStatus: status, nextAction: null, active: null,
  }
}

function stateOf(l: ShelfObject, reports: ShelfObject[] = []): LibraryState {
  return deriveRunState(l, reports)
}

describe('deriveRunState — sechs getrennte Zustaende', () => {
  it('laeuft (pending und processing)', () => {
    expect(stateOf(lauf('a', [job('simulation_run', 'processing')]))).toBe('running')
    expect(stateOf(lauf('a', [job('simulation_run', 'pending')]))).toBe('running')
  })

  it('fertig', () => {
    expect(stateOf(lauf('a', [job('report_generate', 'completed')]), [bericht('r', 'a', 'completed')])).toBe('done')
  })

  it('unvollstaendig (INCOMPLETE) ist NICHT fertig', () => {
    const l = lauf('a', [job('report_generate', 'completed')])
    const state = stateOf(l, [bericht('r', 'a', 'incomplete')])
    expect(state).toBe('incomplete')
    expect(state).not.toBe('done')
    expect(STATE_GLYPH.incomplete).not.toBe(STATE_GLYPH.done)
  })

  it('gestoppt (user_stop)', () => {
    expect(stateOf(lauf('a', [job('simulation_run', 'stopped', { reason: 'user_stop' })]))).toBe('stopped')
  })

  it('Budget erschoepft, auch wenn der Job als failed oder stopped endet', () => {
    expect(stateOf(lauf('a', [job('simulation_run', 'failed', { reason: 'budget_tokens' })]))).toBe('budget')
    expect(stateOf(lauf('a', [job('simulation_run', 'stopped', { reason: 'budget_cost' })]))).toBe('budget')
  })

  it('fehlgeschlagen, auch process_restart', () => {
    expect(stateOf(lauf('a', [job('simulation_run', 'failed')]))).toBe('failed')
    expect(stateOf(lauf('a', [job('simulation_run', 'failed', { reason: 'process_restart' })]))).toBe('failed')
  })

  it('alle sechs Zustaende haben verschiedene Zeichen', () => {
    const six: LibraryState[] = ['running', 'done', 'incomplete', 'stopped', 'budget', 'failed']
    expect(new Set(six.map((s) => STATE_GLYPH[s])).size).toBe(6)
  })

  it('pausiert ist eigener Zustand und weder gestoppt noch laufend', () => {
    expect(stateOf(lauf('a', [job('simulation_run', 'paused')]))).toBe('paused')
  })

  it('ohne Job-Angabe: unbekannt', () => {
    expect(stateOf(lauf('a', []))).toBe('unknown')
  })

  it('stimmt mit den Zaehlern der Seitenleiste ueberein (laeuft/braucht dich)', () => {
    const objects: ShelfObject[] = [
      lauf('run', [job('simulation_run', 'processing', { sim: 'run' })]),
      lauf('ok', [job('simulation_run', 'completed', { sim: 'ok' })]),
      lauf('fail', [job('simulation_run', 'failed', { sim: 'fail' })]),
      lauf('stop', [job('simulation_run', 'stopped', { sim: 'stop', reason: 'user_stop' })]),
      lauf('bud', [job('simulation_run', 'failed', { sim: 'bud', reason: 'budget_time' })]),
      lauf('inc', [job('report_generate', 'completed', { sim: 'inc' })]),
      bericht('r1', 'inc', 'incomplete'),
    ]
    const entries = buildRunEntries(objects)
    const counts = deriveLibraryCounts({ objects, unavailable: [] })
    expect(filterRuns(entries, 'running')).toHaveLength(counts.laeuft as number)
    expect(filterRuns(entries, 'attention')).toHaveLength(counts.brauchtDich as number)
  })
})

describe('deriveStages', () => {
  it('liefert die Stufen aus den Jobs und dem juengsten Bericht', () => {
    const l = lauf('a', [
      job('report_generate', 'completed'),
      job('simulation_run', 'completed'),
      job('simulation_prepare', 'completed'),
      job('graph_build', 'completed'),
    ])
    const stages = deriveStages(l, [bericht('r', 'a', 'incomplete')])
    expect(stages.map((s) => [s.key, s.state])).toEqual([
      ['graph', 'done'],
      ['personas', 'done'],
      ['simulation', 'done'],
      ['report', 'incomplete'],
    ])
  })

  it('Interviews erscheinen nur, wenn die Registry einen Interview-Job fuehrt', () => {
    expect(deriveStages(lauf('a', [job('simulation_run', 'completed')]), []).some((s) => s.key === 'interviews')).toBe(false)
    expect(deriveStages(lauf('a', [job('interview_agents', 'processing')]), []).find((s) => s.key === 'interviews')?.state).toBe('running')
  })

  it('fehlende Stufe vor einer belegten ist „keine Angabe“, am Kettenende „offen“', () => {
    const stages = deriveStages(lauf('a', [job('simulation_run', 'completed')]), [])
    expect(stages.find((s) => s.key === 'graph')?.state).toBe('unknown')
    expect(stages.find((s) => s.key === 'report')?.state).toBe('pending')
  })
})

describe('buildRunEntries', () => {
  it('Frage aus dem juengsten Bericht als Titel, Quelle bleibt erhalten', () => {
    const [e] = buildRunEntries([
      lauf('sim_1', [job('simulation_run', 'completed', { sim: 'sim_1' })]),
      bericht('r_old', 'sim_1', 'completed', 'Alte Frage', '2026-10-01T10:00:00Z'),
      bericht('r_new', 'sim_1', 'completed', 'Neue Frage', '2026-10-05T10:00:00Z'),
    ])
    expect(e.title).toBe('Neue Frage')
    expect(e.source).toBe('Quelle sim_1')
    expect(e.reports.map((r) => r.id)).toEqual(['r_new', 'r_old'])
  })

  it('ohne Bericht: Name des Laufs als Titel, keine Quellzeile', () => {
    const [e] = buildRunEntries([lauf('sim_2', [job('simulation_run', 'processing', { sim: 'sim_2' })])])
    expect(e.title).toBe('Quelle sim_2')
    expect(e.source).toBeNull()
    expect(e.question).toBeNull()
  })

  it('Bericht, dessen Titel nur seine Kennung ist, liefert keine Frage', () => {
    const [e] = buildRunEntries([lauf('sim_3', [job('simulation_run', 'completed', { sim: 'sim_3' })]), bericht('r3', 'sim_3', 'completed', 'r3')])
    expect(e.question).toBeNull()
  })

  it('Grund in einem Satz fuer gestoppt, Budget, fehlgeschlagen und unvollstaendig', () => {
    const reasons = buildRunEntries([
      lauf('a', [job('simulation_run', 'stopped', { reason: 'user_stop' })]),
      lauf('b', [job('simulation_run', 'failed', { reason: 'budget_tokens' })]),
      lauf('c', [job('simulation_run', 'failed', { reason: 'process_restart' })]),
      lauf('d', [job('simulation_run', 'completed', { sim: 'd' })]),
      bericht('rd', 'd', 'incomplete'),
    ]).map((e) => e.reason?.code ?? null)
    expect(reasons).toEqual(['user_stop', 'budget', 'process_restart', 'incomplete'])
  })

  it('fertige Laeufe tragen keinen Grund', () => {
    expect(buildRunEntries([lauf('a', [job('simulation_run', 'completed')])])[0].reason).toBeNull()
  })
})

describe('Filter ?view=', () => {
  const objects: ShelfObject[] = [
    lauf('run', [job('simulation_run', 'processing', { sim: 'run' })]),
    lauf('rep', [job('simulation_run', 'completed', { sim: 'rep' })]),
    bericht('r1', 'rep', 'completed'),
    bericht('r2', 'rep', 'completed'),
    lauf('fail', [job('simulation_run', 'failed', { sim: 'fail' })]),
  ]
  const entries = buildRunEntries(objects)

  it('running zeigt nur laufende Laeufe', () => {
    expect(filterRuns(entries, 'running').map((e) => e.lauf.id)).toEqual(['run'])
  })
  it('attention zeigt nur Laeufe, die dich brauchen', () => {
    expect(filterRuns(entries, 'attention').map((e) => e.lauf.id)).toEqual(['fail'])
  })
  it('with-report zeigt nur Laeufe mit mindestens einem Bericht, mit Zahl der Fassungen', () => {
    const r = filterRuns(entries, 'with-report')
    expect(r.map((e) => e.lauf.id)).toEqual(['rep'])
    expect(r[0].reports).toHaveLength(2)
  })
  it('all zeigt alles', () => {
    expect(filterRuns(entries, 'all')).toHaveLength(3)
  })
  it('parseRunsView faellt bei Unbekanntem auf „all“', () => {
    expect(parseRunsView('running')).toBe('running')
    expect(parseRunsView(['attention'])).toBe('attention')
    expect(parseRunsView('quatsch')).toBe('all')
    expect(parseRunsView(undefined)).toBe('all')
  })
})

describe('reportStatusState', () => {
  it('incomplete ist nie done; unbekannter Rohstatus ist unknown', () => {
    expect(reportStatusState('completed')).toBe('done')
    expect(reportStatusState('incomplete')).toBe('incomplete')
    expect(reportStatusState('failed')).toBe('failed')
    expect(reportStatusState('generating')).toBe('running')
    expect(reportStatusState('xyz')).toBe('unknown')
  })
})

describe('parseReportVersions', () => {
  const report = (id: string, status: string, created: string) => ({
    schema_version: 2, report_id: id, simulation_id: 'sim_1', graph_id: 'g', simulation_requirement: 'Frage', status, created_at: created,
  })

  it('nummeriert vom aeltesten aufwaerts, neueste zuerst', () => {
    const r = parseReportVersions({
      success: true,
      data: [report('r2', 'completed', '2026-10-02T00:00:00Z'), report('r1', 'incomplete', '2026-10-01T00:00:00Z')],
    })
    expect(r.ok).toBe(true)
    if (!r.ok) return
    expect(r.versions.map((v) => [v.reportId, v.number, v.state])).toEqual([
      ['r2', 2, 'done'],
      ['r1', 1, 'incomplete'],
    ])
  })

  it('zaehlt vertragswidrige Fassungen statt sie zu rendern', () => {
    const r = parseReportVersions({ success: true, data: [report('r1', 'completed', '2026-10-01T00:00:00Z'), { report_id: 'kaputt' }] })
    expect(r).toMatchObject({ ok: true, invalid: 1 })
    if (r.ok) expect(r.versions).toHaveLength(1)
  })

  it('success=false oder fremde Form ist ein Fehler', () => {
    expect(parseReportVersions({ success: false })).toEqual({ ok: false })
    expect(parseReportVersions('x')).toEqual({ ok: false })
  })
})
