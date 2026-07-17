// Issue #744 Phase 4a/4b — useGraphRender Pin-Persistenz & Mini-Map Tests.
//
// Diese Specs ergänzen die Auto-Freeze-Suite (useGraphRender.spec.ts) um:
//   4a. Pin-Persistenz:
//     - Drag-End sichert Node-Positionen in localStorage pro graph_id.
//     - render() wendet gespeichertes Layout als fx/fy an (vor Simulation).
//     - resetLayout() leert den Key und re-rendert.
//   4b. Mini-Map:
//     - minimapNodes wird auf Tick-Updates gespiegelt (via rAF-Flush).
//     - minimapViewport wird beim Zoom-Event aktualisiert.
//     - panToGraphPoint treibt den zoom programmatisch (Call-Spy auf
//       selection.call(zoom.transform, ...)).
//
// D3 wird gemockt — die Handler werden direkt mit synthetischen Events
// aufgerufen, um das Verhalten ohne echtes SVG zu verifizieren.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref, type Ref } from 'vue'

// ---------------------------------------------------------------------------
// Mock D3 — vi.mock factory must NOT reference top-level variables (hoisting).
// ---------------------------------------------------------------------------
vi.mock('d3', () => {
  // Captured handlers per render() so tests can invoke them.
  const captured: Record<string, unknown> = {}

  const makeSim = () => {
    const sim: Record<string, unknown> = {}
    sim['force'] = vi.fn().mockReturnValue(sim)
    sim['stop'] = vi.fn()
    sim['restart'] = vi.fn()
    sim['alpha'] = vi.fn().mockReturnValue(sim)
    sim['alphaTarget'] = vi.fn().mockReturnValue(sim)
    // Capture tick handler so tests can fire it.
    sim['on'] = vi.fn((ev: string, cb: unknown) => {
      if (ev === 'tick') captured.tick = cb
      return sim
    })
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
    // `.call(zoomBehavior)` — capture zoom behavior; `.call(d3.drag()...)` — capture drag handlers.
    sel['call'] = vi.fn((target: unknown) => {
      // Heuristic: d3.drag() returns { on: fn } (has `.on`), zoom behavior has `.transform`.
      const t = target as Record<string, unknown>
      if (t && typeof t.on === 'function' && typeof t.transform === 'undefined') {
        // drag behavior — already captured via .on() below
      } else if (t && typeof t.transform === 'function') {
        captured.zoomBehavior = t
        captured.svgSelection = sel
      }
      return sel
    })
    sel['filter'] = vi.fn().mockReturnValue(sel)
    sel['each'] = vi.fn().mockReturnValue(sel)
    sel['nodes'] = vi.fn().mockReturnValue([])
    return sel
  }

  // Zoom behavior factory: capture 'zoom' handler and expose .transform spy.
  const zoom = () => {
    const zb: Record<string, unknown> = {
      extent: vi.fn().mockReturnThis(),
      scaleExtent: vi.fn().mockReturnThis(),
      on: vi.fn((ev: string, cb: unknown) => {
        if (ev === 'zoom') captured.zoom = cb
        return zb
      }),
      transform: vi.fn(),
    }
    return zb
  }

  // Drag behavior factory: capture start/drag/end handlers.
  const drag = () => {
    const db: Record<string, unknown> = { on: vi.fn().mockReturnThis() }
    // We intercept .on('start'|'drag'|'end', cb) by overriding on to capture.
    db['on'] = vi.fn((ev: string, cb: unknown) => {
      if (ev === 'start') captured.dragStart = cb
      else if (ev === 'drag') captured.dragDrag = cb
      else if (ev === 'end') captured.dragEnd = cb
      return db
    })
    return db
  }

  return {
    forceSimulation: () => makeSim(),
    forceLink: () => ({ id: vi.fn().mockReturnThis(), distance: vi.fn().mockReturnThis() }),
    forceManyBody: () => ({ strength: vi.fn().mockReturnThis() }),
    forceCenter: vi.fn(),
    forceCollide: () => ({ radius: vi.fn().mockReturnThis() }),
    forceX: () => ({ strength: vi.fn().mockReturnThis() }),
    forceY: () => ({ strength: vi.fn().mockReturnThis() }),
    zoom,
    drag,
    select: () => makeSel(),
    zoomIdentity: {
      translate: vi.fn().mockReturnThis(),
      scale: vi.fn().mockReturnThis(),
    },
    __captured: captured,
  }
})

