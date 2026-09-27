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

  return {
    queryNearest(x, y, maxDist = 0.04) {
      const cx = Math.floor(x / cellSize)
      const cy = Math.floor(y / cellSize)
      const radius = Math.max(1, Math.ceil(maxDist / cellSize))
      let best = null
      let bestDist = maxDist
      for (let dx = -radius; dx <= radius; dx += 1) {
        for (let dy = -radius; dy <= radius; dy += 1) {
          const bucket = cells.get(`${cx + dx}:${cy + dy}`)
          if (!bucket) continue
          for (const system of bucket) {
            const dist = Math.hypot(system.x - x, system.y - y)
            if (dist < bestDist) {
              bestDist = dist
              best = system
            }
          }
        }
      }
      return best
    },
  }
}
