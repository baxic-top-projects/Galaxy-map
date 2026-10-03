import { afterEach, describe, expect, test } from 'vitest'
import {
  __resetTileCacheMemoryForTests,
  catalogRevisionFromMap,
  clearTileCache,
  getCachedTile,
  listCachedTiles,
  loadGalaxyWarmCache,
  setCachedEdges,
  setCachedMap,
  setCachedSearch,
  setCachedTile,
} from './tileCache.js'

describe('tileCache', () => {
  afterEach(async () => {
    await clearTileCache()
    __resetTileCacheMemoryForTests()
  })

  test('catalogRevisionFromMap changes with meta', () => {
    const a = catalogRevisionFromMap({
      meta: { systemCount: 10, mapLim: 1.06 },
      tileGrid: { size: 16, mapLim: 1.06 },
      polities: [],
      systems: [{ id: 'a' }],
    })
    const b = catalogRevisionFromMap({
      meta: { systemCount: 11, mapLim: 1.06 },
      tileGrid: { size: 16, mapLim: 1.06 },
      polities: [],
      systems: [{ id: 'a' }],
    })
    expect(a).not.toBe(b)
  })

  test('persists map tiles edges and warms galaxy', async () => {
    const revision = 'rev-1'
    await setCachedMap(revision, {
      meta: { systemCount: 3 },
      polities: [{ stem: 'A' }],
      systems: [{ id: 'seed', kind: 'well', x: 0, y: 0 }],
      tileGrid: { size: 2, mapLim: 1.06 },
    })
    await setCachedTile(revision, 0, 0, [{ id: 't00', x: -1, y: -1 }])
    await setCachedTile(revision, 1, 1, [{ id: 't11', x: 1, y: 1 }])
    await setCachedEdges(revision, {
      edgesCanon: [],
      edgesDisplay: [{ a: 't00', b: 't11' }],
    })
    await setCachedSearch(revision, [{ id: 't00', kind: 'system', token: 'T' }])

    const cached = await getCachedTile(revision, 0, 0)
    expect(cached.systems[0].id).toBe('t00')
    expect(await listCachedTiles(revision)).toHaveLength(2)

    const warm = await loadGalaxyWarmCache()
    expect(warm.revision).toBe(revision)
    expect(warm.systems.map((system) => system.id).sort()).toEqual(['seed', 't00', 't11'])
    expect(warm.edgesDisplay).toHaveLength(1)
    expect(warm.search[0].token).toBe('T')
    expect(warm.systemsHydrated).toBe(false)
  })

  test('systemsHydrated when all tiles present', async () => {
    const revision = 'rev-full'
    await setCachedMap(revision, {
      meta: {},
      polities: [],
      systems: [],
      tileGrid: { size: 2, mapLim: 1.06 },
    })
    await setCachedTile(revision, 0, 0, [])
    await setCachedTile(revision, 0, 1, [])
    await setCachedTile(revision, 1, 0, [])
    await setCachedTile(revision, 1, 1, [])
    const warm = await loadGalaxyWarmCache()
    expect(warm.systemsHydrated).toBe(true)
  })
})
