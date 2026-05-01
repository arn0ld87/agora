/**
 * Issue #36 — Stabile Node-/Edge-ViewModels für die Graph-UI.
 *
 * Backend-Edges tragen historisch zwei alternative Felder für Beziehungs-Typ
 * und -Label (`fact_type` aus früherer NER-Pipeline, `name` aus dem aktuellen
 * Schema). Hier landet die einzige Stelle, an der dieser Legacy-Alias
 * aufgelöst wird; die UI-Komponenten konsumieren nur noch das normalisierte
 * Result.
 *
 * @typedef {object} GraphNodeViewModel
 * @property {string} id        – stabile Node-ID (UUID des Backends)
 * @property {string} name      – Anzeige-Name, fällt auf 'Unnamed' zurück
 * @property {string} type      – Entity-Typ-Label aus Neo4j-Labels
 * @property {object} rawData   – ungemappter Backend-Node für Detail-Panel
 *
 * @typedef {object} GraphEdgeViewModel
 * @property {string}  source       – Source-Node-UUID (für d3-forceLink)
 * @property {string}  target       – Target-Node-UUID
 * @property {string}  type         – Beziehungs-Typ (alias-aufgelöst)
 * @property {string}  name         – Anzeige-Label (alias-aufgelöst)
 * @property {number}  curvature    – Pfad-Krümmung für mehrfach-Edges
 * @property {boolean} isSelfLoop   – `true` bei Self-Loop-Aggregat
 * @property {number} [pairIndex]   – Index in der Paar-Gruppe (nicht-Self-Loops)
 * @property {number} [pairTotal]   – Gesamtzahl Edges zwischen demselben Paar
 * @property {object}  rawData      – ungemapptes Backend-Edge plus aufgelöste Namen
 */

function getNodeType(node) {
  return node.labels?.find((label) => label !== 'Entity') || 'Entity'
}

/**
 * Löst die Backend-Aliasse `fact_type` und `name` zu einem stabilen
 * `{ type, label }`-Paar auf. Einziger Ort der Alias-Logik.
 *
 * Backend-Konvention:
 *  - Aktuelles Schema: `name` ist das Beziehungs-Label.
 *  - Legacy NER-Pipeline: `fact_type` lieferte Typ und Label.
 *
 * Mapping:
 *  - `type`  bevorzugt `fact_type`, fällt auf `name`, dann `'RELATED'` zurück.
 *  - `label` bevorzugt `name`, fällt auf `fact_type`, dann `'RELATED'` zurück.
 */
function normalizeEdgeAliases(edge) {
  const factType = edge.fact_type
  const name = edge.name
  return {
    type: factType || name || 'RELATED',
    label: name || factType || 'RELATED',
  }
}

function buildColorMap(entityTypes) {
  const colorMap = {}
  for (const entityType of entityTypes) {
    colorMap[entityType.name] = entityType.color
  }
  return colorMap
}

function buildGraphNodes(nodesData) {
  return nodesData.map((node) => ({
    id: node.uuid,
    name: node.name || 'Unnamed',
    type: getNodeType(node),
    rawData: node,
  }))
}

function buildSelfLoopLookup(candidateEdges, nodeMap) {
  const selfLoopEdges = {}

  for (const edge of candidateEdges) {
    if (edge.source_node_uuid !== edge.target_node_uuid) {
      continue
    }

    if (!selfLoopEdges[edge.source_node_uuid]) {
      selfLoopEdges[edge.source_node_uuid] = []
    }

    selfLoopEdges[edge.source_node_uuid].push({
      ...edge,
      source_name: nodeMap[edge.source_node_uuid]?.name,
      target_name: nodeMap[edge.target_node_uuid]?.name,
    })
  }

  return selfLoopEdges
}

function buildPairCountLookup(candidateEdges) {
  const edgePairCount = {}

  for (const edge of candidateEdges) {
    if (edge.source_node_uuid === edge.target_node_uuid) {
      continue
    }

    const pairKey = [edge.source_node_uuid, edge.target_node_uuid].sort().join('_')
    edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
  }

  return edgePairCount
}

