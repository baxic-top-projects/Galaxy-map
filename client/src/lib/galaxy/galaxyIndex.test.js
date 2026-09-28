import { afterEach, describe, expect, test, vi } from 'vitest'
import { loadGalaxy, loadSystemDetail, polityLabel, systemLabel } from './loadGalaxy.js'

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

  test('uses painted territory ownership for mismatched systems', async () => {
    const payload = {
      meta: {},
      polities: [
        { stem: 'Varis_Republic', nameEn: 'Varis Republic' },
        { stem: 'Tessar_Syndicate', nameEn: 'Tessar Syndicate' },
      ],
      systems: [
        {
          id: 'Varis_Republic:Thalyx',
          stem: 'Varis_Republic',
          token: 'Thalyx',
        },
      ],
      edgesCanon: [],
      edgesDisplay: [],
      search: [
        {
          id: 'Varis_Republic:Thalyx',
          stem: 'Varis_Republic',
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
    expect(system.stem).toBe('Tessar_Syndicate')
    expect(system.canonicalStem).toBe('Varis_Republic')
    expect(galaxy.search[0].stem).toBe('Tessar_Syndicate')
  })

  test('labels prefer locale', () => {
    const system = { nameEn: 'Alpha', nameRu: 'Альфа' }
    const polity = { nameEn: 'Empire', nameRu: 'Империя' }
    expect(systemLabel(system, 'ru')).toBe('Альфа')
    expect(systemLabel(system, 'en')).toBe('Alpha')
    expect(polityLabel(polity, 'ru')).toBe('Империя')
  })
})
