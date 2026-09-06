/**
 * SimulationLiveView — Vitest-Smoke-Tests (Redesign PR 7).
 *
 * Prueft:
 * 1. Kopfzeile zeigt Runde x/y und vergangene Zeit.
 * 2. Rundenachse markiert die laufende Runde.
 * 3. Die vier Bahnen rendern ihre Eintraege (Akteure, Reddit, Twitter,
 *    System/Ereignisse).
 * 4. Pause/Abbrechen loesen die richtigen API-Aufrufe aus.
 * 5. prefers-reduced-motion schaltet die Enter-Transition im SFC-Quelltext ab
 *    (kein getComputedStyle auf scoped Styles — jsdom wendet sie nicht an).
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { resetSimFeedStore } from '@/composables/useSimFeed'
import { clearSimClock } from '@/composables/useSimClock'
import { SimulationLiveTestId } from '@/contracts/testIds'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const SIM_ID = 'live-sim-1'

// ---- API mocks ----
let capturedStateHandler: ((msg: { payload: unknown }) => void) | undefined
let capturedPostHandler: ((data: PostCreatedEvent) => void) | undefined

const pauseSimulationMock = vi.fn(async () => ({ success: true, data: {} }))
const resumeSimulationMock = vi.fn(async () => ({ success: true, data: {} }))
const cancelRunMock = vi.fn(async () => ({ success: true }))
const getRunStatusDetailMock = vi.fn(async () => ({
  success: true,
  data: { simulation_id: SIM_ID, status: 'running', current_round: 3, total_rounds: 5, paused: false, run_id: 'run-1' },
}))
const getRunEventsMock = vi.fn(async () => ({
  success: true,
  data: [{ timestamp: '2026-09-06T12:00:00Z', type: 'round_started', message: 'Runde 3 gestartet' }],
}))
const getRunUsageMock = vi.fn(async () => ({
  success: true,
  data: {
    schema_version: 1,
    totals: { total_tokens: 1200, input_tokens: 800, output_tokens: 400, llm_calls: 12, duration_ms: 500, cost_usd: null },
    by_stage: {},
    by_provider: {},
    by_model: {},
    measurement_status: 'complete',
  },
}))

vi.mock('@/api/simulation', () => ({
  getRunStatusDetail: (...args: unknown[]) => getRunStatusDetailMock(...(args as [])),
  pauseSimulation: (...args: unknown[]) => pauseSimulationMock(...(args as [])),
  resumeSimulation: (...args: unknown[]) => resumeSimulationMock(...(args as [])),
  getSimulationFeedSnapshot: vi.fn(async () => []),
}))

vi.mock('@/api/runs', () => ({
  cancelRun: (...args: unknown[]) => cancelRunMock(...(args as [])),
  getRunEvents: (...args: unknown[]) => getRunEventsMock(...(args as [])),
}))

vi.mock('@/api/budget', () => ({
  getRunUsage: (...args: unknown[]) => getRunUsageMock(...(args as [])),
}))

vi.mock('@/composables/useEventStream', () => ({
  useEventStream: (_id: string, handlers: Record<string, (arg: unknown) => void>) => {
    capturedStateHandler = handlers.state as (msg: { payload: unknown }) => void
    capturedPostHandler = handlers.post_created as (data: PostCreatedEvent) => void
    return {
      isStreaming: { value: true },
      error: { value: null },
      lastEventAt: { value: null },
      lastTraceId: { value: null },
      start: vi.fn(async () => {}),
      stop: vi.fn(),
    }
  },
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { simulationId: SIM_ID } }),
  }
})

vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  cb(0)
  return 0
})

// FeedColumn.vue nutzt IntersectionObserver fuer den Auto-Scroll-Pin —
// jsdom kennt den Browser-API nicht (analog StepSimulationFeedView.spec.ts-
// Umfeld, das FeedColumn dort stubbt; hier reicht ein No-Op-Stub, da wir die
// Auto-Scroll-Mechanik nicht testen).
vi.stubGlobal(
  'IntersectionObserver',
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
)

import SimulationLiveView from '../SimulationLiveView.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: {
    de: {
      step3: {
        controls: { pause: 'Pausieren', resume: 'Fortsetzen', cancel: 'Abbrechen' },
        live: {
          title: 'Simulation live',
          round: 'Runde',
          elapsed: 'vergangen',
          secPerRound: 's/Runde',
          roundAxis: 'Rundenachse',
          roundAxisHint: 'Rundenstatus',
          now: 'jetzt',
          lanes: { actors: 'Akteure', reddit: 'Reddit', twitter: 'Twitter', system: 'System' },
          actorsActive: '{count} aktiv',
          usage: { llmCalls: 'LLM-Calls', tokens: 'Tokens gesamt' },
          events: { title: 'Ereignisse', empty: 'Noch keine Ereignisse.' },
          empty: 'Noch keine Aktivität.',
        },
      },
    },
  },
})

const SHELL_STUBS = {
  AppShell: { template: '<main><slot /></main>' },
  PageHeader: { template: '<header><slot /></header>' },
}

function mountView() {
  return mount(SimulationLiveView, { global: { plugins: [i18n], stubs: SHELL_STUBS } })
}

function mkPost(overrides: Partial<PostCreatedEvent> = {}): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: SIM_ID,
    post_id: `p-${Math.random().toString(36).slice(2)}`,
    parent_post_id: null,
    platform: 'reddit',
    persona_id: 'alice',
    persona_name: 'Alice',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'Test',
    timestamp: '2026-09-06T12:00:00Z',
    score: 0,
    ...overrides,
  }
}

describe('SimulationLiveView', () => {
  beforeEach(() => {
    resetSimFeedStore(SIM_ID)
    clearSimClock(SIM_ID)
    capturedStateHandler = undefined
    capturedPostHandler = undefined
    pauseSimulationMock.mockClear()
    resumeSimulationMock.mockClear()
    cancelRunMock.mockClear()
    getRunStatusDetailMock.mockClear()
    getRunEventsMock.mockClear()
    getRunUsageMock.mockClear()
  })

  it('zeigt Runde x/y in der Kopfzeile nach dem initialen Status-Poll', async () => {
    const wrapper = mountView()
    await flushPromises()
    const header = wrapper.find(`[data-testid="${SimulationLiveTestId.headerRound}"]`)
    expect(header.text()).toContain('3')
    expect(header.text()).toContain('5')
  })

  it('markiert die laufende Runde auf der Rundenachse', async () => {
    const wrapper = mountView()
    await flushPromises()
    const ticks = wrapper.findAll(`[data-testid="${SimulationLiveTestId.roundTick}"]`)
    expect(ticks.length).toBe(5)
    expect(ticks[2].classes()).toContain('sl-tick--now')
    expect(ticks[2].attributes('aria-current')).toBe('step')
  })

  it('rendert die Akteure-Bahn aus dem Post-Strom', async () => {
    const wrapper = mountView()
    await flushPromises()
    capturedPostHandler?.(mkPost({ persona_id: 'alice', persona_name: 'Alice' }))
    capturedPostHandler?.(mkPost({ persona_id: 'bob', persona_name: 'Bob', platform: 'twitter' }))
    await flushPromises()
    const rows = wrapper.findAll(`[data-testid="${SimulationLiveTestId.actorRow}"]`)
    expect(rows.length).toBe(2)
    expect(wrapper.find(`[data-testid="${SimulationLiveTestId.laneActors}"]`).text()).toContain('Alice')
  })

  it('rendert Reddit- und Twitter-Bahn aus dem Post-Strom', async () => {
    const wrapper = mountView()
    await flushPromises()
    capturedPostHandler?.(mkPost({ platform: 'reddit', post_id: 'r-1', body: 'Reddit-Inhalt' }))
    capturedPostHandler?.(mkPost({ platform: 'twitter', post_id: 't-1', body: 'Twitter-Inhalt' }))
    await flushPromises()
    expect(wrapper.find(`[data-testid="${SimulationLiveTestId.laneReddit}"]`).text()).toContain('Reddit-Inhalt')
    expect(wrapper.find(`[data-testid="${SimulationLiveTestId.laneTwitter}"]`).text()).toContain('Twitter-Inhalt')
  })

  it('rendert die System/Ereignisse-Bahn aus getRunEvents + getRunUsage', async () => {
    const wrapper = mountView()
    await flushPromises()
    const lane = wrapper.find(`[data-testid="${SimulationLiveTestId.laneSystem}"]`)
    expect(lane.text()).toContain('Runde 3 gestartet')
    expect(lane.text()).toContain('12')
    const rows = wrapper.findAll(`[data-testid="${SimulationLiveTestId.eventRow}"]`)
    expect(rows.length).toBe(1)
  })

  it('Fortsetzen/Pausieren ruft pauseSimulation bzw. resumeSimulation auf', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find(`[data-testid="${SimulationLiveTestId.headerPauseResume}"]`).trigger('click')
    await flushPromises()
    expect(pauseSimulationMock).toHaveBeenCalledWith(SIM_ID)
  })

  it('Abbrechen ruft cancelRun auf', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find(`[data-testid="${SimulationLiveTestId.headerCancel}"]`).trigger('click')
    await flushPromises()
    expect(cancelRunMock).toHaveBeenCalledWith(SIM_ID)
  })

  // Kein getComputedStyle auf scoped Styles (jsdom wendet sie nicht an) —
  // Zusicherung direkt im SFC-Quelltext, analog designTokens.spec.ts.
  it('reduced-motion: die Enter-Transition wird im prefers-reduced-motion-Block deaktiviert', () => {
    const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../SimulationLiveView.vue'), 'utf-8')
    expect(source).toMatch(/@media \(prefers-reduced-motion: reduce\) \{[^}]*\.sl-slide-in-enter-active \{[^}]*transition: none;/s)
  })

  // Fallstrick aus PR 5: keine Transition auf Fokus-Eigenschaften (outline/
  // box-shadow/border-color), sonst wird der Playwright-Fokus-Check instabil.
  it('legt keine Transition auf outline/box-shadow/border-color', () => {
    const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../SimulationLiveView.vue'), 'utf-8')
    const focusRuleMatch = source.match(/\.sl-actor-row:focus-visible \{([^}]*)\}/)
    expect(focusRuleMatch).not.toBeNull()
    expect(focusRuleMatch?.[1]).not.toMatch(/transition/)
  })
})
