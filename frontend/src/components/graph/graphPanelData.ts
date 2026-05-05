/**
 * Issue #36 — Stabile Node-/Edge-ViewModels für die Graph-UI.
 *
 * Backend-Edges tragen historisch zwei alternative Felder für Beziehungs-Typ
 * und -Label (`fact_type` aus früherer NER-Pipeline, `name` aus dem aktuellen
 * Schema). Hier landet die einzige Stelle, an der dieser Legacy-Alias
 * aufgelöst wird; die UI-Komponenten konsumieren nur noch das normalisierte
 * Result.
 */

export interface GraphNodeViewModel {
  /** stabile Node-ID (UUID des Backends) */
  id: string
  /** Anzeige-Name, fällt auf 'Unnamed' zurück */
  name: string
  /** Entity-Typ-Label aus Neo4j-Labels */
  type: string
  /** ungemappter Backend-Node für Detail-Panel */
  rawData: Record<string, unknown>
}

export interface GraphEdgeViewModel {
  /** Source-Node-UUID (für d3-forceLink) */
  source: string
  /** Target-Node-UUID */
  target: string
  /** Beziehungs-Typ (alias-aufgelöst) */
  type: string
  /** Anzeige-Label (alias-aufgelöst) */
  name: string
  /** Pfad-Krümmung für mehrfach-Edges */
  curvature: number
  /** `true` bei Self-Loop-Aggregat */
  isSelfLoop: boolean
  /** Index in der Paar-Gruppe (nicht-Self-Loops) */
  pairIndex?: number
  /** Gesamtzahl Edges zwischen demselben Paar */
  pairTotal?: number
  /** ungemapptes Backend-Edge plus aufgelöste Namen */
  rawData: Record<string, unknown>
}

function getNodeType(node: Record<string, unknown>): string {
  const labels = node.labels as string[] | undefined
  return labels?.find((label) => label !== 'Entity') || 'Entity'
}

/**
 * Löst die Backend-Aliasse `fact_type` und `name` zu einem stabilen
 * `{ type, label }`-Paar auf. Einziger Ort der Alias-Logik.
 */
function normalizeEdgeAliases(edge: Record<string, unknown>): { type: string; label: string } {
  const factType = edge.fact_type as string | undefined
  const name = edge.name as string | undefined
  return {
    type: factType || name || 'RELATED',
    label: name || factType || 'RELATED',
  }
}

function buildColorMap(entityTypes: Array<{ name: string; color: string }>): Record<string, string> {
  const colorMap: Record<string, string> = {}
  for (const entityType of entityTypes) {
    colorMap[entityType.name] = entityType.color
  }
  return colorMap
}

function buildGraphNodes(nodesData: Array<Record<string, unknown>>): GraphNodeViewModel[] {
  return nodesData.map((node) => ({
    id: node.uuid as string,
    name: (node.name as string) || 'Unnamed',
    type: getNodeType(node),
    rawData: node,
  }))
}

function buildSelfLoopLookup(
  candidateEdges: Array<Record<string, unknown>>,
  nodeMap: Record<string, Record<string, unknown>>,
): Record<string, Array<Record<string, unknown>>> {
  const selfLoopEdges: Record<string, Array<Record<string, unknown>>> = {}

  for (const edge of candidateEdges) {
    if (edge.source_node_uuid !== edge.target_node_uuid) {
      continue
    }

    const uuid = edge.source_node_uuid as string
    if (!selfLoopEdges[uuid]) {
      selfLoopEdges[uuid] = []
    }

    selfLoopEdges[uuid].push({
      ...edge,
      source_name: nodeMap[uuid]?.name,
      target_name: nodeMap[edge.target_node_uuid as string]?.name,
    })
  }

  return selfLoopEdges
}

function buildPairCountLookup(candidateEdges: Array<Record<string, unknown>>): Record<string, number> {
  const edgePairCount: Record<string, number> = {}

  for (const edge of candidateEdges) {
    if (edge.source_node_uuid === edge.target_node_uuid) {
      continue
    }

    const pairKey = [edge.source_node_uuid, edge.target_node_uuid].sort().join('_')
    edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
  }

  return edgePairCount
}

function buildCurvedEdge(
  edge: Record<string, unknown>,
  edgePairCount: Record<string, number>,
  edgePairIndex: Record<string, number>,
  nodeMap: Record<string, Record<string, unknown>>,
): GraphEdgeViewModel {
  const pairKey = [edge.source_node_uuid, edge.target_node_uuid].sort().join('_')
  const totalCount = edgePairCount[pairKey]
  const currentIndex = edgePairIndex[pairKey] || 0
  edgePairIndex[pairKey] = currentIndex + 1

  const isReversed = (edge.source_node_uuid as string) > (edge.target_node_uuid as string)
  let curvature = 0

  if (totalCount > 1) {
    const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
    curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2
    if (isReversed) {
      curvature = -curvature
    }
  }

  const aliases = normalizeEdgeAliases(edge)

  return {
    source: edge.source_node_uuid as string,
    target: edge.target_node_uuid as string,
    type: aliases.type,
    name: aliases.label,
    curvature,
    isSelfLoop: false,
    pairIndex: currentIndex,
    pairTotal: totalCount,
    rawData: {
      ...edge,
      source_name: nodeMap[edge.source_node_uuid as string]?.name,
      target_name: nodeMap[edge.target_node_uuid as string]?.name,
    },
  }
}

