const ENTITY_TYPE_COLORS = [
  '#FF6B35',
  '#004E89',
  '#7B2D8E',
  '#1A936F',
  '#C5283D',
  '#E9724C',
  '#3498db',
  '#9b59b6',
  '#27ae60',
  '#f39c12',
]

export function buildEntityTypes(graphData) {
  if (!graphData?.nodes) return []

  const typeMap = {}
  for (const node of graphData.nodes) {
    const type = node.labels?.find((label) => label !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = {
        name: type,
        count: 0,
        color: ENTITY_TYPE_COLORS[Object.keys(typeMap).length % ENTITY_TYPE_COLORS.length],
      }
    }
    typeMap[type].count += 1
  }

  return Object.values(typeMap)
}

export function formatDateTime(dateStr) {
  if (!dateStr) return ''

  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    })
  } catch {
    return dateStr
  }
}
