import { describe, expect, test } from 'vitest'
import { normalizeStormSnapshot, stormStageLabel, stormTypeLabel, stormWebSocketUrl } from './stormsApi.js'

describe('stormsApi', () => {
  test('normalizes snapshot systems into a lookup map', () => {
    const normalized = normalizeStormSnapshot({
      tick: 4,
      generatedAt: '2026-09-28T00:00:00Z',
      storms: [{ id: 'storm-1' }],
      systems: [
        {
          systemId: 'A:One',
          intensity: 0.7,
          stage: 'active',
          type: 'electric',
          stormId: 'storm-1',
          color: '#6ec8ff',
        },
      ],
    })

    expect(normalized.tick).toBe(4)
    expect(normalized.bySystemId['A:One']).toMatchObject({
      intensity: 0.7,
      stage: 'active',
      type: 'electric',
    })
  })

  test('tolerates empty or invalid payloads', () => {
    const empty = normalizeStormSnapshot(null)
    expect(empty.systems).toEqual([])
    expect(Object.keys(empty.bySystemId)).toEqual([])
  })

  test('labels storm stage and type', () => {
    expect(stormStageLabel('forming', 'ru')).toBe('Зарождение')
    expect(stormTypeLabel('gravity', 'en')).toBe('Gravity storm')
  })

  test('builds websocket url from http api base', () => {
    expect(stormWebSocketUrl('http://localhost:9998')).toBe('ws://localhost:9998/api/v1/storms/ws')
    expect(stormWebSocketUrl('https://galaxy.baxic.ru')).toBe('wss://galaxy.baxic.ru/api/v1/storms/ws')
  })
})
