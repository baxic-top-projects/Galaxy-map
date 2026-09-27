import { describe, expect, test } from 'vitest'
import { filterSearch } from './lib/galaxy/search.js'
import { estimateZoom, pickLabels } from './lib/galaxy/labelLod.js'
import { buildSpatialIndex } from './lib/galaxy/spatialIndex.js'
import { resolveStarTypeKey, starColor, starModelPath } from './lib/galaxy/modelCatalog.js'

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
    expect(starModelPath('class_g')).toBe('/models/stars/star_type_class_g.glb')
    expect(starColor('class_g')).toBe(0xffe08a)
  })
})
