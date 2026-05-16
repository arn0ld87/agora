/**
 * LogDrawer — SSE-Reconnect-Verhalten.
 *
 * Slice 4 (Observability-Welle 2026-05-16, User-Decision):
 * Reconnects sind UNBEGRENZT (kein 5-Versuche-Cap mehr). EventSource nutzt
 * den vom Backend gesetzten ``retry: 5000``-Wert für automatisches Browser-
 * Reconnect. Ein ``streamReconnecting``-Indikator erscheint erst nach 30 s
 * ohne erfolgreichen Frame — kurze Hiccups werden optisch verschluckt.
 *
 * Tests:
 *   1. Mehrere onerror-Events innerhalb < 30 s schließen den Stream NICHT
 *      und triggern KEIN Reload-Button (kein Cap).
 *   2. Erfolgreiche onmessage hält den Reconnect-Indikator inaktiv und setzt
 *      lastFrameAt zurück.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

// localStorage muss vor allen Modul-Imports gemockt sein,
// da i18n/index.js bei Import-Zeit localStorage.getItem aufruft.
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// --- Mock API-Abhängigkeiten ---
vi.mock('../../api/logs', () => ({
  fetchLogs: vi.fn().mockResolvedValue({ data: { success: true, data: { lines: [], offset: 0 } } }),
  buildLogsStreamUrl: vi.fn().mockResolvedValue('http://localhost/api/logs/stream'),
}))

vi.mock('../../api/index', () => ({
  default: { get: vi.fn().mockResolvedValue({ data: {} }), post: vi.fn().mockResolvedValue({ data: { ticket: 'mock-ticket' } }) },
  getAgoraToken: vi.fn().mockReturnValue('test-token'),
}))

vi.mock('../../composables/useStickyScroll', () => ({
  useStickyScroll: vi.fn().mockReturnValue({
    unreadCount: { value: 0 },
    scrollToBottom: vi.fn(),
    markAppended: vi.fn(),
  }),
}))

// --- Kontrollierbarer EventSource-Mock ---
interface FakeSourceHandle {
  close: ReturnType<typeof vi.fn>
  fireMessage: (data: unknown) => void
  fireError: () => void
}

let _capturedSource: FakeSourceHandle | null = null

class MockEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  close = vi.fn()

  constructor(_url: string) {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const self = this
    _capturedSource = {
      close: self.close,
      fireMessage(data: unknown) {
        if (self.onmessage) {
          self.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
        }
      },
      fireError() {
        if (self.onerror) {
          self.onerror(new Event('error'))
        }
      },
    }
  }
}

// @ts-expect-error – globales EventSource durch Mock ersetzen
globalThis.EventSource = MockEventSource

import LogDrawer from '../LogDrawer.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      logs: {
        drawer: {
          title: 'Backend-Logs',
          allLevels: 'Alle Level',
          search: 'Suchen…',
          pause: 'Auto-Scroll pausieren',
          empty: 'Noch keine Log-Zeilen.',
          loading: 'Logs werden geladen…',
          unknownError: 'Logs konnten nicht geladen werden.',
          connectionError: 'SSE-Verbindung unterbrochen, Browser versucht Reconnect…',
          reconnectExhausted: 'Verbindung zum Log-Stream nach mehreren Versuchen abgebrochen.',
          reconnect: 'Erneut verbinden',
          reconnecting: 'Verbindung wird wiederhergestellt…',
        },
      },
      common: { close: 'Schließen' },
    },
    en: {},
  },
})

const globalConfig = {
  plugins: [i18n],
  stubs: { StickyScrollBanner: { template: '<div />' } },
}

beforeEach(() => {
  _capturedSource = null
  vi.clearAllMocks()
})

describe('LogDrawer — SSE Reconnect (Slice 4, unbegrenzte Reconnects)', () => {
  it('mehrere onerror-Events schließen den Stream NICHT (kein Cap)', async () => {
    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })

    await flushPromises()
    await nextTick()

    expect(_capturedSource).not.toBeNull()
    const src = _capturedSource!

    // 10 onerror-Events feuern — früher Cap bei 5, jetzt unbegrenzt.
    for (let i = 0; i < 10; i++) {
      src.fireError()
      await nextTick()
    }

    await flushPromises()
    await nextTick()

    expect(src.close).not.toHaveBeenCalled()
    expect(wrapper.find('.reconnect-btn').exists()).toBe(false)

    wrapper.unmount()
  })

  it('zeigt Fehlermeldung wenn fetchLogs einen Fehler wirft (Task 7)', async () => {
    const { fetchLogs } = await import('../../api/logs')
    ;(fetchLogs as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'))

    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('boom')
  })

  it('zeigt Backend-Marker bei file=null (Task 7)', async () => {
    const { fetchLogs } = await import('../../api/logs')
    ;(fetchLogs as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: {
        success: true,
        data: { lines: [], offset: 0, file: null, message: 'log file for today not yet written' },
      },
    })

    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('log file for today not yet written')
  })

  it('zeigt Loading-State während fetchLogs läuft (Task 7)', async () => {
    const { fetchLogs } = await import('../../api/logs')
    let resolveFetch: (val: unknown) => void = () => {}
    ;(fetchLogs as unknown as ReturnType<typeof vi.fn>).mockImplementationOnce(
      () => new Promise((resolve) => { resolveFetch = resolve }),
    )

    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('Logs werden geladen…')

    resolveFetch({ data: { success: true, data: { lines: ['ok'], offset: 0 } } })
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).not.toContain('Logs werden geladen…')
  })

  it('reconnect-indicator bleibt versteckt, wenn onmessage rechtzeitig kommt', async () => {
    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })

    await flushPromises()
    await nextTick()

    expect(_capturedSource).not.toBeNull()
    const src = _capturedSource!

    // onerror direkt nach Mount — lastFrameAt ist gerade gesetzt, also
    // streamReconnecting bleibt false (Drift < 30 s).
    src.fireError()
    await nextTick()
    expect(wrapper.find('.reconnect-indicator').exists()).toBe(false)

    // Valider Frame setzt lastFrameAt erneut und sollte den Indikator
    // garantiert versteckt halten.
    src.fireMessage({ line: 'INFO — alles gut' })
    await nextTick()
    expect(wrapper.find('.reconnect-indicator').exists()).toBe(false)

    wrapper.unmount()
  })
})
