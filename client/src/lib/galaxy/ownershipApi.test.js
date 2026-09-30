import { afterEach, describe, expect, test, vi } from 'vitest'
import { updateSystemOwner } from './ownershipApi.js'

describe('ownershipApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('patches system owner through /api/v1/systems/{id}/owner', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options) => {
        expect(String(url)).toContain('/api/v1/systems/')
        expect(String(url)).toContain(encodeURIComponent('A:One'))
        expect(String(url)).toMatch(/\/owner$/)
        expect(options.method).toBe('PATCH')
        expect(JSON.parse(options.body)).toEqual({ stem: 'Miradin_Empire' })
        return {
          ok: true,
          json: async () => ({
            id: 'A:One',
            stem: 'Miradin_Empire',
            canonicalStem: 'Cyberlins',
          }),
        }
      }),
    )

    const result = await updateSystemOwner('A:One', 'Miradin_Empire', 'http://gateway.test')
    expect(result.stem).toBe('Miradin_Empire')
    expect(result.canonicalStem).toBe('Cyberlins')
  })

  test('surfaces API error detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({ detail: 'Unknown polity: Nope' }),
      })),
    )

    await expect(updateSystemOwner('A:One', 'Nope', 'http://gateway.test')).rejects.toThrow(
      'Unknown polity: Nope',
    )
  })
})
