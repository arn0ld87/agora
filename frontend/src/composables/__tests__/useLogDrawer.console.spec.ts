/**
 * useLogDrawer — Konsole: Höhe (gemerkt, begrenzt) und Zähler ungelesener
 * Fehler bei geschlossener Konsole (#1795, Ticket 8).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

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

vi.mock('../../api/logs', () => ({
  buildLogsStreamUrl: vi.fn().mockResolvedValue('http://localhost/api/logs/stream?level=error'),
}))

const sources: MockEventSource[] = []
class MockEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1
  close = vi.fn(() => { this.readyState = 2 })
  constructor(public url: string) { sources.push(this) }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
}
// @ts-expect-error – globales EventSource durch Mock ersetzen
globalThis.EventSource = MockEventSource

import { useLogDrawer, clampLogDrawerHeight, LOG_DRAWER_MIN_HEIGHT } from '../useLogDrawer'
import { buildLogsStreamUrl } from '../../api/logs'
import { useAuthStore } from '../../store/auth'

type Drawer = ReturnType<typeof useLogDrawer>
function mountDrawer(): { drawer: Drawer; unmount: () => void } {
  let drawer!: Drawer
  const wrapper = mount(
    defineComponent({
      setup() {
        drawer = useLogDrawer()
        return () => h('div')
      },
    }),
  )
  return { drawer, unmount: () => wrapper.unmount() }
}

describe('useLogDrawer — Höhe', () => {
  it('begrenzt auf Unter- und Obergrenze und merkt sich den Wert', () => {
    const { setHeight, height } = useLogDrawer()
    setHeight(5)
    expect(height.value).toBe(LOG_DRAWER_MIN_HEIGHT)
    setHeight(99999)
    expect(height.value).toBe(clampLogDrawerHeight(99999))
    expect(height.value).toBeGreaterThan(LOG_DRAWER_MIN_HEIGHT)
    setHeight(300)
    expect(height.value).toBe(300)
    expect(store['agora.ui.logDrawer.height']).toBe('300')
  })

  it('ersetzt ungültige Werte durch den Standard', () => {
    expect(clampLogDrawerHeight(Number.NaN)).toBe(320)
  })
})

describe('useLogDrawer — unreadErrors', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sources.length = 0
    vi.mocked(buildLogsStreamUrl).mockClear()
    // Singleton-Zähler zurücksetzen: Öffnen setzt ihn auf 0.
    useLogDrawer().open()
    useLogDrawer().close()
  })

  it('zählt Fehlerzeilen bei geschlossener Konsole, Öffnen setzt auf 0 und beendet den Strom', async () => {
    const { drawer, unmount } = mountDrawer()
    await flushPromises()

    expect(buildLogsStreamUrl).toHaveBeenCalledWith('error', null)
    expect(sources).toHaveLength(1)
    sources[0]!.emit({ line: 'ERROR a' })
    sources[0]!.emit({ line: 'ERROR b' })
    expect(drawer.unreadErrors.value).toBe(2)

    drawer.open()
    await nextTick()
    expect(drawer.unreadErrors.value).toBe(0)
    expect(sources[0]!.close).toHaveBeenCalled()

    drawer.close()
    await flushPromises()
    expect(sources).toHaveLength(2)
    sources[1]!.emit({ line: 'ERROR c' })
    expect(drawer.unreadErrors.value).toBe(1)

    unmount()
    expect(sources[1]!.close).toHaveBeenCalled()
  })

  it('ignoriert Frames ohne Zeile', async () => {
    const { drawer, unmount } = mountDrawer()
    await flushPromises()
    sources[0]!.emit({ ts: 'x' })
    sources[0]!.onmessage?.(new MessageEvent('message', { data: 'kein json' }))
    expect(drawer.unreadErrors.value).toBe(0)
    unmount()
  })

  it('öffnet für Nicht-Operatoren keine Verbindung und zählt nichts', async () => {
    const auth = useAuthStore()
    auth.config = { auth_backend: 'hybrid', jwt_enabled: true, supabase_url: 'https://s.test', supabase_anon_key: 'k', realtime_enabled: false, demo_mode: false }
    auth.session = { access_token: 'x' } as never
    const { drawer, unmount } = mountDrawer()
    await flushPromises()

    expect(drawer.available.value).toBe(false)
    expect(sources).toHaveLength(0)
    expect(drawer.unreadErrors.value).toBe(0)
    unmount()
  })
})
