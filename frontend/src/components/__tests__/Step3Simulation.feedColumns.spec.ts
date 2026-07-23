// Task 2 — Dual-Column Sim-Feed Smoke-Test.
//
// Mountet Step3Simulation mit gestubbtem useEventStream und feuert zwei
// post_created-Events (1 reddit, 1 twitter) über den Store. Erwartung:
// Card 3 enthält genau zwei FeedColumn-Stubs, und beide Columns rendern
// jeweils einen Post-Stub. Stats (allActions) und Console bleiben
// unangetastet — der Test isoliert den Feed-Pfad.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

// API-Stubs — Step3Simulation feuert pollDetail() onMounted; wir lassen
// alles still durchlaufen.
vi.mock('../../api/simulation', () => ({
  startSimulation: vi.fn(),
  stopSimulation: vi.fn(),
  pauseSimulation: vi.fn(),
  resumeSimulation: vi.fn(),
  getRunStatus: vi.fn().mockResolvedValue({ success: false }),
  getRunStatusDetail: vi.fn().mockResolvedValue({ success: false }),
  getSimulationConsoleLog: vi.fn().mockResolvedValue(null),
}))

vi.mock('../../api/report', () => ({
  generateReport: vi.fn(),
}))

// useEventStream-Mock: speichert die Handlers, gibt sie für den Test frei.
let capturedHandlers: Record<string, (data: unknown) => void> = {}
vi.mock('../../composables/useEventStream', () => ({
  useEventStream: (_id: unknown, handlers: Record<string, (d: unknown) => void>) => {
    capturedHandlers = handlers
    return {
      isStreaming: ref(false),
      error: ref(null),
      lastEventAt: ref(null),
      lastTraceId: ref<string | null>(null),
      start: vi.fn(),
      stop: vi.fn(),
    }
  },
}))

vi.mock('../../composables/useIncrementalLogPolling', () => ({
  useIncrementalLogPolling: () => ({
    lines: { value: [] },
    polling: { start: vi.fn(), stop: vi.fn() },
    reset: vi.fn(),
  }),
}))

vi.mock('../../composables/usePolling', () => ({
  usePolling: () => ({ start: vi.fn(), stop: vi.fn() }),
}))

vi.mock('../../composables/useStickyScroll', () => ({
  useStickyScroll: () => ({
    unreadCount: { value: 0 },
    scrollToBottom: vi.fn(),
    markAppended: vi.fn(),
  }),
}))

vi.mock('../../utils/feedHighlight', () => ({
  tokenizeFeedText: (s: string) => [{ type: 'text', value: s }],
}))

vi.mock('../../observability/tracing', () => ({
  traceIdToSigNozUrl: () => null,
}))

vi.mock('../../composables/useEnvForm', () => ({
  storedEffectiveModel: () => 'mock',
  STORAGE_CUSTOM_MODEL: 'k1',
  STORAGE_MODEL: 'k2',
}))

vi.mock('../../composables/useRuntimeLlmOptions', () => ({
  runtimeLlmPayloadFromStorage: () => ({}),
  runtimeProviderMissingKeyEverywhere: () => false,
}))

// Kanonische Modell-Auswahl stubben: Step3 ruft useEffectiveModelSelection
// im Setup auf; ohne Mock läge kein Pinia-/Store-Kontext vor. Default: keine
// Auswahl → Legacy-Pfad bleibt unberührt (Feed-Test ruft doStart nicht auf).
vi.mock('@/composables/useEffectiveModelSelection', () => ({
  useEffectiveModelSelection: () => ({
    effectiveRef: { value: null },
    effectiveRoute: { value: null },
    loading: { value: false },
    error: { value: null },
    ensureLoaded: vi.fn().mockResolvedValue(undefined),
    setGlobalSelection: vi.fn().mockResolvedValue(undefined),
  }),
}))