function buildSelfLoopEdge(
  edge: Record<string, unknown>,
  selfLoopEdges: Record<string, Array<Record<string, unknown>>>,
  nodeMap: Record<string, Record<string, unknown>>,
): GraphEdgeViewModel {
  const uuid = edge.source_node_uuid as string
  const allSelfLoops = selfLoopEdges[uuid]
  const nodeName = (nodeMap[uuid]?.name as string) || 'Unknown'

  return {
    source: uuid,
    target: edge.target_node_uuid as string,
    type: 'SELF_LOOP',
    name: `Self Relations (${allSelfLoops.length})`,
    curvature: 0,
    isSelfLoop: true,
    rawData: {
      isSelfLoopGroup: true,
      source_name: nodeName,
      target_name: nodeName,
      selfLoopCount: allSelfLoops.length,
      selfLoopEdges: allSelfLoops,
    },
  }
}

function buildGraphEdges(
  candidateEdges: Array<Record<string, unknown>>,
  selfLoopEdges: Record<string, Array<Record<string, unknown>>>,
  edgePairCount: Record<string, number>,
  nodeMap: Record<string, Record<string, unknown>>,
): GraphEdgeViewModel[] {
  const processedSelfLoopNodes = new Set<string>()
  const edgePairIndex: Record<string, number> = {}
  const edges: GraphEdgeViewModel[] = []

  for (const edge of candidateEdges) {
    const isSelfLoop = edge.source_node_uuid === edge.target_node_uuid

    if (isSelfLoop) {
      const uuid = edge.source_node_uuid as string
      if (processedSelfLoopNodes.has(uuid)) {
        continue
      }
      processedSelfLoopNodes.add(uuid)
      edges.push(buildSelfLoopEdge(edge, selfLoopEdges, nodeMap))
      continue
    }

    edges.push(buildCurvedEdge(edge, edgePairCount, edgePairIndex, nodeMap))
  }

  return edges
}

/**
 * Issue #10 — Highest valid_from_round seen across the edge list. Returns 0
 * for graphs that never went through a simulation (no temporal stamps).
 * Treats missing values as 0 (legacy edges before #10 backfill).
 */
export function getMaxRoundFromEdges(edges: Array<Record<string, unknown>>): number {
  if (!Array.isArray(edges) || edges.length === 0) return 0
  let max = 0
  for (const edge of edges) {
    const from = edge?.valid_from_round
    if (typeof from === 'number' && from > max) max = from
    const to = edge?.valid_to_round
    if (typeof to === 'number' && to > max) max = to
  }
  return max
}

/**
 * Issue #10 — Local snapshot filter mirroring the backend's snapshot semantics:
 * an edge is "alive" at round R iff valid_from_round <= R and (valid_to_round
 * is null OR valid_to_round > R). Saves a round-trip during slider scrubbing.
 */
export function filterEdgesAtRound(
  edges: Array<Record<string, unknown>>,
  round: number | null | undefined,
): Array<Record<string, unknown>> {
  if (!Array.isArray(edges)) return []
  if (round == null) return edges
  return edges.filter((edge) => {
    const from = typeof edge?.valid_from_round === 'number' ? edge.valid_from_round : 0
    const to = edge?.valid_to_round
    if (from > round) return false
    if (to != null && typeof to === 'number' && to <= round) return false
    return true
  })
}

/**
 * Public-API des Daten-Mappers. Liefert die UI-konsumierten ViewModels plus
 * die Farbabbildung. UI-Komponenten greifen NICHT direkt auf das Backend-
 * Format zu, sondern lesen ausschließlich diese ViewModels.
 */
export function buildGraphRenderData(
  graphData: { nodes?: Array<Record<string, unknown>>; edges?: Array<Record<string, unknown>> } | null | undefined,
  entityTypes: Array<{ name: string; color: string }> = [],
): {
  nodes: GraphNodeViewModel[]
  edges: GraphEdgeViewModel[]
  getColor: (type: string) => string
} {
  const nodesData = graphData?.nodes || []
  const edgesData = graphData?.edges || []
  const nodes = buildGraphNodes(nodesData)
  const nodeMap = Object.fromEntries(nodesData.map((node) => [node.uuid as string, node]))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const candidateEdges = edgesData.filter(
    (edge) => nodeIds.has(edge.source_node_uuid as string) && nodeIds.has(edge.target_node_uuid as string),
  )

  const selfLoopEdges = buildSelfLoopLookup(candidateEdges, nodeMap)
  const edgePairCount = buildPairCountLookup(candidateEdges)
  const edges = buildGraphEdges(candidateEdges, selfLoopEdges, edgePairCount, nodeMap)
  const colorMap = buildColorMap(entityTypes)

  return {
    nodes,
    edges,
    getColor(type: string): string {
      return colorMap[type] || 'var(--fg-muted)'
    },
  }
}
