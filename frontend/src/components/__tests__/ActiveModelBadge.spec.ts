/**
 * ActiveModelBadge — Tests (Slice E.2 / Observability Wave 2026-05).
 *
 * Nutzt createTestingPinia (kein echter HTTP/SSE).
 *
 * Test 1: lastEvent gesetzt → Modell-Name + Cloud-Icon sichtbar, aria-live="polite".
 * Test 2: isStale=true ohne lastKnownModel → zeigt activeModel.idle-Label.
 * Test 3: connectionStatus="failed" → Reload-Button sichtbar; Click ruft store.reconnect().
 * Test 4: connectionStatus="connecting" mit lastKnownModel → Modellname bleibt, Spinner-Dot erscheint.
 * Test 5: connectionStatus="reconnecting" mit lastKnownModel → Modellname bleibt, Spinner-Dot erscheint.
 * Test 6: connectionStatus="connecting" ohne lastKnownModel → activeModel.unknown-Fallback + Spinner-Dot.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createI18n } from 'vue-i18n'
import { useActiveModelStore } from '../../store/useActiveModelStore'
import type { ModelActiveEvent } from '../../contracts/modelActiveContract'

// localStorage mock — must be before any module-time localStorage access.
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

// Stub EventSource so the component's onMounted connect() call doesn't explode.
vi.stubGlobal('EventSource', class {
  onmessage = null
  onerror = null
  close = vi.fn()
})

// Mock api/index — connect() touches it.
vi.mock('../../api/index', () => ({
  default: { post: vi.fn().mockResolvedValue({ data: { ticket: undefined } }) },
  getAgoraToken: vi.fn().mockReturnValue(''),
}))

import ActiveModelBadge from '../ActiveModelBadge.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      activeModel: {
        label: 'Active model',
        idle: 'Idle',
        connecting: 'Connecting…',
        reconnecting: 'Reconnecting…',
        unknown: 'Unknown model',
        failed: 'Connection lost',
        reload: 'Reconnect',
        provider: {
          ollama: 'Ollama (local)',
          cloud: 'Cloud',
          openai: 'OpenAI',
          unknown: 'Unknown provider',
        },
        context: {
          chat: 'Chat',
          chat_json: 'Structured chat',
          embedding: 'Embedding',
          report: 'Report',
          persona: 'Persona',
          graph: 'Graph',
          unknown: 'Unknown context',
        },
      },
    },
    de: {},
  },
})

function makeTestingPinia(overrides: Partial<{
  lastEvent: ModelActiveEvent | null
  lastKnownModel: string | null
  isStale: boolean
  connectionStatus: string
}> = {}) {
  return createTestingPinia({
    createSpy: vi.fn,
    initialState: {
      activeModel: {
        lastEvent: overrides.lastEvent ?? null,
        lastKnownModel: overrides.lastKnownModel ?? null,
        connectionStatus: overrides.connectionStatus ?? 'idle',
        reconnectAttempts: 0,
      },
    },
  })
}

const globalBase = {
  plugins: [i18n],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ActiveModelBadge', () => {
  it('Test 1: lastEvent gesetzt → Modell-Name + Cloud-Icon sichtbar, aria-live=polite', async () => {
    const event: ModelActiveEvent = {
      model: 'gemini-3-flash-preview:cloud',
      provider: 'cloud',
      context: 'chat',
      ts: Date.now() / 1000,
      extra: null,
    }

    const pinia = makeTestingPinia({ lastEvent: event, lastKnownModel: event.model, connectionStatus: 'connected' })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    const store = useActiveModelStore()
    // Override computed isStale via store patch so it reads false.
    store.$patch((s) => { s.lastEvent = event })

    await flushPromises()

    // aria-live must be set.
    const root = wrapper.find('[role="status"]')
    expect(root.exists()).toBe(true)
    expect(root.attributes('aria-live')).toBe('polite')

    // Model name is rendered.
    expect(wrapper.text()).toContain('gemini-3-flash-preview:cloud')

    // Cloud SVG icon present (CloudIcon renders an SVG).
    expect(wrapper.find('svg').exists()).toBe(true)

    wrapper.unmount()
  })

  it('Test 2: isStale=true ohne lastKnownModel → zeigt activeModel.idle', async () => {
    // lastEvent is null, lastKnownModel is null → idle label.
    const pinia = makeTestingPinia({ lastEvent: null, lastKnownModel: null, connectionStatus: 'connected' })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Idle')

    wrapper.unmount()
  })

  it('Test 3: connectionStatus=failed → Reload-Button sichtbar; click ruft reconnect()', async () => {
    const pinia = makeTestingPinia({ connectionStatus: 'failed' })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    await flushPromises()

    // Reload button visible.
    const btn = wrapper.find('.badge-reload-btn')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toBe('Reconnect')

    const store = useActiveModelStore()
    await btn.trigger('click')

    expect(store.reconnect).toHaveBeenCalled()

    wrapper.unmount()
  })

  it('Test 4: connectionStatus=connecting mit lastKnownModel → Modellname bleibt, Spinner-Dot erscheint', async () => {
    const pinia = makeTestingPinia({
      connectionStatus: 'connecting',
      lastEvent: null,
      lastKnownModel: 'llama3:70b',
    })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    await flushPromises()

    // Kein „Verbinde…" als Hauptlabel.
    expect(wrapper.text()).not.toContain('Connecting')

    // Modellname bleibt sichtbar.
    expect(wrapper.text()).toContain('llama3:70b')

    // Spinner-Dot vorhanden.
    expect(wrapper.find('.badge-spinner-dot').exists()).toBe(true)

    // Kein Reload-Button.
    expect(wrapper.find('.badge-reload-btn').exists()).toBe(false)

    wrapper.unmount()
  })

  it('Test 5: connectionStatus=reconnecting mit lastKnownModel → Modellname bleibt, Spinner-Dot erscheint', async () => {
    const event: ModelActiveEvent = {
      model: 'mistral:7b',
      provider: 'ollama',
      context: 'chat',
      ts: Date.now() / 1000,
      extra: null,
    }
    const pinia = makeTestingPinia({
      connectionStatus: 'reconnecting',
      lastEvent: event,
      lastKnownModel: 'mistral:7b',
    })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    await flushPromises()

    // Modellname sichtbar — kein „Verbinde…" / „Reconnecting…" als Hauptlabel.
    expect(wrapper.text()).toContain('mistral:7b')

    // Spinner-Dot vorhanden.
    expect(wrapper.find('.badge-spinner-dot').exists()).toBe(true)

    // Kein Reload-Button (nur bei 'failed').
    expect(wrapper.find('.badge-reload-btn').exists()).toBe(false)

    wrapper.unmount()
  })

  it('Test 6: connectionStatus=connecting ohne lastKnownModel → unknown-Fallback + Spinner-Dot', async () => {
    const pinia = makeTestingPinia({
      connectionStatus: 'connecting',
      lastEvent: null,
      lastKnownModel: null,
    })
    const wrapper = mount(ActiveModelBadge, {
      global: { ...globalBase, plugins: [i18n, pinia] },
    })

    await flushPromises()

    // Unbekanntes Modell als Fallback-Label.
    expect(wrapper.text()).toContain('Unknown model')

    // Spinner-Dot vorhanden.
    expect(wrapper.find('.badge-spinner-dot').exists()).toBe(true)

    wrapper.unmount()
  })
})
