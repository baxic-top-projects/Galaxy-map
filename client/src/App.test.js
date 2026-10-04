import { describe, expect, test } from 'vitest'
import { filterSearch } from './lib/galaxy/search.js'
import { estimateZoom, pickLabels } from './lib/galaxy/labelLod.js'
import { buildSpatialIndex } from './lib/galaxy/spatialIndex.js'
import { resolveStarTypeKey, starColor } from './lib/galaxy/modelCatalog.js'

describe('search', () => {
  const entries = [
    { id: 'A:Mira', kind: 'world', token: 'Mira', nameEn: 'Mira', nameRu: 'Мира', stem: 'Miradin_Empire' },
    { id: 'A:MiradinSirius', kind: 'system', token: 'MiradinSirius', nameEn: 'Miradin Sirius', nameRu: 'Мирадинский Сириус', stem: 'Miradin_Empire' },
    { id: 'B:Efol', kind: 'system', token: 'Efol', nameEn: 'Efol', nameRu: 'Эфол', stem: 'Efol_Raih' },
  ]

  test('finds russian and english names', () => {
    expect(filterSearch(entries, 'мир', { locale: 'ru' })[0].token).toBe('Mira')
    expect(filterSearch(entries, 'efol', { locale: 'en' })[0].token).toBe('Efol')
  })

  test('respects polity filter', () => {
    expect(filterSearch(entries, 'm', { stem: 'Efol_Raih' })).toHaveLength(0)
    expect(filterSearch(entries, 'ef', { stem: 'Efol_Raih' })).toHaveLength(1)
  })

  test('finds by compact English token and spaced nameEn', () => {
    const rows = [
      {
        id: 'O:CorvuthAltair',
        kind: 'system',
        token: 'CorvuthAltair',
        nameEn: 'Corvuth Altair',
        nameRu: 'Корвут Альтаир',
        stem: 'Ossirian_Mandate',
      },
    ]
    expect(filterSearch(rows, 'corvuthaltair', { locale: 'ru' })[0].token).toBe('CorvuthAltair')
    expect(filterSearch(rows, 'корвут', { locale: 'ru' })[0].nameRu).toBe('Корвут Альтаир')
    expect(filterSearch(rows, 'altair', { locale: 'en' })[0].nameEn).toBe('Corvuth Altair')
  })
})

describe('label LOD', () => {
  const systems = [
    { id: '1', token: 'A', capital: true, kind: 'star', worldCount: 3, x: 0, y: 0, z: 0 },
    { id: '2', token: 'B', capital: false, kind: 'star', worldCount: 5, x: 0.1, y: 0, z: 0 },
    { id: '3', token: 'C', capital: false, kind: 'star', worldCount: 1, x: 0.2, y: 0, z: 0 },
  ]

  test('keeps selected and capitals first', () => {
    const labels = pickLabels(systems, { zoom: 2, selectedId: '3', maxLabels: 2 })
    expect(labels.map((item) => item.system.id)).toEqual(['3', '1'])
  })

  test('estimates zoom from camera distance', () => {
    expect(estimateZoom(8)).toBe(1)
    expect(estimateZoom(2)).toBe(4)
  })

  test('does not label unnamed frontier objects', () => {
    const labels = pickLabels(
      [
        ...systems,
        { id: 'frontier:arm-1:star-001', token: '', nameEn: '', nameRu: '', kind: 'star', x: 1, y: 0, z: 0 },
      ],
      { zoom: 8, selectedId: 'frontier:arm-1:star-001', maxLabels: 10 },
    )
    expect(labels.some((item) => item.system.id.startsWith('frontier:'))).toBe(false)
  })

  test('labels named hypercorridor junctions when zoomed in', () => {
    const labels = pickLabels(
      [
        ...systems,
        {
          id: 'G:Forkoth',
          token: 'Forkoth',
          nameEn: 'Forkoth',
          nameRu: 'Форкот',
          kind: 'junction',
          x: 0.3,
          y: 0,
          z: 0,
        },
      ],
      { zoom: 8, selectedId: 'G:Forkoth', maxLabels: 10 },
    )
    expect(labels.some((item) => item.system.id === 'G:Forkoth')).toBe(true)
  })
})

describe('junction labels', () => {
  test('RU locale uses Cyrillic canon name, not English token', async () => {
    const { applyJunctionCanonNames, systemLabel } = await import(
      './lib/galaxy/loadGalaxy.js'
    )
    const system = {
      id: 'Miradin_Empire:Weaveith',
      token: 'Weaveith',
      kind: 'junction',
      nameEn: 'Weaveith Junction',
      nameRu: 'Стык Weaveith',
      stem: 'Miradin_Empire',
    }
    const [patched] = applyJunctionCanonNames([system])
    expect(patched.nameRu).toBe('Вивит')
    expect(patched.nameRu.includes('Стык')).toBe(false)
    expect(/[A-Za-z]/.test(patched.nameRu)).toBe(false)
    expect(patched.nameEn).toBe('Weaveith')
    expect(systemLabel(patched, 'ru')).toBe('Вивит')
    expect(systemLabel(system, 'ru')).toBe('Вивит')
    expect(systemLabel(system, 'en')).toBe('Weaveith')
  })
})

describe('spatial index', () => {
  test('returns nearest system', () => {
    const index = buildSpatialIndex([
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: 0.2, y: 0.2 },
    ])
    expect(index.queryNearest(0.01, 0.01)?.id).toBe('a')
  })
})

describe('model catalog', () => {
  test('maps star type keys to asset paths', () => {
    expect(resolveStarTypeKey('class_g')).toBe('class_g')
    expect(resolveStarTypeKey('class_g', 'black_hole')).toBe('black_hole')
    expect(resolveStarTypeKey('class_g', 'well')).toBe('supermassive_black_hole')
    expect(starColor('class_g')).toBe(0xffe08a)
  })
})
