import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import de from '../../../i18n/locales/de.json'

const logsApi = vi.hoisted(() => ({
  fetchLogs: vi.fn(),
  buildLogsStreamUrl: vi.fn().mockResolvedValue('/api/logs/stream'),
}))
vi.mock('../../../api/logs', () => logsApi)
vi.mock('../../../composables/useStickyScroll', () => ({
  useStickyScroll: () => ({
    unreadCount: { value: 0 },
    scrollToBottom: vi.fn(),
    markAppended: vi.fn(),
  }),
}))

const tailLines = [
  'DEBUG sim_1 tail detail',
  'INFO sim_1 tail visible',
  'WARN sim_1 tail warning',
  'ERROR sim_1 tail issue',
  'INFO sim_2 other run',
]
class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()
  constructor() { FakeEventSource.instances.push(this) }
  send(line: string) { this.onmessage?.({ data: JSON.stringify({ line }) } as MessageEvent) }
}
// @ts-expect-error – replace browser EventSource for this component test
globalThis.EventSource = FakeEventSource

import { fetchLogs } from '../../../api/logs'
import LogStream from '../LogStream.vue'

function setup() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: de as never } })
  return mount(LogStream, {
    props: { scopeId: 'sim_1' },
    global: { plugins: [i18n] },
  })
}

describe('LogStream severity filter', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    logsApi.fetchLogs.mockReset()
    logsApi.fetchLogs.mockImplementation(async () => ({
      success: true,
      data: { lines: tailLines, offset: 0 },
    }))
  })

  it('defaults to INFO and filters tail and SSE while retaining scope and search', async () => {
    const wrapper = setup()
    await flushPromises()

    expect(wrapper.get('.level-select').element).toHaveProperty('value', 'info')
    expect(fetchLogs).toHaveBeenCalledWith({ tail: 500, level: null })
    const source = FakeEventSource.instances.at(-1)!
    source.send('DEBUG sim_1 live detail')
    source.send('INFO sim_1 live visible')
    source.send('INFO sim_2 live other')
    await flushPromises()

    expect(wrapper.findAll('.log-line').map((line) => line.text())).toEqual([
      'INFO sim_1 tail visible',
      'WARN sim_1 tail warning',
      'ERROR sim_1 tail issue',
      'INFO sim_1 live visible',
    ])

    await wrapper.get('.search-input').setValue('live visible')
    expect(wrapper.findAll('.log-line').map((line) => line.text())).toEqual(['INFO sim_1 live visible'])

    await wrapper.get('.search-input').setValue('')
    await wrapper.get('.level-select').setValue('debug')
    await flushPromises()
    expect(fetchLogs).toHaveBeenLastCalledWith({ tail: 500, level: null })
    const debugSource = FakeEventSource.instances.at(-1)!
    debugSource.send('DEBUG sim_1 live detail')
    await flushPromises()

    const visible = wrapper.findAll('.log-line').map((line) => line.text())
    expect(visible).toContain('DEBUG sim_1 tail detail')
    expect(visible).toContain('DEBUG sim_1 live detail')
    expect(visible).not.toContain('INFO sim_2 other run')
    wrapper.unmount()
  })
})
