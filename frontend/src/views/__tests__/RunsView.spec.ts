import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../components/AppFooter.vue', () => ({
  default: { template: '<footer />' },
}))
vi.mock('../../components/ui/AgoraGlyph.vue', () => ({
  default: { template: '<svg />' },
}))
vi.mock('../../components/RunsDashboard.vue', () => ({
  default: {
    props: { pollIntervalMs: { type: Number, required: false, default: 5000 } },
    template: '<div class="runs-dashboard-prop">{{ pollIntervalMs }}</div>',
  },
}))
vi.mock('../../api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  openSettingsStream: vi.fn().mockResolvedValue({ close: vi.fn() }),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))

import { fetchSettings, fetchSettingsSchema } from '../../api/settings'
import { useSettingsStore } from '../../store/settings'
import RunsView from '../RunsView.vue'

describe('RunsView', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    setActivePinia(createPinia())
    ;(fetchSettingsSchema as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        sections: ['ui'],
        fields: [
          { key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int', secret: false, reload_required: false, default: 5000, min: 1000, max: 60000 },
        ],
      },
    })
    ;(fetchSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      data: {
        sections: ['ui'],
        fields: {
          ui: [
            { key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int', secret: false, reload_required: false, value: 1500, default: 5000, source: 'file', is_set: true },
          ],
        },
      },
    })
  })

  it('binds the live settings poll interval into RunsDashboard', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: RunsView }],
    })

    const wrapper = mount(RunsView, {
      global: {
        plugins: [router, pinia],
      },
    })

    await router.isReady()
    await flushPromises()

    expect(wrapper.find('.runs-dashboard-prop').text()).toBe('1500')

    const store = useSettingsStore()
    store.fields = {
      ui: [
        { key: 'RUNS_POLL_INTERVAL_MS', section: 'ui', type: 'int', secret: false, reload_required: false, value: 2500, default: 5000, source: 'file', is_set: true },
      ],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.runs-dashboard-prop').text()).toBe('2500')
  })
})
