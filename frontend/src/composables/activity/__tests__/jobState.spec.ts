import { describe, it, expect } from 'vitest'
import type { RunDetail } from '../../../contracts/runsContract'
import { filterJobRows, formatDuration, jobRowOf, jobRowsOf, jobStateOf } from '../jobState'
import { filterLinesByScope, parseLogFrame, parseLogTail } from '../logTail'

function run(over: Record<string, unknown> = {}): RunDetail {
  return {
    run_id: 'run_1',
    run_type: 'simulation_run',
    entity_id: 'e',
    status: 'processing',
    progress: 10,
    message: '',
    started_at: '2026-10-05T14:00:00Z',
    updated_at: '2026-10-05T14:10:00Z',
    metadata: {},
    linked_ids: {},
    artifacts: {},
    resume_capability: {},
    ...over,
  } as RunDetail
}

describe('jobStateOf', () => {
  it('leitet die Zustände getrennt ab', () => {
    expect(jobStateOf(run({ status: 'pending' }))).toBe('pending')
    expect(jobStateOf(run({ status: 'processing' }))).toBe('running')
    expect(jobStateOf(run({ status: 'paused' }))).toBe('paused')
    expect(jobStateOf(run({ status: 'completed' }))).toBe('completed')
    expect(jobStateOf(run({ status: 'failed' }))).toBe('failed')
    expect(jobStateOf(run({ status: 'stopped' }))).toBe('stopped')
  })

  it('user_stop ist gestoppt, Budget ist Budget, process_restart ist fehlgeschlagen', () => {
    expect(jobStateOf(run({ status: 'stopped', termination_reason: 'user_stop' }))).toBe('stopped')
    expect(jobStateOf(run({ status: 'stopped', metadata: { termination_reason: 'budget_cost' } }))).toBe('budget')
    expect(jobStateOf(run({ status: 'failed', termination_reason: 'budget_tokens' }))).toBe('budget')
    expect(jobStateOf(run({ status: 'failed', termination_reason: 'process_restart' }))).toBe('failed')
  })

  it('ignoriert unbekannte Gründe und nicht abgeschlossene Jobs', () => {
    expect(jobStateOf(run({ status: 'failed', termination_reason: 'was-neues' }))).toBe('failed')
    expect(jobStateOf(run({ status: 'processing', termination_reason: 'user_stop' }))).toBe('running')
  })
})

describe('jobRowOf', () => {
  it('trägt simulationId nur, wenn der Job eine Simulation hat', () => {
    expect(jobRowOf(run(), 0).simulationId).toBeNull()
    expect(jobRowOf(run({ linked_ids: { simulation_id: 'sim_1' } }), 0).simulationId).toBe('sim_1')
  })

  it('Abbrechen nur für laufende Jobs bekannter Arten', () => {
    expect(jobRowOf(run(), 0).cancellable).toBe(true)
    expect(jobRowOf(run({ status: 'completed' }), 0).cancellable).toBe(false)
    expect(jobRowOf(run({ status: 'failed' }), 0).cancellable).toBe(false)
    expect(jobRowOf(run({ run_type: 'ontology_generate' }), 0).cancellable).toBe(false)
  })

  it('Dauer: laufend bis jetzt, beendet bis completed_at', () => {
    const start = Date.parse('2026-10-05T14:00:00Z')
    expect(jobRowOf(run(), start + 90_000).durationMs).toBe(90_000)
    expect(jobRowOf(run({ status: 'completed', completed_at: '2026-10-05T14:03:31Z' }), start + 9e9).durationMs).toBe(211_000)
  })
})

describe('Filter und Format', () => {
  const rows = jobRowsOf(
    [
      run({ run_id: 'a', status: 'processing', updated_at: '2026-10-05T14:10:00Z' }),
      run({ run_id: 'b', run_type: 'graph_build', status: 'failed', updated_at: '2026-10-05T15:00:00Z' }),
    ],
    0,
  )
  it('sortiert neueste zuerst und filtert nach Art und Zustand', () => {
    expect(rows.map((r) => r.runId)).toEqual(['b', 'a'])
    expect(filterJobRows(rows, { kind: 'graph_build', state: '' }).map((r) => r.runId)).toEqual(['b'])
    expect(filterJobRows(rows, { kind: '', state: 'running' }).map((r) => r.runId)).toEqual(['a'])
    expect(filterJobRows(rows, { kind: 'graph_build', state: 'running' })).toEqual([])
  })
  it('formatiert Dauern', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(8_000)).toBe('8 s')
    expect(formatDuration(211_000)).toBe('3 min 31 s')
    expect(formatDuration(3_840_000)).toBe('1 h 4 min')
  })
})

describe('logTail', () => {
  it('liest die Hülle und die doppelte Hülle', () => {
    const data = { lines: ['a'], offset: 3 }
    expect(parseLogTail({ success: true, data })).toEqual({ ok: true, data: { lines: ['a'], offset: 3 } })
    expect(parseLogTail({ data: { success: true, data } })).toMatchObject({ ok: true })
    expect(parseLogTail({ success: false, error: 'kaputt' })).toEqual({ ok: false, error: 'kaputt' })
    expect(parseLogTail({ nope: 1 })).toEqual({ ok: false, error: null })
  })
  it('liest Frames und filtert per Textsuche', () => {
    expect(parseLogFrame(JSON.stringify({ line: 'x' }))).toBe('x')
    expect(parseLogFrame('kein json')).toBeNull()
    expect(parseLogFrame(JSON.stringify({ line: 3 }))).toBeNull()
    expect(filterLinesByScope(['sim_1 ok', 'sim_2 ok'], 'sim_1')).toEqual(['sim_1 ok'])
    expect(filterLinesByScope(['a', 'b'], null)).toEqual(['a', 'b'])
  })
})
