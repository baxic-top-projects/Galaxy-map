/** Spatial tile helpers for viewport-driven galaxy loading. */

export const DEFAULT_TILE_GRID_SIZE = 16
export const DEFAULT_MAP_LIM = 1.06

export function tileKey(tx, ty) {
  return `${tx}:${ty}`
}

export function parseTileKey(key) {
  const [tx, ty] = String(key).split(':').map(Number)
  return { tx, ty }
}

export function clampTileIndex(value, size) {
  return Math.max(0, Math.min(size - 1, Math.floor(value)))
}

/**
 * Inclusive list of tiles overlapping an axis-aligned bounds in galaxy x/y.
 */
export function tilesForBounds(minX, maxX, minY, maxY, mapLim = DEFAULT_MAP_LIM, size = DEFAULT_TILE_GRID_SIZE) {
  const lim = Number(mapLim) > 0 ? Number(mapLim) : DEFAULT_MAP_LIM
  const grid = Number(size) > 0 ? Math.floor(Number(size)) : DEFAULT_TILE_GRID_SIZE
  const span = 2 * lim
  const left = Math.min(minX, maxX)
  const right = Math.max(minX, maxX)
  const bottom = Math.min(minY, maxY)
  const top = Math.max(minY, maxY)
  const minTx = clampTileIndex(((left + lim) / span) * grid, grid)
  const maxTx = clampTileIndex(((right + lim) / span) * grid, grid)
  const minTy = clampTileIndex(((bottom + lim) / span) * grid, grid)
  const maxTy = clampTileIndex(((top + lim) / span) * grid, grid)
  const tiles = []
  for (let tx = minTx; tx <= maxTx; tx += 1) {
    for (let ty = minTy; ty <= maxTy; ty += 1) {
      tiles.push({ tx, ty })
    }
  }
  return tiles
}

/** Expand a tile set by a Chebyshev ring (Google-style neighbor prefetch). */
export function expandTiles(tiles, ring = 1, size = DEFAULT_TILE_GRID_SIZE) {
  const grid = Number(size) > 0 ? Math.floor(Number(size)) : DEFAULT_TILE_GRID_SIZE
  const r = Math.max(0, Math.floor(ring))
  const seen = new Set()
  const out = []
  for (const tile of tiles || []) {
    for (let dx = -r; dx <= r; dx += 1) {
      for (let dy = -r; dy <= r; dy += 1) {
        const tx = tile.tx + dx
        const ty = tile.ty + dy
        if (tx < 0 || ty < 0 || tx >= grid || ty >= grid) continue
        const key = tileKey(tx, ty)
        if (seen.has(key)) continue
        seen.add(key)
        out.push({ tx, ty })
      }
    }
  }
  return out
}

/** All tiles in the grid (background prefetch). */
export function allTiles(size = DEFAULT_TILE_GRID_SIZE) {
  const grid = Number(size) > 0 ? Math.floor(Number(size)) : DEFAULT_TILE_GRID_SIZE
  const tiles = []
  for (let tx = 0; tx < grid; tx += 1) {
    for (let ty = 0; ty < grid; ty += 1) {
      tiles.push({ tx, ty })
    }
  }
  return tiles
}

/**
 * Approximate visible galaxy XY bounds from an orbit camera looking at z=0.
 * Uses target + distance-based half-extent (good enough for tile selection).
 */
export function boundsFromCameraView(target, distance, mapLim = DEFAULT_MAP_LIM) {
  const lim = Number(mapLim) > 0 ? Number(mapLim) : DEFAULT_MAP_LIM
  const dist = Math.max(4, Number(distance) || 40)
  // Wider when far (overview), tighter when zoomed in.
  const half = Math.min(lim * 1.05, Math.max(0.08, dist / 42))
  const cx = Number(target?.x) || 0
  const cy = Number(target?.y) || 0
  return {
    minX: cx - half,
    maxX: cx + half,
    minY: cy - half,
    maxY: cy + half,
  }
}
