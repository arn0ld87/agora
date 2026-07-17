/**
 * useGraphRender — D3-Force-basiertes Rendering für den Agora-Graph.
 *
 * Issue #35 (EPIC-04-ST-02): hebt die D3-Renderlogik aus `GraphCanvas.vue`
 * heraus, damit sie separat test- und wartbar wird. Das Composable
 * ownst den Render-Lifecycle (mount/unmount/resize), hält die internen
 * D3-Refs (`currentSimulation`, `linkLabelsRef`, `linkLabelBgRef`) als
 * Modul-State pro Aufruf, watcht die reaktiven Eingaben (`graphData`,
 * `showEdgeLabels`) und stellt `selectedItem` als Output-Ref zur Verfügung.
 *
 * Schnittstellen (Issue-Akzeptanz):
 *  - Resize:    Composable registriert `window.resize` → `nextTick(renderGraph)`,
 *               cleanup in `onUnmounted`.
 *  - Re-Render: Watch auf `graphData` (deep) und `selectedRound`/`showEdgeLabels`
 *               wird vom Composable verdrahtet; Erst-Render in `onMounted`.
 *  - Selection: `selectedItem`-Ref wird vom Composable zurückgegeben; D3-Click-
 *               Handler schreiben hinein, der Aufrufer kann sie auch von außen
 *               leeren (z.B. bei „Detail schließen").
 */

import { onMounted, onUnmounted, onScopeDispose, ref, toValue, watch, nextTick, type MaybeRefOrGetter, type Ref } from 'vue'
import * as d3 from 'd3'

import { buildGraphRenderData } from '../components/graph/graphPanelData'
import { formatEdgeLabel } from '../components/graph/edgeLabelI18n'
import { getLinkMidpoint, getLinkPath } from '../components/graph/graphPanelGeometry'
import type { BuildProgressDetail } from '../api/graph'

/** Raw graph data shape consumed by buildGraphRenderData. */
interface RawGraphData {
  nodes?: Record<string, unknown>[]
  edges?: Record<string, unknown>[]
}

/** Entity-type color-mapping entry as expected by buildGraphRenderData. */
export interface EntityTypeEntry {
  name: string
  color: string
}

export interface UseGraphRenderArgs {
  svgRef: Ref<SVGSVGElement | null>
  containerRef: Ref<HTMLElement | null>
  graphData: MaybeRefOrGetter<RawGraphData | null>
  entityTypes: MaybeRefOrGetter<EntityTypeEntry[]>
  showEdgeLabels: Ref<boolean>
  translateLabel?: ((key: string) => string) | null
  /** Optional reactive signal carrying current batch progress during graph build. */
  batchSignal?: MaybeRefOrGetter<BuildProgressDetail | null>
  /**
   * Duration in milliseconds for which the Force-Simulation is frozen when a new
   * batch is committed during graph build.
   *
   * Defaults to 800 ms. Settings-wiring (#133/#212) is a follow-up slice (SUB3).
   */
  autoFreezeMs?: number
}

export interface UseGraphRenderReturn {
  selectedItem: Ref<Record<string, unknown> | null>
  render: () => void
  isPaused: Ref<boolean>
  pauseSimulation: () => void
  resumeSimulation: () => void
  togglePause: () => void
  /**
   * Issue #744 Phase 4a — clears the persisted node-pinch layout for the
   * current graph_id and re-renders without fixed positions (fx/fy = null).
   */
  resetLayout: () => void
  /**
   * Issue #744 Phase 4b — reactive mirror of node positions for the Mini-Map.
   * Updated (throttled via rAF) on every Force-Simulation tick.
   */
  minimapNodes: Ref<Array<{ id: string; x: number; y: number }>>
  /**
   * Issue #744 Phase 4b — reactive mirror of the main viewport's d3.zoom
   * transform plus container dimensions, so the Mini-Map can draw the
   * viewport rectangle and convert Mini-Map clicks back to graph coords.
   */
  minimapViewport: Ref<{ x: number; y: number; k: number; width: number; height: number }>
  /**
   * Issue #744 Phase 4b — pans the main viewport so that the given graph-space
   * point is centered. Used by the Mini-Map click/drag handler.
   */
  panToGraphPoint: (gx: number, gy: number) => void
}

