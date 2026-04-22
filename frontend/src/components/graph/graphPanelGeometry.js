const SELF_LOOP_RADIUS = 30
const SELF_LOOP_PATH_OFFSET_X = 8
const SELF_LOOP_PATH_OFFSET_TOP_Y = -4
const SELF_LOOP_PATH_OFFSET_BOTTOM_Y = 4
const SELF_LOOP_LABEL_OFFSET_X = 70
const MIN_CURVE_OFFSET = 35
const CURVE_OFFSET_BASE_RATIO = 0.25
const CURVE_OFFSET_PAIR_RATIO = 0.05

function getCurveControlPoint(edge) {
  const sx = edge.source.x
  const sy = edge.source.y
  const tx = edge.target.x
  const ty = edge.target.y
  const dx = tx - sx
  const dy = ty - sy
  const dist = Math.sqrt(dx * dx + dy * dy)
  const pairTotal = edge.pairTotal || 1
  const offsetRatio = CURVE_OFFSET_BASE_RATIO + pairTotal * CURVE_OFFSET_PAIR_RATIO
  const baseOffset = Math.max(MIN_CURVE_OFFSET, dist * offsetRatio)
  const offsetX = (-dy / dist) * edge.curvature * baseOffset
  const offsetY = (dx / dist) * edge.curvature * baseOffset

  return {
    x: (sx + tx) / 2 + offsetX,
    y: (sy + ty) / 2 + offsetY,
  }
}

export function getLinkPath(edge) {
  const sx = edge.source.x
  const sy = edge.source.y
  const tx = edge.target.x
  const ty = edge.target.y

  if (edge.isSelfLoop) {
    const x1 = sx + SELF_LOOP_PATH_OFFSET_X
    const y1 = sy + SELF_LOOP_PATH_OFFSET_TOP_Y
    const x2 = sx + SELF_LOOP_PATH_OFFSET_X
    const y2 = sy + SELF_LOOP_PATH_OFFSET_BOTTOM_Y
    return `M${x1},${y1} A${SELF_LOOP_RADIUS},${SELF_LOOP_RADIUS} 0 1,1 ${x2},${y2}`
  }

  if (edge.curvature === 0) {
    return `M${sx},${sy} L${tx},${ty}`
  }

  const controlPoint = getCurveControlPoint(edge)
  return `M${sx},${sy} Q${controlPoint.x},${controlPoint.y} ${tx},${ty}`
}

export function getLinkMidpoint(edge) {
  const sx = edge.source.x
  const sy = edge.source.y
  const tx = edge.target.x
  const ty = edge.target.y

  if (edge.isSelfLoop) {
    return { x: sx + SELF_LOOP_LABEL_OFFSET_X, y: sy }
  }

  if (edge.curvature === 0) {
    return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
  }

  const controlPoint = getCurveControlPoint(edge)
  return {
    x: 0.25 * sx + 0.5 * controlPoint.x + 0.25 * tx,
    y: 0.25 * sy + 0.5 * controlPoint.y + 0.25 * ty,
  }
}
