/** Simple flat spatial index for 2D picking against galaxy x/y. */
export function buildSpatialIndex(systems) {
  const cells = new Map()
  const cellSize = 0.06

  const keyFor = (x, y) => `${Math.floor(x / cellSize)}:${Math.floor(y / cellSize)}`

  for (const system of systems) {
    const key = keyFor(system.x, system.y)
    if (!cells.has(key)) cells.set(key, [])
    cells.get(key).push(system)
  }

  function collectAround(x, y, radiusCells) {
    const cx = Math.floor(x / cellSize)
    const cy = Math.floor(y / cellSize)
    const out = []
    for (let dx = -radiusCells; dx <= radiusCells; dx += 1) {
      for (let dy = -radiusCells; dy <= radiusCells; dy += 1) {
        const bucket = cells.get(`${cx + dx}:${cy + dy}`)
        if (bucket) out.push(...bucket)
      }
    }
    return out
  }

  return {
    queryNearest(x, y, maxDist = 0.04) {
      const radius = Math.max(1, Math.ceil(maxDist / cellSize))
      let best = null
      let bestDist = maxDist
      for (const system of collectAround(x, y, radius)) {
        const dist = Math.hypot(system.x - x, system.y - y)
        if (dist < bestDist) {
          bestDist = dist
          best = system
        }
      }
      return best
    },
    /** Nearest system with expanding search — for continuous territory fill. */
    queryNearestAny(x, y) {
      const maxR = 48
      for (let radius = 1; radius <= maxR; radius += 1) {
        let best = null
        let bestDist = Infinity
        for (const system of collectAround(x, y, radius)) {
          const dist = Math.hypot(system.x - x, system.y - y)
          if (dist < bestDist) {
            bestDist = dist
            best = system
          }
        }
        if (best && bestDist <= radius * cellSize) return best
      }
      return null
    },
    queryNearestDistance(system, maxDist = 0.2) {
      const radius = Math.max(1, Math.ceil(maxDist / cellSize))
      let bestDist = maxDist
      for (const other of collectAround(system.x, system.y, radius)) {
        if (other.id === system.id) continue
        const dist = Math.hypot(other.x - system.x, other.y - system.y)
        if (dist < bestDist) bestDist = dist
      }
      return bestDist < maxDist ? bestDist : null
    },
  }
}