// ---------------------------------------------------------------------------
// Issue #744 Phase 4a — localStorage persistence for per-graph node pinch.
// Layouts are keyed by graph_id so different graphs keep independent layouts.
// ---------------------------------------------------------------------------

const GRAPH_LAYOUT_STORAGE_PREFIX = 'agora:graph-layout:'

function layoutStorageKey(graphId: string): string {
  return GRAPH_LAYOUT_STORAGE_PREFIX + graphId
}

function loadSavedLayout(graphId: string): Record<string, { x: number; y: number }> | null {
  if (typeof localStorage === 'undefined') return null
  try {
    const raw = localStorage.getItem(layoutStorageKey(graphId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') return null
    return parsed as Record<string, { x: number; y: number }>
  } catch {
    return null
  }
}

function saveNodeLayout(
  graphId: string,
  nodes: ReadonlyArray<{ id: string; x: number; y: number }>,
): void {
  if (typeof localStorage === 'undefined') return
  const map: Record<string, { x: number; y: number }> = {}
  for (const n of nodes) {
    if (n && typeof n.id === 'string' && Number.isFinite(n.x) && Number.isFinite(n.y)) {
      map[n.id] = { x: n.x, y: n.y }
    }
  }
  try {
    localStorage.setItem(layoutStorageKey(graphId), JSON.stringify(map))
  } catch {
    // ignore quota / serialization errors — pin persistence is best-effort
  }
}

function clearNodeLayout(graphId: string): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.removeItem(layoutStorageKey(graphId))
  } catch {
    // ignore
  }
}

// reason: d3 v7 ships types via @types/d3; its internal Selection/Simulation generics require
// matching the exact datum types from graphPanelData.js (a JS file, checkJs=false).
// Using `any` here is the pragmatic choice to avoid sprawling casts across every d3 call.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D3Selection = d3.Selection<any, any, any, any>
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D3Simulation = d3.Simulation<any, any>

