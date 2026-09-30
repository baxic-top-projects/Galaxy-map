/**
 * Interior territory anchors for polity labels (normalized UV, y-down).
 * Prefer the pole of inaccessibility of the largest connected region so labels
 * stay inside the painted territory instead of sitting on borders.
 */

/**
 * @param {Int32Array|number[]} owner owner[i] = system index or -1
 * @param {{ polityStem: string }[]} systemMeta
 * @param {number} size square raster edge
 * @returns {Record<string, [number, number]>}
 */
export function centroidsFromOwnerRaster(owner, systemMeta, size) {
  /** @type {Map<string, number>} */
  const stemIds = new Map()
  /** @type {string[]} */
  const stems = []
  const stemOf = new Int16Array(owner.length)
  stemOf.fill(-1)

  for (let i = 0; i < owner.length; i += 1) {
    const idx = owner[i]
    if (idx < 0) continue
    const stem = systemMeta[idx]?.polityStem
    if (!stem || stem === '__neutral__') continue
    let id = stemIds.get(stem)
    if (id == null) {
      id = stems.length
      stemIds.set(stem, id)
      stems.push(stem)
    }
    stemOf[i] = id
  }

  /** @type {Record<string, [number, number]>} */
  const anchors = {}
  const denom = Math.max(size - 1, 1)
  const seen = new Uint8Array(owner.length)
  const queue = new Int32Array(owner.length)

  for (let stemId = 0; stemId < stems.length; stemId += 1) {
    let bestCount = 0
    let bestStart = -1

    for (let i = 0; i < owner.length; i += 1) {
      if (stemOf[i] !== stemId || seen[i]) continue
      let head = 0
      let tail = 0
      queue[tail++] = i
      seen[i] = 1
      let count = 0
      const start = i
      while (head < tail) {
        const cur = queue[head++]
        count += 1
        const x = cur % size
        const y = (cur / size) | 0
        if (x > 0) {
          const n = cur - 1
          if (stemOf[n] === stemId && !seen[n]) {
            seen[n] = 1
            queue[tail++] = n
          }
        }
        if (x + 1 < size) {
          const n = cur + 1
          if (stemOf[n] === stemId && !seen[n]) {
            seen[n] = 1
            queue[tail++] = n
          }
        }
        if (y > 0) {
          const n = cur - size
          if (stemOf[n] === stemId && !seen[n]) {
            seen[n] = 1
            queue[tail++] = n
          }
        }
        if (y + 1 < size) {
          const n = cur + size
          if (stemOf[n] === stemId && !seen[n]) {
            seen[n] = 1
            queue[tail++] = n
          }
        }
      }
      if (count > bestCount) {
        bestCount = count
        bestStart = start
      }
    }

    if (bestStart < 0 || bestCount === 0) continue

    const component = new Uint8Array(owner.length)
    let head = 0
    let tail = 0
    queue[tail++] = bestStart
    component[bestStart] = 1
    let sx = 0
    let sy = 0
    while (head < tail) {
      const cur = queue[head++]
      const x = cur % size
      const y = (cur / size) | 0
      sx += x
      sy += y
      if (x > 0) {
        const n = cur - 1
        if (stemOf[n] === stemId && !component[n]) {
          component[n] = 1
          queue[tail++] = n
        }
      }
      if (x + 1 < size) {
        const n = cur + 1
        if (stemOf[n] === stemId && !component[n]) {
          component[n] = 1
          queue[tail++] = n
        }
      }
      if (y > 0) {
        const n = cur - size
        if (stemOf[n] === stemId && !component[n]) {
          component[n] = 1
          queue[tail++] = n
        }
      }
      if (y + 1 < size) {
        const n = cur + size
        if (stemOf[n] === stemId && !component[n]) {
          component[n] = 1
          queue[tail++] = n
        }
      }
    }

    const dist = new Int16Array(owner.length)
    dist.fill(-1)
    head = 0
    tail = 0
    for (let i = 0; i < owner.length; i += 1) {
      if (!component[i]) continue
      const x = i % size
      const y = (i / size) | 0
      const exterior =
        x === 0 ||
        y === 0 ||
        x === size - 1 ||
        y === size - 1 ||
        !component[i - 1] ||
        !component[i + 1] ||
        !component[i - size] ||
        !component[i + size]
      if (!exterior) continue
      dist[i] = 0
      queue[tail++] = i
    }

    while (head < tail) {
      const cur = queue[head++]
      const nextDist = dist[cur] + 1
      const x = cur % size
      const y = (cur / size) | 0
      const neighbors = []
      if (x > 0) neighbors.push(cur - 1)
      if (x + 1 < size) neighbors.push(cur + 1)
      if (y > 0) neighbors.push(cur - size)
      if (y + 1 < size) neighbors.push(cur + size)
      for (const n of neighbors) {
        if (!component[n] || dist[n] >= 0) continue
        dist[n] = nextDist
        queue[tail++] = n
      }
    }

    const meanX = sx / bestCount
    const meanY = sy / bestCount
    let bestPixel = bestStart
    let bestScore = -1
    let bestTie = Infinity
    for (let i = 0; i < owner.length; i += 1) {
      if (!component[i]) continue
      const d = dist[i] < 0 ? 0 : dist[i]
      const x = i % size
      const y = (i / size) | 0
      const tie = (x - meanX) * (x - meanX) + (y - meanY) * (y - meanY)
      if (d > bestScore || (d === bestScore && tie < bestTie)) {
        bestScore = d
        bestTie = tie
        bestPixel = i
      }
    }

    anchors[stems[stemId]] = [
      (bestPixel % size) / denom,
      ((bestPixel / size) | 0) / denom,
    ]
  }

  return anchors
}

