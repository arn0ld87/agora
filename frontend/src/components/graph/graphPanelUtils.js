const ENTITY_TYPE_COLORS = [
  'var(--accent)',
  'var(--plasma-600)',
  'var(--plasma-400)',
  'var(--status-success)',
  'var(--status-error)',
  'var(--status-warn)',
  'var(--plasma-500)',
  'var(--plasma-200)',
  'var(--status-success)',
  'var(--status-warn)',
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
