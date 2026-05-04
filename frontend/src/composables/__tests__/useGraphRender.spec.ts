// Issue #137 SUB2 — useGraphRender Auto-Freeze Tests.
//
// Tests focus exclusively on the Auto-Freeze / batchSignal logic inside
// useGraphRender. D3 and graphPanelData are mocked so no real SVG layout
// is needed — the tests run in jsdom without a canvas.
//
// Tested contracts:
//   1. batch-trigger   — batchSignal.batch_count increase → Auto-Freeze fires,
//                        isPaused=true; after autoFreezeMs isPaused=false.
//   2. no-op same count — same batch_count value → no pause/resume.
//   3. manual-pause wins — _isManuallyPaused → batch increment does NOT
//                          trigger Auto-Freeze; no resumeSimulation after timer.
//   4a. manual-during-freeze — user pauses mid Auto-Freeze; timer fires but
//                              must NOT resume (manual intent wins).
//   5. cleanup on unmount — pending Auto-Freeze timer is cancelled; no crash.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref, type Ref } from 'vue'
import type { BuildProgressDetail } from '../../api/graph'

// ---------------------------------------------------------------------------
// Mock D3 — vi.mock factory must NOT reference top-level variables (hoisting).
// All spies are created fresh inside the factory with vi.fn().
// ---------------------------------------------------------------------------
vi.mock('d3', () => {
  const makeSim = () => {
    const sim: Record<string, unknown> = {}
    sim['force'] = vi.fn().mockReturnValue(sim)
    sim['stop'] = vi.fn()
    sim['restart'] = vi.fn()
    sim['alpha'] = vi.fn().mockReturnValue(sim)
    sim['alphaTarget'] = vi.fn().mockReturnValue(sim)
    sim['on'] = vi.fn().mockReturnValue(sim)
    return sim
  }

  const makeSel = (): Record<string, unknown> => {
    const sel: Record<string, unknown> = {}
    sel['attr'] = vi.fn().mockReturnValue(sel)
    sel['style'] = vi.fn().mockReturnValue(sel)
    sel['selectAll'] = vi.fn().mockReturnValue(sel)
    sel['append'] = vi.fn().mockReturnValue(sel)
    sel['remove'] = vi.fn().mockReturnValue(sel)
    sel['data'] = vi.fn().mockReturnValue(sel)
    sel['enter'] = vi.fn().mockReturnValue(sel)
    sel['text'] = vi.fn().mockReturnValue(sel)
    sel['on'] = vi.fn().mockReturnValue(sel)
    sel['call'] = vi.fn().mockReturnValue(sel)
    sel['filter'] = vi.fn().mockReturnValue(sel)
    sel['each'] = vi.fn().mockReturnValue(sel)
    sel['nodes'] = vi.fn().mockReturnValue([])
    return sel
  }

  return {
    forceSimulation: () => makeSim(),
    forceLink: () => ({ id: vi.fn().mockReturnThis(), distance: vi.fn().mockReturnThis() }),
    forceManyBody: () => ({ strength: vi.fn().mockReturnThis() }),
    forceCenter: vi.fn(),
    forceCollide: () => ({ radius: vi.fn().mockReturnThis() }),
    forceX: () => ({ strength: vi.fn().mockReturnThis() }),
    forceY: () => ({ strength: vi.fn().mockReturnThis() }),
    zoom: () => ({
      extent: vi.fn().mockReturnThis(),
      scaleExtent: vi.fn().mockReturnThis(),
      on: vi.fn().mockReturnThis(),
    }),
    select: () => makeSel(),
    drag: () => ({ on: vi.fn().mockReturnThis() }),
  }
})

vi.mock('../../components/graph/graphPanelData', () => ({
  buildGraphRenderData: () => ({
    nodes: [{ id: 'n1', name: 'Node 1', type: 'Entity', x: 0, y: 0, rawData: {} }],
    edges: [],
    getColor: () => '#ccc',
  }),
}))

vi.mock('../../components/graph/edgeLabelI18n', () => ({
  formatEdgeLabel: (key: string) => key,
}))

vi.mock('../../components/graph/graphPanelGeometry', () => ({
  getLinkMidpoint: () => ({ x: 0, y: 0 }),
  getLinkPath: () => '',
}))

// Import composable AFTER mocks are registered.
import { useGraphRender } from '../useGraphRender'

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeSvgRef(): Ref<SVGSVGElement | null> {
  const svgEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg') as unknown as SVGSVGElement
  return ref(svgEl)
}

function makeContainerRef(): Ref<HTMLElement | null> {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { value: 800, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true })
  return ref(el)
}

const MINIMAL_GRAPH = { nodes: [{ id: 'n1' }], edges: [] }

interface HarnessResult {
  wrapper: ReturnType<typeof mount>
  pauseSimulation: () => void
  resumeSimulation: () => void
  togglePause: () => void
  isPaused: Ref<boolean>
}

