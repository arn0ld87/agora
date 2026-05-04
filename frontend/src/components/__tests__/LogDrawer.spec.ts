/**
 * LogDrawer — SSE Reconnect-Cap Tests (Sub-Slice J.6, Audit-Empfehlung 7).
 *
 * Testet:
 *   1. Nach 5 onerror-Events wird der Stream gestoppt und streamFailed=true gesetzt.
 *      Der Reload-Button erscheint im DOM.
 *   2. Eine valide onmessage nach 3 Errors resettet den Counter. Weitere Errors
 *      akkumulieren erst ab diesem Reset — der Cap greift erst nach 5 neuen Fehlern.
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
// _capturedSource gibt Tests Zugriff auf Handler und close().
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

// --- i18n-Minimalkonfiguration ---
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
          connectionError: 'SSE-Verbindung unterbrochen, Browser versucht Reconnect…',
          reconnectExhausted: 'Verbindung zum Log-Stream nach mehreren Versuchen abgebrochen.',
          reconnect: 'Erneut verbinden',
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

describe('LogDrawer — SSE Reconnect-Cap (J.6, Audit-Empfehlung 7)', () => {
  it('stoppt den Stream und zeigt Reload-Button nach 5 onerror-Events', async () => {
    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })

    await flushPromises()
    await nextTick()

    // EventSource muss nach dem Mount erzeugt worden sein.
    expect(_capturedSource).not.toBeNull()
    const src = _capturedSource!

    // Reload-Button noch nicht sichtbar.
    expect(wrapper.find('.reconnect-btn').exists()).toBe(false)

    // 5 onerror-Events feuern.
    for (let i = 0; i < 5; i++) {
      src.fireError()
      await nextTick()
    }

    await flushPromises()
    await nextTick()

    // close() muss aufgerufen worden sein (stopStream).
    expect(src.close).toHaveBeenCalled()

    // Reload-Button ist jetzt sichtbar.
    expect(wrapper.find('.reconnect-btn').exists()).toBe(true)

    wrapper.unmount()
  })

  it('resettet den Counter bei onmessage — Cap greift erst nach 5 neuen Fehlern', async () => {
    const wrapper = mount(LogDrawer, {
      props: { open: true },
      global: globalConfig,
    })

    await flushPromises()
    await nextTick()

    expect(_capturedSource).not.toBeNull()
    const src = _capturedSource!

    // 3 Errors — unter dem Cap.
    for (let i = 0; i < 3; i++) {
      src.fireError()
      await nextTick()
    }

    // close noch nicht aufgerufen, Reload-Button nicht sichtbar.
    expect(src.close).not.toHaveBeenCalled()
    expect(wrapper.find('.reconnect-btn').exists()).toBe(false)

    // Valide Message — Counter wird auf 0 zurückgesetzt.
    src.fireMessage({ line: 'INFO — alles gut' })
    await nextTick()

    // Reload-Button darf nach Reset nicht erscheinen.
    expect(wrapper.find('.reconnect-btn').exists()).toBe(false)

    // 4 weitere Errors nach dem Reset — immer noch unter Cap.
    for (let i = 0; i < 4; i++) {
      src.fireError()
      await nextTick()
    }

    expect(src.close).not.toHaveBeenCalled()
    expect(wrapper.find('.reconnect-btn').exists()).toBe(false)

    // 5. Error nach Reset — jetzt ist der Cap erreicht (0→5 neue Fehler).
    src.fireError()
    await nextTick()
    await flushPromises()

    expect(src.close).toHaveBeenCalled()
    expect(wrapper.find('.reconnect-btn').exists()).toBe(true)

    wrapper.unmount()
  })
})