vi.mock('../../components/graph/graphPanelData', () => {
  // Capture the last returned nodes so tests can assert post-render mutations
  // (e.g. fx/fy applied from a saved layout) without overriding forceSimulation.
  let lastNodes: Record<string, unknown>[] = []
  const buildGraphRenderData = (data: { nodes?: Record<string, unknown>[] }) => {
    lastNodes = (data.nodes ?? []).map((n) => ({ ...n, x: 0, y: 0, rawData: {} }))
    return { nodes: lastNodes, edges: [], getColor: () => '#ccc' }
  }
  return {
    buildGraphRenderData,
    __getLastNodes: () => lastNodes,
  }
})

vi.mock('../../components/graph/edgeLabelI18n', () => ({
  formatEdgeLabel: (key: string) => key,
}))

vi.mock('../../components/graph/graphPanelGeometry', () => ({
  getLinkMidpoint: () => ({ x: 0, y: 0 }),
  getLinkPath: () => '',
}))

// Import composable + mocked d3 AFTER mocks are registered.
import { useGraphRender } from '../useGraphRender'
import * as d3MockStar from 'd3'
import * as graphDataMock from '../../components/graph/graphPanelData'
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const d3Mock: any = d3MockStar

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// jsdom in this vitest setup does not expose `localStorage` as a global, so we
// install a minimal in-memory stub. The composable reads/writes `localStorage`
// directly (module-scope helpers), so the stub must live on globalThis.
function installLocalStorageStub() {
  const store = new Map<string, string>()
  const stub = {
    getItem: (k: string) => (store.has(k) ? store.get(k) as string : null),
    setItem: (k: string, v: string) => { store.set(k, String(v)) },
    removeItem: (k: string) => { store.delete(k) },
    clear: () => { store.clear() },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() { return store.size },
  }
  ;(globalThis as Record<string, unknown>).localStorage = stub
  return stub
}

function makeSvgRef(): Ref<SVGSVGElement | null> {
  const svgEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg') as unknown as SVGSVGElement
  return ref(svgEl)
}

function makeContainerRef(w = 800, h = 600): Ref<HTMLElement | null> {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { value: w, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: h, configurable: true })
  return ref(el)
}

interface Harness {
  minimapNodes: Ref<Array<{ id: string; x: number; y: number }>>
  minimapViewport: Ref<{ x: number; y: number; k: number; width: number; height: number }>
  resetLayout: () => void
  panToGraphPoint: (gx: number, gy: number) => void
  unmount: () => void
}

