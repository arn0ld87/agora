import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ActiveRunsCard from '../ActiveRunsCard.vue'
import { makeI18n, makeRouter } from './dashTestHelpers'
import type { RunDetail } from '../../../../contracts/runsContract'

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

describe('ActiveRunsCard', () => {
  it('rendert aktive Run-Zeilen mit ID und Progress', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(ActiveRunsCard, {
      props: {
        runs: [run({ run_id: 'aaaaaaaa-bbbb-cccc', status: 'processing', progress: 33 })],
        loading: false,
        error: '',
      },
      global: { plugins: [makeI18n(), router] },
    })
    expect(w.find('.dt-table').exists()).toBe(true)
    expect(w.text()).toContain('aaaaaaaa')
    expect(w.text()).toContain('33')
  })

  it('rendert EmptyState ohne aktive Runs', async () => {
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(ActiveRunsCard, {
      props: { runs: [], loading: false, error: '' },
      global: { plugins: [makeI18n(), router] },
    })
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
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(ActiveRunsCard, {
      props: {
        runs: [
          run({ run_id: 'completed-1', status: 'completed' }),
          run({ run_id: 'failed-1', status: 'failed' }),
        ],
        loading: false,
        error: '',
      },
      global: { plugins: [makeI18n(), router] },
    })
    expect(w.find('.es-root').exists()).toBe(true)
  })
})
