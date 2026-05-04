/**
 * useActiveModelStore — Tests (Slice E.2, Issue #213).
 *
 * Tested:
 *  1. Modell-Wechsel: connect() → 2 Frames → lastEvent ist der zweite Frame; isStale=false.
 *  2. Idle-Fallback: nach STALE_AFTER_MS ohne neue Events → isStale=true.
 *  3. Reconnect-Cap: 5x onerror → connectionStatus='failed'; reconnect() resettet.
 *  4. Auth-Fehler: Ticket-fetch wirft 401-ähnlich → status='failed', kein EventSource.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useActiveModelStore, STALE_AFTER_MS } from '../useActiveModelStore'

// --- localStorage mock (needed before any module that touches i18n) ---
const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// --- Mock api/index so no real HTTP calls are made ---
vi.mock('../../api/index', () => ({
  default: {
    post: vi.fn(),
  },
  getAgoraToken: vi.fn().mockReturnValue(''),
}))

import service, { getAgoraToken } from '../../api/index'

// --- Controlled EventSource stub ---
interface FakeEsHandle {
  onmessage: ((e: MessageEvent) => void) | null
  onerror: ((e: Event) => void) | null
  close: ReturnType<typeof vi.fn>
  fireMessage(data: unknown): void
  fireError(): void
}

let _capturedEs: FakeEsHandle | null = null

class MockEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  close = vi.fn()

  constructor(_url: string) {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    const self = this
    _capturedEs = {
      get onmessage() { return self.onmessage },
      get onerror() { return self.onerror },
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

vi.stubGlobal('EventSource', MockEventSource)

// Valid event fixture.
function makeEvent(model: string, overrides: Partial<{
  context: string
  provider: string
  ts: number
  extra: null
}> = {}) {
  return {
    model,
    context: overrides.context ?? 'chat',
    provider: overrides.provider ?? 'ollama',
    ts: overrides.ts ?? Date.now() / 1000,
    extra: overrides.extra ?? null,
  }
}

// Cast mock helpers.
const _service = service as unknown as { post: ReturnType<typeof vi.fn> }
const _getAgoraToken = getAgoraToken as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  setActivePinia(createPinia())
  _capturedEs = null
  vi.clearAllMocks()
  // Default: no token so no ticket fetch happens (unauthenticated mode).
  _getAgoraToken.mockReturnValue('')
  _service.post.mockResolvedValue({ data: { ticket: 'test-ticket' } })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useActiveModelStore', () => {
  it('Test 1: Modell-Wechsel — lastEvent ist der zweite Frame; isStale=false direkt danach', async () => {
    vi.useFakeTimers()
    const store = useActiveModelStore()

    await store.connect()

    expect(_capturedEs).not.toBeNull()

    const tsNow = Date.now() / 1000

    _capturedEs!.fireMessage(makeEvent('model-a:v1', { ts: tsNow }))
    expect(store.lastEvent?.model).toBe('model-a:v1')

    _capturedEs!.fireMessage(makeEvent('model-b:v2', { ts: tsNow }))
    expect(store.lastEvent?.model).toBe('model-b:v2')
    expect(store.isStale).toBe(false)

    store.disconnect()
  })

  it('Test 2: Idle-Fallback — nach STALE_AFTER_MS → isStale=true', async () => {
    vi.useFakeTimers()
    const store = useActiveModelStore()

    await store.connect()

    // Fire one event at t=0 (fake time).
    const tsAtStart = Date.now() / 1000
    _capturedEs!.fireMessage(makeEvent('model-a:v1', { ts: tsAtStart }))
    expect(store.isStale).toBe(false)

    // Advance past stale threshold. The tick interval updates _now.
    vi.advanceTimersByTime(STALE_AFTER_MS + 10_000)

    expect(store.isStale).toBe(true)

    store.disconnect()
  })

  it('Test 3: Reconnect-Cap — 5x onerror → failed; reconnect() setzt zurück', async () => {
    const store = useActiveModelStore()
    await store.connect()

    expect(_capturedEs).not.toBeNull()

    for (let i = 0; i < 5; i++) {
      _capturedEs!.fireError()
    }

    expect(store.connectionStatus).toBe('failed')

    // reconnect() should call connect() again and reset state.
    _capturedEs = null
    await store.reconnect()

    // A new EventSource must have been created.
    expect(_capturedEs).not.toBeNull()
    expect(store.reconnectAttempts).toBe(0)
    expect(store.connectionStatus).not.toBe('failed')

    store.disconnect()
  })

  it('Test 4: Auth-Fehler — Ticket-fetch wirft → status=failed, kein EventSource', async () => {
    // Simulate auth token present so ticket fetch is attempted.
    _getAgoraToken.mockReturnValue('some-token')
    _service.post.mockRejectedValue(new Error('401 Unauthorized'))

    const store = useActiveModelStore()
    await store.connect()

    expect(store.connectionStatus).toBe('failed')
    // EventSource constructor should NOT have been called.
    expect(_capturedEs).toBeNull()
  })
})