function mountHarness(graphDataValue: unknown): Harness {
  let exposed: ReturnType<typeof useGraphRender> | undefined
  const svgRef = makeSvgRef()
  const containerRef = makeContainerRef()
  const showEdgeLabels = ref(true)
  // The composable accepts MaybeRefOrGetter<RawGraphData | null>; the test data
  // carries an extra graph_id field, so cast through any.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphData: any = ref(graphDataValue)

  const Comp = defineComponent({
    setup() {
      exposed = useGraphRender({
        svgRef,
        containerRef,
        graphData,
        entityTypes: ref([]),
        showEdgeLabels,
      })
      return () => h('div')
    },
  })

  const wrapper = mount(Comp)
  return {
    minimapNodes: exposed!.minimapNodes,
    minimapViewport: exposed!.minimapViewport,
    resetLayout: () => exposed!.resetLayout(),
    panToGraphPoint: (gx: number, gy: number) => exposed!.panToGraphPoint(gx, gy),
    unmount: () => wrapper.unmount(),
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useGraphRender — Pin-Persistenz (Phase 4a)', () => {
  beforeEach(() => {
    installLocalStorageStub()
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('Drag-End sichert Node-Position in localStorage pro graph_id', async () => {
    const graphData = { graph_id: 'g-123', nodes: [{ id: 'n1' }, { id: 'n2' }], edges: [] }
    mountHarness(graphData)
    await flushPromises()

    // Use the real node object the composable closed over so saveNodeLayout
    // iterates the same array we mutate.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const nodes = (graphDataMock as any).__getLastNodes() as Array<Record<string, unknown>>
    const n1 = nodes.find((n) => n.id === 'n1') as Record<string, unknown>

    const captured = d3Mock.__captured
    // Start handler sets fx/fy + drag-tracking fields.
    captured.dragStart?.({ x: 5, y: 5 }, n1)
    // Drag moves the node and flags _isDragging.
    captured.dragDrag?.({ x: 100, y: 120 }, n1)
    // Simulate the tick having updated d.x/d.y to the drop position.
    n1.x = 100
    n1.y = 120
    // End handler must persist the layout (reads n1.x/n1.y → saveNodeLayout).
    captured.dragEnd?.({}, n1)

    const raw = localStorage.getItem('agora:graph-layout:g-123')
    expect(raw, 'layout key must be written').not.toBeNull()
    const parsed = JSON.parse(raw as string)
    expect(parsed.n1).toEqual({ x: 100, y: 120 })
  })

  it('Drag-End persistiert die Drop-Position (d.fx/fy) auch wenn d.x/d.y stale sind', async () => {
    // CodeRabbit/codex P2: läst der User zwischen Simulation-Ticks los, sind
    // d.x/d.y noch die vorige Tick-Position (stale), während d.fx/d.fy bereits
    // die Drop-Position halten. Persistiert werden muss die Drop-Position
    // (sonst snap-back beim Restore). d.x/d.y müssen auf d.fx/d.fy gesynced
    // werden, damit saveNodeLayout (liest n.x/n.y) den echten Drop-Punkt schreibt.
    const graphData = { graph_id: 'g-stale', nodes: [{ id: 'n1' }], edges: [] }
    mountHarness(graphData)
    await flushPromises()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const nodes = (graphDataMock as any).__getLastNodes() as Array<Record<string, unknown>>
    const n1 = nodes.find((n) => n.id === 'n1') as Record<string, unknown>

    const captured = d3Mock.__captured
    captured.dragStart?.({ x: 5, y: 5 }, n1)
    // drag handler setzt d.fx/d.fy = event.x/event.y (Drop-Position 100/120).
    captured.dragDrag?.({ x: 100, y: 120 }, n1)
    // d.x/d.y bleiben auf der vorigen Tick-Position (stale) — User lässt
    // zwischen Ticks los, der letzte Tick hat d.x/d.y noch nicht auf fx/fy gezogen.
    n1.x = 50
    n1.y = 60
    captured.dragEnd?.({}, n1)

    const raw = localStorage.getItem('agora:graph-layout:g-stale')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    // Drop-Position (100/120 via fx/fy), NICHT stale d.x/d.y (50/60).
    expect(parsed.n1).toEqual({ x: 100, y: 120 })
    // Node-Position wurde auf Drop-Punkt gesynced (verhindert snap-back).
    expect(n1.x).toBe(100)
    expect(n1.y).toBe(120)
  })

  it('render() wendet gespeichertes Layout als fx/fy an (vor Simulation)', async () => {
    // Seed a saved layout for graph_id 'g-layout'.
    localStorage.setItem(
      'agora:graph-layout:g-layout',
      JSON.stringify({ n1: { x: 42, y: 77 } }),
    )
    const graphData = { graph_id: 'g-layout', nodes: [{ id: 'n1' }, { id: 'n2' }], edges: [] }
    mountHarness(graphData)
    await flushPromises()

    // The graphPanelData mock captured the node objects; the composable
    // mutated them in place (x/y/fx/fy) before starting the simulation.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const nodes = (graphDataMock as any).__getLastNodes() as Record<string, unknown>[]
    const n1 = nodes.find((n) => n.id === 'n1')
    const n2 = nodes.find((n) => n.id === 'n2')
    expect(n1?.fx).toBe(42)
    expect(n1?.fy).toBe(77)
    expect(n1?.x).toBe(42)
    expect(n1?.y).toBe(77)
    // Unpinned node keeps fx/fy undefined.
    expect(n2?.fx).toBeUndefined()
    expect(n2?.fy).toBeUndefined()
  })

  it('resetLayout() leert den localStorage-Key und re-rendert', async () => {
    const graphData = { graph_id: 'g-reset', nodes: [{ id: 'n1' }], edges: [] }
    const harness = mountHarness(graphData)
    await flushPromises()

    // Seed via drag-end so there is something to clear.
    const captured = d3Mock.__captured
    const node = { id: 'n1', x: 5, y: 6 }
    captured.dragStart?.({ x: 1, y: 1 }, node)
    captured.dragDrag?.({ x: 50, y: 60 }, node)
    node.x = 50
    node.y = 60
    captured.dragEnd?.({}, node)
    expect(localStorage.getItem('agora:graph-layout:g-reset')).not.toBeNull()

    harness.resetLayout()
    await flushPromises()
    expect(localStorage.getItem('agora:graph-layout:g-reset')).toBeNull()
  })

  it('ohne graph_id wird kein localStorage-Key geschrieben', async () => {
    const graphData = { nodes: [{ id: 'n1' }], edges: [] } // no graph_id
    mountHarness(graphData)
    await flushPromises()

    const captured = d3Mock.__captured
    const node = { id: 'n1', x: 0, y: 0 }
    captured.dragStart?.({ x: 1, y: 1 }, node)
    captured.dragDrag?.({ x: 30, y: 40 }, node)
    node.x = 30
    node.y = 40
    captured.dragEnd?.({}, node)

    // No key under the agora prefix should exist.
    let hasKey = false
    for (let i = 0; i < localStorage.length; i++) {
      if ((localStorage.key(i) ?? '').startsWith('agora:graph-layout:')) {
        hasKey = true
        break
      }
    }
    expect(hasKey).toBe(false)
  })

  it('Drag-End ohne echte Bewegung (Klick) pinnt nicht und schreibt keinen Key', async () => {
    const graphData = { graph_id: 'g-click', nodes: [{ id: 'n1' }], edges: [] }
    mountHarness(graphData)
    await flushPromises()

    const captured = d3Mock.__captured
    const node: Record<string, unknown> = { id: 'n1', x: 10, y: 10 }
    captured.dragStart?.({ x: 10, y: 10 }, node)
    // No drag event — _isDragging stays false.
    captured.dragEnd?.({}, node)
    expect(node.fx).toBeNull()
    expect(node.fy).toBeNull()
    expect(localStorage.getItem('agora:graph-layout:g-click')).toBeNull()
  })
})

describe('useGraphRender — Mini-Map (Phase 4b)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('minimapViewport wird beim Zoom-Event aktualisiert', async () => {
    const graphData = { graph_id: 'g-zoom', nodes: [{ id: 'n1' }], edges: [] }
    const harness = mountHarness(graphData)
    await flushPromises()

    const captured = d3Mock.__captured
    const zoomCb = captured.zoom as ((event: { transform: { x: number; y: number; k: number } }) => void) | undefined
    expect(zoomCb, 'zoom handler must be wired').toBeDefined()
    zoomCb!({ transform: { x: 120, y: 80, k: 2 } })
    expect(harness.minimapViewport.value).toMatchObject({ x: 120, y: 80, k: 2, width: 800, height: 600 })
  })

  it('minimapNodes wird nach rAF-Flush aus dem Tick-Handler aktualisiert', async () => {
    vi.useRealTimers()
    const graphData = { graph_id: 'g-tick', nodes: [{ id: 'n1' }, { id: 'n2' }], edges: [] }
    const harness = mountHarness(graphData)
    await flushPromises()
    expect(harness.minimapNodes.value).toEqual([])

    const captured = d3Mock.__captured
    const tickCb = captured.tick as (() => void) | undefined
    expect(tickCb, 'tick handler must be wired').toBeDefined()
    tickCb!()
    // Flush the rAF the composable scheduled.
    await new Promise((r) => requestAnimationFrame(() => r(null)))
    await flushPromises()
    expect(harness.minimapNodes.value.length).toBe(2)
    expect(harness.minimapNodes.value.map((n) => n.id).sort()).toEqual(['n1', 'n2'])
  })

  it('panToGraphPoint ruft zoom.transform programmatisch auf', async () => {
    const graphData = { graph_id: 'g-pan', nodes: [{ id: 'n1' }], edges: [] }
    const harness = mountHarness(graphData)
    await flushPromises()

    const captured = d3Mock.__captured
    const zb = captured.zoomBehavior as { transform: ReturnType<typeof vi.fn> } | undefined
    expect(zb, 'zoom behavior must be captured').toBeDefined()
    const transformFn = zb!.transform
    // Set a known viewport scale via zoom event so _currentTransform.k is set.
    ;(captured.zoom as (event: { transform: { x: number; y: number; k: number } }) => void)!({
      transform: { x: 0, y: 0, k: 1.5 },
    })
    // The svg selection's .call spy is the dispatch surface used by
    // panToGraphPoint: `svgSelection.call(zoomBehavior.transform, newTransform)`.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const svgCallSpy = (captured.svgSelection as any).call as ReturnType<typeof vi.fn>
    svgCallSpy.mockClear()
    d3Mock.zoomIdentity.translate.mockReturnValue(d3Mock.zoomIdentity)
    d3Mock.zoomIdentity.scale.mockReturnValue(d3Mock.zoomIdentity)
    harness.panToGraphPoint(100, 200)
    expect(svgCallSpy).toHaveBeenCalled()
    // Last call's first arg must be the zoom behavior's transform method.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const calls = (svgCallSpy as any).mock.calls as unknown[]
    const lastCall = calls[calls.length - 1] as unknown[]
    expect(lastCall?.[0]).toBe(transformFn)
    // Second arg is the new transform (built via zoomIdentity.translate().scale()).
    expect(lastCall?.[1]).toBeDefined()
  })
})