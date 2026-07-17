import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ActiveRunsCard from '../ActiveRunsCard.vue'
import { makeI18n, makeRouter } from './dashTestHelpers'
import type { RunDetail } from '../../../../contracts/runsContract'

const { stopRunMock } = vi.hoisted(() => ({ stopRunMock: vi.fn() }))
vi.mock('../../../../api/runs', async (importOriginal) => ({
  ...((await importOriginal()) as Record<string, unknown>),
  stopRun: stopRunMock,
}))

function run(over: Partial<RunDetail>): RunDetail {
  return {
    run_id: 'r-1234567890',
    run_type: 'graph_build',
    entity_id: 'project-a',
    parent_run_id: null,
    status: 'processing',
    progress: 45,
    message: '',
    error: null,
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_at: null,
    branch_label: null,
    metadata: {},
    linked_ids: { project_id: 'project-a' },
    artifacts: {},
    resume_capability: {},
    summary: {
      model: 'qwen2.5:32b',
      document_name: 'Briefing.pdf',
      persona_count: 12,
      graph_id: null,
      graph_name: null,
      branch_name: null,
    },
    ...over,
  } as RunDetail
}

async function mountCard(runs: RunDetail[] = []) {
  const router = makeRouter()
  await router.push('/dashboard')
  const w = mount(ActiveRunsCard, {
    props: { runs, loading: false, error: '' },
    global: { plugins: [makeI18n(), router] },
  })
  return w
}

describe('ActiveRunsCard', () => {
  beforeEach(() => {
    stopRunMock.mockReset()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('rendert aktive Run-Zeilen mit ID und Progress', async () => {
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb-cccc', status: 'processing', progress: 33 })])
    expect(w.find('.dt-table').exists()).toBe(true)
    expect(w.text()).toContain('aaaaaaaa')
    expect(w.text()).toContain('33')
  })

  it('rendert EmptyState ohne aktive Runs', async () => {
    const w = await mountCard([])
    expect(w.find('.es-root').exists()).toBe(true)
  })

  it('rendert Error-State + Retry', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(ActiveRunsCard, {
      props: { runs: [], loading: false, error: 'Schema-Drift: bad field' },
      global: { plugins: [makeI18n(), router] },
    })
    expect(w.find('.ar-error').exists()).toBe(true)
    await w.find('.ar-retry').trigger('click')
    expect(w.emitted('refresh')).toBeTruthy()
  })

  it('filtert nicht-aktive Status raus', async () => {
    const w = await mountCard([
      run({ run_id: 'completed-1', status: 'completed' }),
      run({ run_id: 'failed-1', status: 'failed' }),
    ])
    expect(w.find('.es-root').exists()).toBe(true)
  })

  it('zeigt pro aktivem Run einen Stop-Button', async () => {
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })])
    expect(w.find('.ar-stop').exists()).toBe(true)
  })

  it('ruft stopRun(runId) auf nach Bestätigung und emit refresh', async () => {
    stopRunMock.mockResolvedValue({ data: { run_id: 'aaaaaaaa-bbbb', status: 'stopped' } })
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })])
    await w.find('.ar-stop').trigger('click')
    await flushPromises()
    expect(stopRunMock).toHaveBeenCalledTimes(1)
    expect(stopRunMock).toHaveBeenCalledWith('aaaaaaaa-bbbb')
    expect(w.emitted('refresh')).toBeTruthy()
  })

  it('ohne Bestätigung keinen stopRun-Aufruf', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })])
    await w.find('.ar-stop').trigger('click')
    await flushPromises()
    expect(stopRunMock).not.toHaveBeenCalled()
    expect(w.emitted('refresh')).toBeFalsy()
  })

  it('zeigt optimistischen Loading-State während stopRun aussteht', async () => {
    let resolveStop!: (v: unknown) => void
    stopRunMock.mockReturnValue(new Promise((r) => { resolveStop = r as (v: unknown) => void }))
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })])
    const btn = w.find('.ar-stop')
    await btn.trigger('click')
    await flushPromises()
    // Button ist während des Aufrufs deaktiviert (loading)
    expect(btn.attributes('aria-busy')).toBe('true')
    expect(btn.attributes('disabled')).toBeDefined()
    resolveStop({ data: { run_id: 'aaaaaaaa-bbbb', status: 'stopped' } })
    await flushPromises()
    expect(w.emitted('refresh')).toBeTruthy()
  })

  it('leitet Stop-Fehler nicht weiter und bleibt stabil (kein Crash)', async () => {
    stopRunMock.mockRejectedValue(new Error('boom'))
    const w = await mountCard([run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })])
    await w.find('.ar-stop').trigger('click')
    await flushPromises()
    expect(stopRunMock).toHaveBeenCalled()
    // Nach Fehler kein refresh-Event (Status unbekannt) und Komponente noch intakt
    expect(w.find('.dt-table').exists()).toBe(true)
    expect(w.emitted('refresh')).toBeFalsy()
  })

  it('stoppt nicht die Row-Navigation beim Klick auf Stop', async () => {
    stopRunMock.mockResolvedValue({ data: { run_id: 'aaaaaaaa-bbbb', status: 'stopped' } })
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(ActiveRunsCard, {
      props: { runs: [run({ run_id: 'aaaaaaaa-bbbb', status: 'processing', run_type: 'simulation_run' })], loading: false, error: '' },
      global: { plugins: [makeI18n(), router] },
    })
    const stopBtn = w.find('.ar-stop')
    await stopBtn.trigger('click')
    await flushPromises()
    // Kein Route-Push nach RunDetail durch den Stop-Klick
    expect(router.currentRoute.value.name).toBe('Dashboard')
  })

  // CodeRabbit/codex P1: Stop-Button darf nur für simulation_run rendern —
  // POST /api/runs/{id}/stop returnt 409 für andere run_types (s. backend
  // test_runs_resume_stop.py::test_resume_unsupported_run_type_returns_409),
  // ein Kill-Switch der immer failt ist schlimmer als keiner.
  it('rendert keinen Stop-Button für graph_build (nicht stoppbar)', async () => {
    const w = await mountCard([run({ run_id: 'graph-aaaaaaaa', status: 'processing', run_type: 'graph_build' })])
    expect(w.find('.ar-stop').exists()).toBe(false)
  })

  it('rendert keinen Stop-Button für report_generate (nicht stoppbar)', async () => {
    const w = await mountCard([run({ run_id: 'report-aaaaaa', status: 'processing', run_type: 'report_generate' })])
    expect(w.find('.ar-stop').exists()).toBe(false)
  })

  it('rendert Stop-Button nur für simulation_run', async () => {
    const w = await mountCard([run({ run_id: 'sim-aaaaaaaa', status: 'processing', run_type: 'simulation_run' })])
    expect(w.find('.ar-stop').exists()).toBe(true)
  })
})