/**
 * Fallback anchors from mean host-system positions in map UV space.
 * @param {{ systems?: Array<{ stem?: string, kind?: string, x: number, y: number }> }} galaxy
 * @param {number} mapLim
 * @returns {Record<string, [number, number]>}
 */
export function centroidsFromSystems(galaxy, mapLim = 1.06) {
  /** @type {Map<string, { sx: number, sy: number, n: number }>} */
  const sums = new Map()
  for (const system of galaxy.systems || []) {
    if (!system.stem) continue
    if (system.kind === 'junction' || system.kind === 'well') continue
    let acc = sums.get(system.stem)
    if (!acc) {
      acc = { sx: 0, sy: 0, n: 0 }
      sums.set(system.stem, acc)
    }
    const u = (system.x / mapLim + 1) / 2
    const v = (-system.y / mapLim + 1) / 2
    acc.sx += u
    acc.sy += v
    acc.n += 1
  }
  /** @type {Record<string, [number, number]>} */
  const anchors = {}
  for (const [stem, acc] of sums) {
    anchors[stem] = [acc.sx / acc.n, acc.sy / acc.n]
  }
  return anchors
}

/**
 * Prefer painted-territory centroids, then system means, then seed anchors.
 * @param {Record<string, [number, number]>} painted
 * @param {Record<string, [number, number]>} fromSystems
 * @param {Record<string, [number, number]>} seed
 * @param {Array<{ stem: string }>} polities
 */
export function resolvePolityLabelAnchors(painted, fromSystems, seed, polities) {
  /** @type {Record<string, [number, number]>} */
  const out = {}
  for (const polity of polities || []) {
    const stem = polity.stem
    if (!stem) continue
    out[stem] = painted[stem] || fromSystems[stem] || seed[stem] || null
  }
  for (const stem of Object.keys(out)) {
    if (!out[stem]) delete out[stem]
  }
  return out
}

/**
 * Scale label text by the territory's linear size (sqrt of raster area).
 * @param {number} area
 * @param {number} largestArea
 * @param {number} minSize
 * @param {number} maxSize
 */
export function polityLabelFontSize(area, largestArea, minSize = 8, maxSize = 22) {
  if (!(area > 0) || !(largestArea > 0)) return minSize
  const ratio = Math.min(1, area / largestArea)
  return minSize + (maxSize - minSize) * Math.sqrt(ratio)
}
