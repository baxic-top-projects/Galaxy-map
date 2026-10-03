import { afterEach, describe, expect, test, vi } from 'vitest'
import {
  loadGalaxy,
  loadGalaxyEdges,
  loadGalaxyMap,
  loadGalaxySearch,
  loadGalaxySystemsTile,
  loadSystemDetail,
  mapPool,
  polityLabel,
  systemLabel,
} from './loadGalaxy.js'

describe('loadGalaxy API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('loads galaxy index from /api/v1/galaxy', async () => {
    const payload = {
      meta: { source: 'EfolsMiradinsPact' },
      polities: [{ stem: 'Miradin_Empire', nameEn: 'Miradin Empire', nameRu: 'Империя Мирадин' }],
      systems: [
        {
          id: 'Miradin_Empire:MiradinSirius',
          token: 'MiradinSirius',
          stem: 'Miradin_Empire',
          kind: 'star',
          nameEn: 'Miradin Sirius',
          nameRu: 'Мирадин Сириус',
          starTypeKey: 'class_g',
          sectorId: 's1',
          capital: true,
          x: 1,
          y: 2,
          z: 3,
          worldCount: 4,
          shard: 'systems/Miradin_Empire__MiradinSirius.json',
        },
      ],
      edgesCanon: [{ a: 'A', b: 'B' }],
      edgesDisplay: [{ a: 'A', b: 'B' }],
      search: [],
    }

    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(String(url)).toMatch(/\/api\/v1\/galaxy$/)
        return {
          ok: true,
          json: async () => payload,
        }
      }),
    )

    const galaxy = await loadGalaxy('http://gateway.test')
    expect(galaxy.meta.source).toBe('EfolsMiradinsPact')
    expect(galaxy.byId.get('Miradin_Empire:MiradinSirius').token).toBe('MiradinSirius')
    expect(galaxy.polityByStem.get('Miradin_Empire').nameEn).toBe('Miradin Empire')
  })

  test('loads system detail by id from /api/v1/systems', async () => {
    const detail = {
      id: 'Miradin_Empire:MiradinSirius',
      token: 'MiradinSirius',
      worlds: [{ token: 'Mira', satellites: [{ nameEn: 'Old Frend' }] }],
    }

    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(String(url)).toContain('/api/v1/systems/')
        expect(String(url)).toContain(encodeURIComponent('Miradin_Empire:MiradinSirius'))
        return {
          ok: true,
          json: async () => detail,
        }
      }),
    )

    const system = await loadSystemDetail(
      { id: 'Miradin_Empire:MiradinSirius' },
      'http://gateway.test',
    )
    expect(system.worlds[0].token).toBe('Mira')
  })

  test('keeps server-provided ownership stems without client remapping', async () => {
    const payload = {
      meta: {},
      polities: [
        { stem: 'Varis_Republic', nameEn: 'Varis Republic' },
        { stem: 'Remar_Federation', nameEn: 'Remar Federation' },
      ],
      systems: [
        {
          id: 'Varis_Republic:Thalyx',
          stem: 'Remar_Federation',
          canonicalStem: 'Varis_Republic',
          token: 'Thalyx',
        },
      ],
      edgesCanon: [],
      edgesDisplay: [],
      search: [
        {
          id: 'Varis_Republic:Thalyx',
          stem: 'Remar_Federation',
          kind: 'system',
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => payload,
      })),
    )

    const galaxy = await loadGalaxy('http://gateway.test')
    const system = galaxy.byId.get('Varis_Republic:Thalyx')
    expect(system.stem).toBe('Remar_Federation')
    expect(system.canonicalStem).toBe('Varis_Republic')
    expect(galaxy.search[0].stem).toBe('Remar_Federation')
  })

  test('qualifies repeated world names with their unique system', async () => {
    const payload = {
      meta: {},
      polities: [],
      systems: [
        { id: 'A:One', stem: 'A', token: 'One', nameEn: 'Alpha', nameRu: 'Альфа' },
        { id: 'B:Two', stem: 'B', token: 'Two', nameEn: 'Beta', nameRu: 'Бета' },
      ],
      edgesCanon: [],
      edgesDisplay: [],
      search: [
        { id: 'A:One', kind: 'world', token: 'Twin', nameEn: 'Twin', nameRu: 'Двойник' },
        { id: 'B:Two', kind: 'world', token: 'Twin', nameEn: 'Twin', nameRu: 'Двойник' },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => payload,
      })),
    )

    const galaxy = await loadGalaxy('http://gateway.test')
    expect(galaxy.search[0].nameRu).toBe('Двойник')
    expect(galaxy.search[1].nameRu).not.toBe('Двойник')
    expect(galaxy.search[1].nameRu).not.toContain('(')
    expect(new Set(galaxy.search.map((entry) => entry.nameRu)).size).toBe(2)
  })

  test('labels prefer locale', () => {
    const system = { nameEn: 'Alpha', nameRu: 'Альфа' }
    const polity = { nameEn: 'Empire', nameRu: 'Империя' }
    expect(systemLabel(system, 'ru')).toBe('Альфа')
    expect(systemLabel(system, 'en')).toBe('Alpha')
    expect(polityLabel(polity, 'ru')).toBe('Империя')
  })

  test('loads map bootstrap without edges or search', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        expect(String(url)).toMatch(/\/api\/v1\/galaxy\/map$/)
        return {
          ok: true,
          json: async () => ({
            meta: { systemCount: 2 },
            polities: [{ stem: 'A', nameEn: 'A', nameRu: 'А' }],
            systems: [{ id: 'A:One', stem: 'A', token: 'One', capital: true, x: 0, y: 0, z: 0 }],
            tileGrid: { size: 16, mapLim: 1.06 },
          }),
        }
      }),
    )

    const galaxy = await loadGalaxyMap('http://gateway.test')
    expect(galaxy.systems).toHaveLength(1)
    expect(galaxy.tileGrid).toEqual({ size: 16, mapLim: 1.06 })
    expect(galaxy.edgesDisplay).toEqual([])
    expect(galaxy.search).toEqual([])
    expect(galaxy.byId.get('A:One').token).toBe('One')
  })

  test('loads spatial system tiles and mapPool concurrency', async () => {
    const seen = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        const href = String(url)
        if (href.includes('/api/v1/galaxy/systems?')) {
          const params = new URL(href).searchParams
          const tx = Number(params.get('tx'))
          const ty = Number(params.get('ty'))
          seen.push(`${tx}:${ty}`)
          return {
            ok: true,
            json: async () => ({
              tx,
              ty,
              systems: [{ id: `T${tx}_${ty}`, token: 'Star', x: 0, y: 0, z: 0 }],
            }),
          }
        }
        throw new Error(`unexpected url ${href}`)
      }),
    )

    const tile = await loadGalaxySystemsTile(3, 7, 'http://gateway.test')
    expect(tile.tx).toBe(3)
    expect(tile.ty).toBe(7)
    expect(tile.systems[0].id).toBe('T3_7')

    const coords = [
      { tx: 0, ty: 0 },
      { tx: 1, ty: 0 },
      { tx: 2, ty: 0 },
      { tx: 3, ty: 0 },
    ]
    const results = await mapPool(coords, 2, async ({ tx, ty }) =>
      loadGalaxySystemsTile(tx, ty, 'http://gateway.test'),
    )
    expect(results).toHaveLength(4)
    expect(seen).toContain('3:7')
    expect(seen).toContain('3:0')
  })

  test('loads edges and search slices', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url) => {
        const href = String(url)
        if (href.endsWith('/api/v1/galaxy/edges')) {
          return {
            ok: true,
            json: async () => ({
              edgesCanon: [{ a: 'A:One', b: 'A:Two' }],
              edgesDisplay: [{ a: 'A:One', b: 'A:Two' }],
            }),
          }
        }
        if (href.endsWith('/api/v1/galaxy/search')) {
          return {
            ok: true,
            json: async () => ({
              search: [{ id: 'A:One', kind: 'system', token: 'One', nameEn: 'One', nameRu: 'Один' }],
            }),
          }
        }
        throw new Error(`unexpected url ${href}`)
      }),
    )

    const edges = await loadGalaxyEdges('http://gateway.test')
    const search = await loadGalaxySearch('http://gateway.test')
    expect(edges.edgesDisplay).toHaveLength(1)
    expect(search[0].token).toBe('One')
  })
})