function buildCurvedEdge(edge, edgePairCount, edgePairIndex, nodeMap) {
  const pairKey = [edge.source_node_uuid, edge.target_node_uuid].sort().join('_')
  const totalCount = edgePairCount[pairKey]
  const currentIndex = edgePairIndex[pairKey] || 0
  edgePairIndex[pairKey] = currentIndex + 1

  const isReversed = edge.source_node_uuid > edge.target_node_uuid
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
    source: edge.source_node_uuid,
    target: edge.target_node_uuid,
    type: aliases.type,
    name: aliases.label,
    curvature,
    isSelfLoop: false,
    pairIndex: currentIndex,
    pairTotal: totalCount,
    rawData: {
      ...edge,
      source_name: nodeMap[edge.source_node_uuid]?.name,
      target_name: nodeMap[edge.target_node_uuid]?.name,
    },
  }
}

function buildSelfLoopEdge(edge, selfLoopEdges, nodeMap) {
  const allSelfLoops = selfLoopEdges[edge.source_node_uuid]
  const nodeName = nodeMap[edge.source_node_uuid]?.name || 'Unknown'

  return {
    source: edge.source_node_uuid,
    target: edge.target_node_uuid,
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

function buildGraphEdges(candidateEdges, selfLoopEdges, edgePairCount, nodeMap) {
  const processedSelfLoopNodes = new Set()
  const edgePairIndex = {}
  const edges = []

  for (const edge of candidateEdges) {
    const isSelfLoop = edge.source_node_uuid === edge.target_node_uuid

    if (isSelfLoop) {
      if (processedSelfLoopNodes.has(edge.source_node_uuid)) {
        continue
      }
      processedSelfLoopNodes.add(edge.source_node_uuid)
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
export function getMaxRoundFromEdges(edges) {
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
export function filterEdgesAtRound(edges, round) {
  if (!Array.isArray(edges)) return []
  if (round == null) return edges
  return edges.filter((edge) => {
    const from = typeof edge?.valid_from_round === 'number' ? edge.valid_from_round : 0
    const to = edge?.valid_to_round
    if (from > round) return false
    if (to != null && to <= round) return false
    return true
  })
}

/**
 * Public-API des Daten-Mappers. Liefert die UI-konsumierten ViewModels plus
 * die Farbabbildung. UI-Komponenten greifen NICHT direkt auf das Backend-
 * Format zu, sondern lesen ausschließlich diese ViewModels.
 *
 * @param {{ nodes?: Array, edges?: Array }} graphData – Rohformat vom Backend
 * @param {Array<{ name: string, color: string }>} [entityTypes=[]] – Farb-Mapping
 * @returns {{
 *   nodes: GraphNodeViewModel[],
 *   edges: GraphEdgeViewModel[],
 *   getColor: (type: string) => string,
 * }}
 */
export function buildGraphRenderData(graphData, entityTypes = []) {
  const nodesData = graphData?.nodes || []
  const edgesData = graphData?.edges || []
  const nodes = buildGraphNodes(nodesData)
  const nodeMap = Object.fromEntries(nodesData.map((node) => [node.uuid, node]))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const candidateEdges = edgesData.filter(
    (edge) => nodeIds.has(edge.source_node_uuid) && nodeIds.has(edge.target_node_uuid),
  )

  const selfLoopEdges = buildSelfLoopLookup(candidateEdges, nodeMap)
  const edgePairCount = buildPairCountLookup(candidateEdges)
  const edges = buildGraphEdges(candidateEdges, selfLoopEdges, edgePairCount, nodeMap)
  const colorMap = buildColorMap(entityTypes)

  return {
    nodes,
    edges,
    getColor(type) {
      return colorMap[type] || 'var(--fg-muted)'
    },
  }
}