function mountHarness(
  batchSignal: Ref<BuildProgressDetail | null>,
  autoFreezeMs = 800,
): HarnessResult {
  let exposed: ReturnType<typeof useGraphRender> | undefined

  const Comp = defineComponent({
    setup() {
      const svgRef = makeSvgRef()
      const containerRef = makeContainerRef()
      const showEdgeLabels = ref(true)
      const graphData = ref(MINIMAL_GRAPH)

      exposed = useGraphRender({
        svgRef,
        containerRef,
        graphData,
        entityTypes: ref([]),
        showEdgeLabels,
        batchSignal,
        autoFreezeMs,
      })

      return () => h('div')
    },
  })

  const wrapper = mount(Comp)

  return {
    wrapper,
    pauseSimulation: () => exposed!.pauseSimulation(),
    resumeSimulation: () => exposed!.resumeSimulation(),
    togglePause: () => exposed!.togglePause(),
    isPaused: exposed!.isPaused,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useGraphRender — Auto-Freeze (Issue #137 SUB2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // -------------------------------------------------------------------------
  // Test 1 — batch_count increase triggers Auto-Freeze and auto-resume.
  // -------------------------------------------------------------------------
  it('Test 1 (batch-trigger): batch_count increase pauses; resumes after autoFreezeMs', async () => {
    const batchSignal = ref<BuildProgressDetail | null>(null)
    const { isPaused } = mountHarness(batchSignal, 800)

    await flushPromises()
    expect(isPaused.value).toBe(false)

    // First batch arrives.
    batchSignal.value = { batch_count: 1, total_batches: 5, batch_at: Date.now() / 1000 }
    await flushPromises()

    expect(isPaused.value).toBe(true)

    // 1 ms before timer fires — still frozen.
    vi.advanceTimersByTime(799)
    expect(isPaused.value).toBe(true)

    // Timer fires — auto-resumed.
    vi.advanceTimersByTime(1)
    expect(isPaused.value).toBe(false)
  })

  // -------------------------------------------------------------------------
  // Test 2 — same batch_count value → no additional freeze.
  // -------------------------------------------------------------------------
  it('Test 2 (no-op same count): same batch_count does not trigger another freeze', async () => {
    const batchSignal = ref<BuildProgressDetail | null>({
      batch_count: 3,
      total_batches: 5,
      batch_at: Date.now() / 1000,
    })
    const { isPaused } = mountHarness(batchSignal, 800)

    await flushPromises()
    // First watch fires with oldCount=undefined → newCount(3) > 0 → initial freeze.
    // Advance past it.
    vi.advanceTimersByTime(800)
    expect(isPaused.value).toBe(false)

    // Same batch_count again — no new freeze.
    batchSignal.value = { batch_count: 3, total_batches: 5, batch_at: Date.now() / 1000 + 1 }
    await flushPromises()

    expect(isPaused.value).toBe(false)

    vi.advanceTimersByTime(800)
    expect(isPaused.value).toBe(false)
  })

  // -------------------------------------------------------------------------
  // Test 3 — Manual-pause wins: batch increment while manually paused
  // must NOT start an Auto-Freeze (no timer, no state change).
  // -------------------------------------------------------------------------
  it('Test 3 (manual-pause wins): batch increment does not trigger Auto-Freeze when user is manually paused', async () => {
    const batchSignal = ref<BuildProgressDetail | null>(null)
    const { isPaused, pauseSimulation } = mountHarness(batchSignal, 800)

    await flushPromises()

    // User manually pauses.
    pauseSimulation()
    expect(isPaused.value).toBe(true)

    // New batch arrives while manually paused — Auto-Freeze must be skipped.
    batchSignal.value = { batch_count: 1, total_batches: 5, batch_at: Date.now() / 1000 }
    await flushPromises()

    // Still paused (manual), and no timer was set to resume.
    expect(isPaused.value).toBe(true)

    // Advance far past any timer window — must stay paused.
    vi.advanceTimersByTime(2000)
    expect(isPaused.value).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Test 4a — User pauses during an active Auto-Freeze; timer fires but
  // must NOT auto-resume (manual intent takes precedence).
  // -------------------------------------------------------------------------
  it('Test 4a (manual-during-freeze): timer does NOT resume when user pauses mid-freeze', async () => {
    const batchSignal = ref<BuildProgressDetail | null>(null)
    const { isPaused, pauseSimulation } = mountHarness(batchSignal, 800)

    await flushPromises()

    // Trigger Auto-Freeze.
    batchSignal.value = { batch_count: 1, total_batches: 5, batch_at: Date.now() / 1000 }
    await flushPromises()
    expect(isPaused.value).toBe(true)

    // User explicitly pauses mid-freeze (sets _isManuallyPaused).
    pauseSimulation()
    expect(isPaused.value).toBe(true)

    // Timer fires — should NOT resume because manual pause intent is active.
    vi.advanceTimersByTime(800)
    expect(isPaused.value).toBe(true)
  })

  // -------------------------------------------------------------------------
  // Test 5 — Cleanup on unmount: pending timer is cancelled, no crash.
  // -------------------------------------------------------------------------
  it('Test 5 (cleanup): unmount cancels pending Auto-Freeze timer without errors', async () => {
    const batchSignal = ref<BuildProgressDetail | null>(null)
    const { wrapper, isPaused } = mountHarness(batchSignal, 800)

    await flushPromises()

    // Trigger Auto-Freeze.
    batchSignal.value = { batch_count: 1, total_batches: 5, batch_at: Date.now() / 1000 }
    await flushPromises()
    expect(isPaused.value).toBe(true)

    // Unmount before timer fires — timer must be cancelled.
    wrapper.unmount()

    // Advancing past the timer must not throw.
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow()
  })
})
