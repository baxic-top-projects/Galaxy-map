import { describe, expect, test } from 'vitest'
import {
  centroidsFromOwnerRaster,
  centroidsFromSystems,
  resolvePolityLabelAnchors,
} from './polityTerritoryAnchors.js'

describe('polityTerritoryAnchors', () => {
  test('centroidsFromOwnerRaster prefers interior of largest region', () => {
    const size = 5
    const owner = new Int32Array(size * size).fill(-1)
    // Left blob 3x3 for polity A (largest)
    for (let y = 0; y < 3; y += 1) {
      for (let x = 0; x < 3; x += 1) owner[y * size + x] = 0
    }
    // Tiny detached pixel for A on the far right — must not pull the label
    owner[0 * size + 4] = 0
    // Polity B owns a vertical strip on the right-middle that would sit under a naive mean
    for (let y = 0; y < 5; y += 1) owner[y * size + 3] = 1

    const meta = [{ polityStem: 'A' }, { polityStem: 'B' }]
    const anchors = centroidsFromOwnerRaster(owner, meta, size)
    // Interior of the 3x3 is (1,1), not the border and not between blobs.
    expect(anchors.A[0]).toBeCloseTo(1 / 4, 6)
    expect(anchors.A[1]).toBeCloseTo(1 / 4, 6)
    // B strip center-ish around x=3
    expect(anchors.B[0]).toBeCloseTo(3 / 4, 6)
  })

  test('centroidsFromSystems ignore junctions and invert y into UV', () => {
    const anchors = centroidsFromSystems(
      {
        systems: [
          { stem: 'P', kind: 'star', x: 0, y: 0 },
          { stem: 'P', kind: 'junction', x: 1, y: 1 },
          { stem: 'P', kind: 'black_hole', x: 1.06, y: -1.06 },
        ],
      },
      1.06,
    )
    expect(anchors.P[0]).toBeCloseTo(0.75, 5)
    expect(anchors.P[1]).toBeCloseTo(0.75, 5)
  })

  test('resolvePolityLabelAnchors prefers painted over systems over seed', () => {
    const resolved = resolvePolityLabelAnchors(
      { A: [0.1, 0.1] },
      { A: [0.2, 0.2], B: [0.3, 0.3] },
      { A: [0.4, 0.4], B: [0.5, 0.5], C: [0.6, 0.6] },
      [{ stem: 'A' }, { stem: 'B' }, { stem: 'C' }],
    )
    expect(resolved.A).toEqual([0.1, 0.1])
    expect(resolved.B).toEqual([0.3, 0.3])
    expect(resolved.C).toEqual([0.6, 0.6])
  })
})