export function useGraphRender({
  svgRef,
  containerRef,
  graphData,
  entityTypes,
  showEdgeLabels,
  translateLabel = null,
  batchSignal,
  autoFreezeMs = 800,
}: UseGraphRenderArgs): UseGraphRenderReturn {
  const selectedItem = ref<Record<string, unknown> | null>(null)
  const isPaused = ref(false)

  let currentSimulation: D3Simulation | null = null
  let linkLabelsRef: D3Selection | null = null
  let linkLabelBgRef: D3Selection | null = null

  /**
   * Whether a manual pause was initiated by the user (via togglePause/pauseSimulation).
   * This flag is distinct from `isPaused`: `isPaused` is the effective render state,
   * `_isManuallyPaused` records the *intent*. When Auto-Freeze runs it temporarily
   * sets `isPaused=true` but does NOT set `_isManuallyPaused`. If the user manually
   * pauses during an Auto-Freeze, `_isManuallyPaused` becomes true and the
   * Auto-Freeze timer must NOT call resumeSimulation when it fires.
   */
  let _isManuallyPaused = false

  /**
   * True while an Auto-Freeze timer is running. Used so the resume-callback can
   * check whether the user manually paused during the freeze window.
   */
  let _autoFreezeActive = false
  let _autoFreezeTimer: ReturnType<typeof setTimeout> | null = null

  // Issue #744 Phase 4a — graph_id of the currently rendered graph, tracked
  // so resetLayout() can clear the matching localStorage key without re-reading
  // the raw data shape, and so the drag-end handler can persist positions.
  let currentGraphId: string | null = null

  // Issue #744 Phase 4b — refs/state consumed by the Mini-Map.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let _zoomBehavior: any = null
  let _svgSelection: D3Selection | null = null
  let _currentTransform: { x: number; y: number; k: number } = { x: 0, y: 0, k: 1 }
  let _containerWidth = 0
  let _containerHeight = 0
  let _minimapRafHandle: number | null = null
  const minimapNodes = ref<Array<{ id: string; x: number; y: number }>>([])
  const minimapViewport = ref<{ x: number; y: number; k: number; width: number; height: number }>({
    x: 0,
    y: 0,
    k: 1,
    width: 0,
    height: 0,
  })

  const render = () => {
    const svgEl = svgRef.value
    const data = toValue(graphData)
    if (!svgEl || !data) return

    if (currentSimulation) {
      currentSimulation.stop()
    }

    const container = containerRef.value
    if (!container) return
    const width = container.clientWidth
    const height = container.clientHeight

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)

    svg.selectAll('*').remove()

    const types = toValue(entityTypes) || []
    // reason: buildGraphRenderData is a JS function; the result types are inferred
    // as JSDoc-only and are not compatible with d3 SimulationNodeDatum generics.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { nodes, edges, getColor } = buildGraphRenderData(data, types) as { nodes: any[]; edges: any[]; getColor: (type: string) => string }
    if (nodes.length === 0) return

    // Issue #744 Phase 4a — track graph_id for localStorage pin persistence.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const rawGraphId = (data as any)?.graph_id
    currentGraphId = typeof rawGraphId === 'string' && rawGraphId.length > 0 ? rawGraphId : null

    // Issue #744 Phase 4a — restore persisted pinch layout BEFORE the simulation
    // starts. Nodes with a saved position get x/y + fx/fy so the Force layout
    // leaves them in place instead of recomputing them.
    const savedLayout = currentGraphId ? loadSavedLayout(currentGraphId) : null
    if (savedLayout) {
      for (const n of nodes) {
        const pos = savedLayout[n.id]
        if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y)) {
          n.x = pos.x
          n.y = pos.y
          n.fx = pos.x
          n.fy = pos.y
        }
      }
    }

    // reason: nodes/edges come from a JS module; cast to any[] is required to satisfy d3 overloads
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const simulation: D3Simulation = (d3.forceSimulation as any)(nodes)
      .force('link', d3.forceLink(edges).id((d: any) => d.id).distance((d: any) => {
        const baseDistance = 150
        const edgeCount = d.pairTotal || 1
        return baseDistance + (edgeCount - 1) * 50
      }))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(50))
      .force('x', d3.forceX(width / 2).strength(0.04))
      .force('y', d3.forceY(height / 2).strength(0.04))

    currentSimulation = simulation
    if (isPaused.value) {
      // Vor dem Re-Render war pausiert → Simulation gar nicht erst loslaufen lassen.
      simulation.stop()
    }

    const g = svg.append('g')

    // Edge-Labels werden bei sehr weit rausgezoomtem Graph automatisch ausgeblendet,
    // damit dichte Stellen lesbar bleiben. Schwelle bewusst niedrig (0.6), damit normales
    // Zoomverhalten die Labels nicht plötzlich verliert. Toggle-State dominiert weiterhin.
    const EDGE_LABEL_AUTO_HIDE_ZOOM = 0.6
    let _zoomedOut = false

    // reason: d3.zoom() requires Selection<Element,...> but d3.select(svgEl) returns
    // Selection<SVGSVGElement,...>; cast is safe because SVGSVGElement extends Element.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const zoomBehavior = (d3.zoom() as any)
      .extent([[0, 0], [width, height]])
      .scaleExtent([0.1, 4])
      .on('zoom', (event: any) => {
        _currentTransform = event.transform
        g.attr('transform', event.transform)
        const wantsHide = event.transform.k < EDGE_LABEL_AUTO_HIDE_ZOOM
        if (wantsHide !== _zoomedOut) {
          _zoomedOut = wantsHide
          const visible = showEdgeLabels.value && !_zoomedOut
          if (linkLabelsRef) linkLabelsRef.style('display', visible ? 'block' : 'none')
          if (linkLabelBgRef) linkLabelBgRef.style('display', visible ? 'block' : 'none')
        }
        // Issue #744 Phase 4b — mirror viewport transform for the Mini-Map.
        minimapViewport.value = {
          x: event.transform.x,
          y: event.transform.y,
          k: event.transform.k,
          width,
          height,
        }
      })

    // Issue #744 Phase 4b — keep refs so panToGraphPoint() can drive the zoom
    // programmatically (Mini-Map click/drag → center main viewport).
    _zoomBehavior = zoomBehavior
    _svgSelection = svg
    _containerWidth = width
    _containerHeight = height
    // The initial viewport matches an untransformed view.
    _currentTransform = { x: 0, y: 0, k: 1 }
    minimapViewport.value = { x: 0, y: 0, k: 1, width, height }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(svg as any).call(zoomBehavior)

    const linkGroup = g.append('g').attr('class', 'links')

    const link = linkGroup.selectAll('path')
      .data(edges)
      .enter().append('path')
      .attr('stroke', 'var(--rule-strong)')
      .attr('stroke-width', 1.5)
      .attr('fill', 'none')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        linkLabelBg.attr('fill', 'var(--bg-inverse)')
        linkLabels.attr('fill', 'var(--fg-meta)')
        d3.select(event.target).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

    const linkLabelBg = linkGroup.selectAll('rect')
      .data(edges)
      .enter().append('rect')
      .attr('fill', 'var(--bg-inverse)')
      .attr('rx', 3)
      .attr('ry', 3)
      .style('cursor', 'pointer')
      .style('pointer-events', 'all')
      .style('display', showEdgeLabels.value ? 'block' : 'none')
      .on('click', (event, d) => {
        event.stopPropagation()
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        linkLabelBg.attr('fill', 'var(--bg-inverse)')
        linkLabels.attr('fill', 'var(--fg-meta)')
        link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
        d3.select(event.target).attr('fill', 'var(--plasma-soft)')

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

    const linkLabels = linkGroup.selectAll('text')
      .data(edges)
      .enter().append('text')
      // reason: formatEdgeLabel is JS (checkJs=false); translateLabel null triggers TS type error
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .text((d: any) => formatEdgeLabel(d.name, translateLabel as any))
      .attr('font-size', '12px')
      .attr('fill', 'var(--fg-meta)')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .style('cursor', 'pointer')
      .style('pointer-events', 'all')
      .style('font-family', 'system-ui, sans-serif')
      .style('display', showEdgeLabels.value ? 'block' : 'none')
      .on('click', (event, d) => {
        event.stopPropagation()
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        linkLabelBg.attr('fill', 'var(--bg-inverse)')
        linkLabels.attr('fill', 'var(--fg-meta)')
        link.filter(l => l === d).attr('stroke', 'var(--plasma-400)').attr('stroke-width', 3)
        d3.select(event.target).attr('fill', 'var(--plasma-400)')

        selectedItem.value = {
          type: 'edge',
          data: d.rawData,
        }
      })

    linkLabelsRef = linkLabels
    linkLabelBgRef = linkLabelBg

    const nodeGroup = g.append('g').attr('class', 'nodes')

    const node = nodeGroup.selectAll('circle')
      .data(nodes)
      .enter().append('circle')
      .attr('r', 10)
      .attr('fill', d => getColor(d.type))
      .attr('stroke', 'var(--mono-50)')
      .attr('stroke-width', 2.5)
      .style('cursor', 'pointer')
      // reason: d3.drag() requires Selection<Element,...>; GraphNodeViewModel from
      // a JS module does not satisfy d3's datum constraints — cast is safe at runtime.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .call((d3.drag() as any)
        .on('start', (event: any, d: any) => {
          d.fx = d.x
          d.fy = d.y
          d._dragStartX = event.x
          d._dragStartY = event.y
          d._isDragging = false
        })
        .on('drag', (event: any, d: any) => {
          const dx = event.x - d._dragStartX
          const dy = event.y - d._dragStartY
          const distance = Math.sqrt(dx * dx + dy * dy)

          if (!d._isDragging && distance > 3) {
            d._isDragging = true
            simulation.alphaTarget(0.3).restart()
          }

          if (d._isDragging) {
            d.fx = event.x
            d.fy = event.y
          }
        })
        .on('end', (event: any, d: any) => {
          if (d._isDragging) {
            simulation.alphaTarget(0)
            // Issue #744 Phase 4a — keep the node pinned at the dropped
            // position (fx/fy) and persist the full layout to localStorage
            // so it survives re-renders and is restored on next render().
            d.fx = d.x
            d.fy = d.y
            if (currentGraphId) saveNodeLayout(currentGraphId, nodes)
          } else {
            // Click without drag → release the temporary pin set in 'start'.
            d.fx = null
            d.fy = null
          }
          d._isDragging = false
        }),
      )
      .on('click', (event, d) => {
        event.stopPropagation()
        node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
        linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
        d3.select(event.target).attr('stroke', 'var(--accent)').attr('stroke-width', 4)
        link.filter(l => l.source.id === d.id || l.target.id === d.id)
          .attr('stroke', 'var(--accent)')
          .attr('stroke-width', 2.5)

        selectedItem.value = {
          type: 'node',
          data: d.rawData,
          entityType: d.type,
          color: getColor(d.type),
        }
      })
      .on('mouseenter', (event: any, d: any) => {
        // reason: d.rawData is typed as `object` from JSDoc; index access via any is safe
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const dataUuid = (selectedItem.value?.data as any)?.uuid
        if (!selectedItem.value || dataUuid !== (d.rawData as any).uuid) {
          d3.select(event.target).attr('stroke', 'var(--fg-on-inverse)').attr('stroke-width', 3)
        }
      })
      .on('mouseleave', (event: any, d: any) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const dataUuid = (selectedItem.value?.data as any)?.uuid
        if (!selectedItem.value || dataUuid !== (d.rawData as any).uuid) {
          d3.select(event.target).attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
        }
      })

    // Entitäts-Label: bis 14 Zeichen voll, sonst Trunkation mit Ellipsis. Voller Name
    // bleibt im SVG-`<title>` als nativer Browser-Tooltip erreichbar (Issue #129 SUB2).
    const NODE_LABEL_MAX = 14
    const nodeLabels = nodeGroup.selectAll('text')
      .data(nodes)
      .enter().append('text')
      .text(d => d.name.length > NODE_LABEL_MAX ? d.name.substring(0, NODE_LABEL_MAX) + '…' : d.name)
      .attr('font-size', '11px')
      .attr('fill', 'var(--fg-on-inverse)')
      .attr('font-weight', '500')
      .attr('dx', 14)
      .attr('dy', 4)
      .style('pointer-events', 'none')
      .style('font-family', 'system-ui, sans-serif')

    nodeLabels.append('title').text(d => d.name)
    node.append('title').text(d => d.name)

    simulation.on('tick', () => {
      link.attr('d', d => getLinkPath(d))

      linkLabels.each(function (d) {
        const mid = getLinkMidpoint(d)
        d3.select(this)
          .attr('x', mid.x)
          .attr('y', mid.y)
          .attr('transform', '')
      })

      linkLabelBg.each(function (d, i) {
        const mid = getLinkMidpoint(d)
        const textEl = linkLabels.nodes()[i]
        const bbox = textEl.getBBox()
        d3.select(this)
          .attr('x', mid.x - bbox.width / 2 - 6)
          .attr('y', mid.y - bbox.height / 2 - 3)
          .attr('width', bbox.width + 12)
          .attr('height', bbox.height + 6)
          .attr('transform', '')
      })

      node
        .attr('cx', d => d.x)
        .attr('cy', d => d.y)

      nodeLabels
        .attr('x', d => d.x)
        .attr('y', d => d.y)

      // Issue #744 Phase 4b — throttled rAF mirror of node positions for the
      // Mini-Map. Coalescing per animation frame avoids Vue-reactivity overhead
      // on every Force-Simulation tick (which fires far more often than 60 Hz).
      scheduleMinimapNodesUpdate(nodes)
    })

    svg.on('click', () => {
      selectedItem.value = null
      node.attr('stroke', 'var(--mono-50)').attr('stroke-width', 2.5)
      linkGroup.selectAll('path').attr('stroke', 'var(--rule-strong)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'var(--bg-inverse)')
      linkLabels.attr('fill', 'var(--fg-meta)')
    })
  }

  // Re-Render bei Datenwechsel (round-gefilterter Graph)
  watch(
    () => toValue(graphData),
    () => nextTick(render),
    { deep: true },
  )

  // Edge-Label-Sichtbarkeit live umschalten ohne Neuaufbau
  watch(showEdgeLabels, (newVal) => {
    if (linkLabelsRef) {
      linkLabelsRef.style('display', newVal ? 'block' : 'none')
    }
    if (linkLabelBgRef) {
      linkLabelBgRef.style('display', newVal ? 'block' : 'none')
    }
  })

  const handleResize = () => nextTick(render)

  onMounted(() => {
    window.addEventListener('resize', handleResize)
    nextTick(render)
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (currentSimulation) {
      currentSimulation.stop()
      currentSimulation = null
    }
  })

  /**
   * Pause/Resume der laufenden Force-Simulation. Issue #129 SUB3:
   * Während des Graph-Aufbaus ist die Animation oft hektisch — Pause
   * friert die aktuelle Position ein, Resume nimmt den Layout-Fluss
   * wieder auf (schwacher Alpha, damit nichts springt).
   *
   * Issue #137 SUB2: Diese öffentlichen Methoden markieren einen manuellen
   * Pause-Intent (`_isManuallyPaused`). Auto-Freeze respektiert diesen Flag
   * und ruft kein automatisches resumeSimulation, wenn der User bereits
   * manuell pausiert hat.
   */
  function pauseSimulation() {
    _isManuallyPaused = true
    isPaused.value = true
    if (currentSimulation) currentSimulation.stop()
  }

  function resumeSimulation() {
    _isManuallyPaused = false
    isPaused.value = false
    if (currentSimulation) {
      currentSimulation.alpha(0.3).alphaTarget(0).restart()
    }
  }

  function togglePause() {
    if (isPaused.value) resumeSimulation()
    else pauseSimulation()
  }

  /**
   * Issue #744 Phase 4a — clear the persisted pinch layout for the current
   * graph and re-render so all nodes float freely again (fx/fy = null because
   * no saved layout is applied). Auto-Freeze / manual-pause state is left
   * untouched; render() re-creates the simulation regardless.
   */
  function resetLayout() {
    if (currentGraphId) clearNodeLayout(currentGraphId)
    render()
  }

  /**
   * Issue #744 Phase 4b — throttle Mini-Map node updates to one per animation
   * frame. Forces a fresh array so Vue reactivity actually triggers.
   */
  function scheduleMinimapNodesUpdate(
    nodes: ReadonlyArray<{ id: string; x: number; y: number }>,
  ) {
    if (_minimapRafHandle !== null) return
    _minimapRafHandle = requestAnimationFrame(() => {
      _minimapRafHandle = null
      minimapNodes.value = nodes.map(n => ({ id: n.id, x: n.x, y: n.y }))
    })
  }

  /**
   * Issue #744 Phase 4b — pan the main viewport so the given graph-space point
   * is centered. Drives the stored d3.zoom behavior programmatically, which
   * fires the zoom handler and thereby re-renders the Mini-Map viewport rect.
   */
  function panToGraphPoint(gx: number, gy: number) {
    if (!_svgSelection || !_zoomBehavior) return
    const k = _currentTransform.k || 1
    const tx = _containerWidth / 2 - gx * k
    const ty = _containerHeight / 2 - gy * k
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const newTransform = (d3.zoomIdentity as any).translate(tx, ty).scale(k)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(_svgSelection as any).call(_zoomBehavior.transform, newTransform)
  }

  /**
   * Internal-only auto-freeze: pauses the simulation without setting the
   * manual-pause flag. After `autoFreezeMs` the simulation auto-resumes
   * unless the user has manually paused in the meantime.
   */
  function _triggerAutoFreeze() {
    // Clear any previous pending timer to avoid double-resume.
    if (_autoFreezeTimer !== null) {
      clearTimeout(_autoFreezeTimer)
      _autoFreezeTimer = null
    }

    _autoFreezeActive = true
    isPaused.value = true
    if (currentSimulation) currentSimulation.stop()

    _autoFreezeTimer = setTimeout(() => {
      _autoFreezeTimer = null
      _autoFreezeActive = false
      // Only resume if the user has NOT manually paused during the freeze window.
      if (!_isManuallyPaused) {
        isPaused.value = false
        if (currentSimulation) {
          currentSimulation.alpha(0.3).alphaTarget(0).restart()
        }
      }
    }, autoFreezeMs)
  }

  // Wire batchSignal → Auto-Freeze when provided.
  if (batchSignal !== undefined) {
    watch(
      () => toValue(batchSignal)?.batch_count,
      (newCount, oldCount) => {
        if (newCount === undefined || newCount === null) return
        if (newCount > (oldCount ?? 0)) {
          // New batch committed — only trigger if user has not manually paused.
          if (!_isManuallyPaused) {
            _triggerAutoFreeze()
          }
        }
      },
    )
  }

  // Cancel any pending Auto-Freeze timer when the composable scope is disposed.
  onScopeDispose(() => {
    if (_autoFreezeTimer !== null) {
      clearTimeout(_autoFreezeTimer)
      _autoFreezeTimer = null
    }
    if (_minimapRafHandle !== null) {
      cancelAnimationFrame(_minimapRafHandle)
      _minimapRafHandle = null
    }
  })

  return {
    selectedItem,
    render,
    isPaused,
    pauseSimulation,
    resumeSimulation,
    togglePause,
    resetLayout,
    minimapNodes,
    minimapViewport,
    panToGraphPoint,
  }
}