// useSimFeed: echtes Modul behalten — wir wollen die Routing- und
// Dedupe-Logik mittesten.
import { clearSimFeed } from '../../composables/useSimFeed'
import Step3Simulation from '../Step3Simulation.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    de: {
      step3: {
        feed: {
          title: 'Live-Feed',
          empty: 'Noch keine Posts.',
          actions: 'Aktionen: {count}',
          density: { label: 'Dichte', comfort: 'Komfort', compact: 'Kompakt' },
        },
        toolPanel: {
          toggle: 'Tool-Panel',
          show: 'Anzeigen',
          hide: 'Verbergen',
          unread: '{n} ungelesen',
          empty: '—',
          noErrors: '—',
          filter: 'Filter',
          filterAll: 'Alle',
          filterErrors: 'Errors',
          copyAsJson: 'Kopieren',
        },
        status: {
          ready: 'Bereit',
          paused: 'Pause',
          running: 'Läuft',
          completed: 'Fertig',
          failed: 'Fehler',
        },
        controls: {
          start: 'Start',
          stop: 'Stop',
          pause: 'Pause',
          resume: 'Resume',
          pauseHint: 'Pausieren…',
        },
      },
      feed: { reddit: 'Reddit', twitter: 'Twitter' },
      common: { close: 'Schließen' },
    },
  },
})

const stubs = {
  Button: { template: '<button><slot /></button>' },
  Badge: { template: '<span><slot /></span>' },
  Kicker: { template: '<h3><slot /></h3>' },
  StickyScrollBanner: { template: '<div />' },
  FeedColumn: {
    name: 'FeedColumn',
    props: ['title', 'channel'],
    template: '<section :data-channel="channel"><slot /></section>',
  },
  TwitterPost: {
    name: 'TwitterPost',
    props: ['post'],
    template: '<article class="tw-post" :data-id="post.post_id" />',
  },
  RedditThread: {
    name: 'RedditThread',
    props: ['node'],
    template: '<article class="rd-thread" :data-id="node.post_id" />',
  },
}

beforeEach(() => {
  capturedHandlers = {}
  clearSimFeed('sim-task2')
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div />' } }],
})

describe('Step3Simulation — Dual-Column Feed (Task 2)', () => {
  it('rendert beide FeedColumns und füttert Twitter/Reddit aus post_created', async () => {
    const wrapper = mount(Step3Simulation, {
      props: { simulationId: 'sim-task2', maxRounds: 3 },
      global: { plugins: [i18n, router], stubs },
    })

    await flushPromises()
    await nextTick()

    // Phase 0 — Card 3 hängt an phase >= 1; wir setzen phase manuell.
    const vm = wrapper.vm as unknown as { phase: number }
    vm.phase = 1
    await nextTick()

    const columns = wrapper.findAllComponents({ name: 'FeedColumn' })
    expect(columns).toHaveLength(2)
    expect(columns[0].props('channel')).toBe('twitter')
    expect(columns[1].props('channel')).toBe('reddit')

    // post_created-Frames feuern.
    expect(typeof capturedHandlers.post_created).toBe('function')
    capturedHandlers.post_created({
      event_type: 'post_created',
      simulation_id: 'sim-task2',
      post_id: 't-1',
      parent_post_id: null,
      platform: 'twitter',
      persona_id: 'p-1',
      voice_register: 'casual',
      is_simulated: true,
      body: 'Tweet body',
      timestamp: '2026-05-16T10:00:00+00:00',
      sentiment: null,
      score: 0,
    })
    capturedHandlers.post_created({
      event_type: 'post_created',
      simulation_id: 'sim-task2',
      post_id: 'r-1',
      parent_post_id: null,
      platform: 'reddit',
      persona_id: 'p-2',
      voice_register: 'formal',
      is_simulated: true,
      body: 'Reddit body',
      timestamp: '2026-05-16T10:01:00+00:00',
      sentiment: null,
      score: 0,
    })
    await nextTick()

    expect(wrapper.findAll('.tw-post')).toHaveLength(1)
    expect(wrapper.findAll('.rd-thread')).toHaveLength(1)
    expect(wrapper.find('.tw-post').attributes('data-id')).toBe('t-1')
    expect(wrapper.find('.rd-thread').attributes('data-id')).toBe('r-1')
  })
})
