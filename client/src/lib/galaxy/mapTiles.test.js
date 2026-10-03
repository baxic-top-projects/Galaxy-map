import { describe, expect, test } from 'vitest'
import {
  allTiles,
  allTilesCenterOut,
  boundsFromCameraView,
  expandTiles,
  tileKey,
  tilesForBounds,
} from './mapTiles.js'

describe('mapTiles', () => {
  test('tilesForBounds covers center cell', () => {
    const tiles = tilesForBounds(-0.01, 0.01, -0.01, 0.01, 1.06, 16)
    expect(tiles.some((tile) => tile.tx === 7 && tile.ty === 7)).toBe(true)
  })

  test('expandTiles adds neighbor ring', () => {
    const expanded = expandTiles([{ tx: 0, ty: 0 }], 1, 16)
    expect(expanded).toEqual(
      expect.arrayContaining([
        { tx: 0, ty: 0 },
        { tx: 1, ty: 0 },
        { tx: 0, ty: 1 },
        { tx: 1, ty: 1 },
      ]),
    )
    expect(expanded.every((tile) => tile.tx >= 0 && tile.ty >= 0)).toBe(true)
  })

  test('allTiles fills the grid', () => {
    expect(allTiles(4)).toHaveLength(16)
    expect(tileKey(2, 3)).toBe('2:3')
  })

  test('allTilesCenterOut starts near the core', () => {
    const ordered = allTilesCenterOut(4)
    expect(ordered).toHaveLength(16)
    expect(ordered[0]).toEqual({ tx: 1, ty: 1 })
    expect(ordered[ordered.length - 1]).toEqual(
      expect.objectContaining({
        tx: expect.any(Number),
        ty: expect.any(Number),
      }),
    )
    const firstDist =
      (ordered[0].tx - 1.5) ** 2 + (ordered[0].ty - 1.5) ** 2
    const lastDist =
      (ordered[ordered.length - 1].tx - 1.5) ** 2 +
      (ordered[ordered.length - 1].ty - 1.5) ** 2
    expect(firstDist).toBeLessThanOrEqual(lastDist)
  })

  test('boundsFromCameraView grows with distance', () => {
    const near = boundsFromCameraView({ x: 0, y: 0 }, 8, 1.06)
    const far = boundsFromCameraView({ x: 0, y: 0 }, 80, 1.06)
    expect(far.maxX - far.minX).toBeGreaterThan(near.maxX - near.minX)
  })
})
