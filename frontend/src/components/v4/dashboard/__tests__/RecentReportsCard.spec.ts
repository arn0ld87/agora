import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { makeI18n, makeRouter } from './dashTestHelpers'

vi.mock('../../../../api/runs', () => ({
  listRuns: vi.fn(),
}))

import { listRuns } from '../../../../api/runs'
import RecentReportsCard from '../RecentReportsCard.vue'

describe('RecentReportsCard', () => {
  beforeEach(() => {
    vi.mocked(listRuns).mockReset()
  })

  it('rendert abgeschlossene Reports im Ready-State', async () => {
    vi.mocked(listRuns).mockResolvedValue({
      success: true,
      data: {
        runs: [{
          run_id: 'report-run-1234567890',
          run_type: 'report_generate',
          entity_id: 'sim-1',
          parent_run_id: null,
          status: 'completed',
          progress: 100,
          message: '',
          error: null,
          started_at: '2026-05-14T09:00:00Z',
          updated_at: '2026-05-14T10:00:00Z',
          completed_at: '2026-05-14T10:00:00Z',
          branch_label: null,
          metadata: { confidence_score: 0.74 },
          linked_ids: { report_id: 'rep-abcdef1234' },
          artifacts: {},
          resume_capability: {},
          summary: { persona_count: 12, document_name: 'Test.pdf' },
        }],
        total: 1,
      },
    } as never)
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(RecentReportsCard, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()
    expect(w.text()).toContain('rep-abcd')
    expect(w.text()).toContain('74%')
    expect(w.text()).toContain('12')
  })

  it('rendert EmptyState ohne Reports', async () => {
    vi.mocked(listRuns).mockResolvedValue({
      success: true,
      data: { runs: [], total: 0 },
    } as never)
    const router = makeRouter()
    await router.push('/dashboard')
    const w = mount(RecentReportsCard, { global: { plugins: [makeI18n(), router] } })
    await flushPromises()
    expect(w.find('.es-root').exists()).toBe(true)
  })
})
