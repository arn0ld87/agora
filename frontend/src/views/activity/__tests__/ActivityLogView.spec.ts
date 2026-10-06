/**
 * Aktivität → Protokoll und Konsole mit Lauf-Vorfilter (#1797, Etappe 2 Ticket 5):
 * dieselbe Komponente, genau ein Strom, Vorfilter samt „Alles zeigen".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { defineComponent, h } from 'vue'
import de from '../../../i18n/locales/de.json'

const store: Record<string, string> = {}
Object.defineProperty(globalThis, 'localStorage', {
  value: {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  },
  writable: true,
})

vi.mock('../../../api/logs', () => ({
  fetchLogs: vi.fn().mockResolvedValue({
    success: true,
    data: { lines: ['INFO sim_1 gestartet', 'INFO sim_2 gestartet', 'ERROR sim_1 kaputt'], offset: 0 },
  }),
  buildLogsStreamUrl: vi.fn().mockResolvedValue('http://localhost/api/logs/stream'),
}))
vi.mock('../../../composables/useStickyScroll', () => ({
  useStickyScroll: vi.fn().mockReturnValue({ unreadCount: { value: 0 }, scrollToBottom: vi.fn(), markAppended: vi.fn() }),
}))
vi.mock('../../../composables/useOperatorAccess', async () => {
  const { ref } = await import('vue')
  return { useOperatorAccess: () => ref(true) }
})
vi.mock('../../../composables/useShellBreadcrumbs', () => ({ useShellBreadcrumbs: () => undefined }))

const sources: { close: ReturnType<typeof vi.fn>; closed: boolean }[] = []
class FakeEventSource {
  onmessage = null
  onerror = null
  closed = false
  close = vi.fn(() => { this.closed = true })
  constructor() { sources.push(this) }
}
// @ts-expect-error – globales EventSource durch Mock ersetzen
globalThis.EventSource = FakeEventSource

import ActivityLogView from '../ActivityLogView.vue'
import LogStream from '../../../components/activity/LogStream.vue'
import LogDrawer from '../../../components/LogDrawer.vue'
import { useLogDrawer } from '../../../composables/useLogDrawer'

// Der erste Test kompiliert Seite, Konsole und Router kalt; unter Last reichen 5 s nicht.
vi.setConfig({ testTimeout: 30000 })

const stub = defineComponent({ render: () => h('div') })
function setup(path: string) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de: de as never } })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/activity/jobs', name: 'ActivityJobs', component: stub },
      { path: '/activity/log', name: 'ActivityLog', component: stub },
      { path: '/simulations/:simulationId', name: 'RunWorkspace', component: stub },
      { path: '/ablage', name: 'Shelf', component: stub },
    ],
  })
  void router.push(path)
  return { i18n, router }
}
const liveSources = () => sources.filter((s) => !s.closed).length

describe('Protokollseite', () => {
  beforeEach(() => { sources.length = 0 })

  it('nutzt dieselbe Protokoll-Komponente wie die Konsole und zeigt die Zeilen', async () => {
    const { i18n, router } = setup('/activity/log')
    await router.isReady()
    const page = mount(ActivityLogView, { global: { plugins: [i18n, router] } })
    await flushPromises()
    expect(page.findComponent(LogStream).exists()).toBe(true)
    expect(page.findAll('.log-line')).toHaveLength(3)
    expect(page.find('.level-select').exists()).toBe(true)
    expect(page.find('.search-input').exists()).toBe(true)
    expect(page.find('.copy-btn').exists()).toBe(true)

    const drawer = mount(LogDrawer, { props: { open: true }, global: { plugins: [i18n, router] } })
    expect(drawer.findComponent(LogStream).exists()).toBe(true)
    drawer.unmount()
    page.unmount()
  })

  it('hält den Strom allein: die Konsole bleibt unsichtbar, nie zwei Verbindungen', async () => {
    const { i18n, router } = setup('/activity/log')
    await router.isReady()
    const host = defineComponent({
      setup() {
        const { visible, open } = useLogDrawer()
        open()
        return () => [h(LogDrawer, { open: visible.value }), h(ActivityLogView)]
      },
    })
    const w = mount(host, { global: { plugins: [i18n, router] } })
    await flushPromises()
    expect(w.findAll('.log-drawer')).toHaveLength(0)
    expect(liveSources()).toBe(1)
    w.unmount()
  })
})

describe('Konsole im Lauf', () => {
  beforeEach(() => { sources.length = 0 })

  it('ist auf den Lauf vorgefiltert, „Alles zeigen" hebt den Filter auf', async () => {
    const { i18n, router } = setup('/simulations/sim_1')
    await router.isReady()
    const w = mount(LogDrawer, { props: { open: true }, global: { plugins: [i18n, router] } })
    await flushPromises()
    expect(w.findAll('.log-line').map((l) => l.text())).toEqual(['INFO sim_1 gestartet', 'ERROR sim_1 kaputt'])
    expect(w.get('.scope-note').text()).toContain('nicht exakt')

    await w.get('.scope-all').setValue(true)
    expect(w.findAll('.log-line')).toHaveLength(3)
    expect(w.find('.scope-note').exists()).toBe(false)
  })

  it('zeigt außerhalb eines Laufs weder Filter noch Schalter', async () => {
    const { i18n, router } = setup('/ablage')
    await router.isReady()
    const w = mount(LogDrawer, { props: { open: true }, global: { plugins: [i18n, router] } })
    await flushPromises()
    expect(w.findAll('.log-line')).toHaveLength(3)
    expect(w.find('.scope-all').exists()).toBe(false)
  })

  it('Kopieren übernimmt nur die sichtbaren, vorgefilterten Zeilen', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { i18n, router } = setup('/simulations/sim_1')
    await router.isReady()
    const w = mount(LogDrawer, { props: { open: true }, global: { plugins: [i18n, router] } })
    await flushPromises()
    await w.get('.copy-btn').trigger('click')
    expect(writeText).toHaveBeenCalledWith('INFO sim_1 gestartet\nERROR sim_1 kaputt')
  })
})
