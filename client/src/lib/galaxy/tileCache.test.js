import { afterEach, describe, expect, test } from 'vitest'
import {
  __resetTileCacheMemoryForTests,
  catalogRevisionFromMap,
  clearTileCache,
  getCachedPoliticalPlate,
  getCachedTile,
  listCachedTiles,
  loadGalaxyWarmCache,
  setCachedEdges,
  setCachedMap,
  setCachedPoliticalPlate,
  setCachedSearch,
  setCachedSystemsSnapshot,
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

  test('systems snapshot marks warm hydrated without all tiles', async () => {
    const revision = 'rev-snap'
    await setCachedMap(revision, {
      meta: {},
      polities: [],
      systems: [{ id: 'seed' }],
      tileGrid: { size: 4, mapLim: 1.06 },
    })
    await setCachedSystemsSnapshot(revision, [
      { id: 'seed' },
      { id: 'a' },
      { id: 'b' },
    ])
    const warm = await loadGalaxyWarmCache()
    expect(warm.systemsHydrated).toBe(true)
    expect(warm.systems.map((system) => system.id).sort()).toEqual(['a', 'b', 'seed'])
    expect(warm.hasPoliticalPlate).toBe(false)
  })

  test('political plate blob round-trips in warm cache', async () => {
    const revision = 'rev-plate'
    await setCachedMap(revision, {
      meta: {},
      polities: [],
      systems: [],
      tileGrid: { size: 1, mapLim: 1.06 },
    })
    const blob = new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'image/png' })
    await setCachedPoliticalPlate(revision, {
      blob,
      labelAnchors: { A: { x: 1, y: 2 } },
      territoryAreas: { A: 10 },
      labelMetrics: { A: { w: 1 } },
      rasterSize: 64,
      mapLim: 1.06,
    })
    const cached = await getCachedPoliticalPlate(revision)
    expect(cached.blob).toBeTruthy()
    expect(cached.labelAnchors.A.x).toBe(1)
    const warm = await loadGalaxyWarmCache()
    expect(warm.hasPoliticalPlate).toBe(true)
  })
})
