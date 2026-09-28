import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, test } from 'vitest'

const root = dirname(fileURLToPath(import.meta.url))
const indexPath = join(root, '../../../public/data/galaxy-index.json')

describe('galaxy-index contract', () => {
  const data = JSON.parse(readFileSync(indexPath, 'utf8'))

  test('contains expected top-level collections', () => {
    expect(data.meta.source).toBe('EfolsMiradinsPact')
    expect(data.polities.length).toBeGreaterThan(40)
    expect(data.systems.length).toBeGreaterThan(3000)
    expect(data.edgesDisplay.length).toBeGreaterThan(4000)
    expect(data.search.length).toBeGreaterThan(data.systems.length)
  })

  test('systems expose coordinates and shards', () => {
    const sample = data.systems.find((system) => system.token === 'MiradinSirius')
    expect(sample).toBeTruthy()
    expect(typeof sample.x).toBe('number')
    expect(typeof sample.y).toBe('number')
    expect(typeof sample.z).toBe('number')
    expect(sample.shard).toContain('systems/')
    expect(sample.capital).toBe(true)
  })

  test('exports all empty hypercorridor junctions as connected systems', () => {
    const junctions = data.systems.filter((system) => system.kind === 'junction')
    const connected = new Set(
      data.edgesDisplay.flatMap((edge) => [edge.a, edge.b]),
    )

    expect(junctions).toHaveLength(400)
    expect(junctions.every((system) => system.worldCount === 0)).toBe(true)
    expect(junctions.every((system) => system.starTypeKey === 'junction')).toBe(true)
    expect(junctions.every((system) => connected.has(system.id))).toBe(true)
    expect(data.search.some((entry) => junctions.some((system) => system.id === entry.id))).toBe(false)
  })

  test('preserves named moons from the canonical planet registry', () => {
    const mira = JSON.parse(
      readFileSync(join(root, '../../../public/data/systems/Miradin_Empire__MiradinSirius.json'), 'utf8'),
    )
    const world = mira.worlds.find((entry) => entry.token === 'Mira')

    expect(world.satellites.map((moon) => moon.nameEn)).toEqual([
      'Old Frend',
      'Ekkel',
      'Shrjne',
    ])
    expect(world.satellites.every((moon) => moon.planetTypeKey === 'moon')).toBe(true)
  })
})
