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
})
