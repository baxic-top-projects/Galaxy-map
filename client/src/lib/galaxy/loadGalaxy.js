/**
 * @typedef {{ id: string, token: string, stem: string|null, kind: string, nameEn: string, nameRu: string, starTypeKey: string, sectorId: string, capital: boolean, x: number, y: number, z: number, worldCount: number, shard: string }} GalaxySystem
 * @typedef {{ stem: string, nameEn: string, nameRu: string, bloc: string, kind: string, color: string, label: string }} Polity
 * @typedef {{ a: string, b: string }} Edge
 * @typedef {{ id: string, kind: string, token: string, nameEn: string, nameRu: string, stem: string|null, planetTypeKey?: string }} SearchEntry
 */

/**
 * @returns {Promise<{
 *   meta: object,
 *   polities: Polity[],
 *   systems: GalaxySystem[],
 *   edgesCanon: Edge[],
 *   edgesDisplay: Edge[],
 *   search: SearchEntry[],
 *   byId: Map<string, GalaxySystem>,
 *   polityByStem: Map<string, Polity>
 * }>}
 */
export async function loadGalaxy(url = '/data/galaxy-index.json') {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load galaxy index: ${response.status}`)
  }
  const data = await response.json()
  const byId = new Map(data.systems.map((system) => [system.id, system]))
  const polityByStem = new Map(data.polities.map((polity) => [polity.stem, polity]))
  return {
    ...data,
    byId,
    polityByStem,
  }
}

export async function loadSystemDetail(shardPath) {
  const response = await fetch(`/data/${shardPath}`)
  if (!response.ok) {
    throw new Error(`Failed to load system detail: ${response.status}`)
  }
  return response.json()
}

export function systemLabel(system, locale = 'ru') {
  return locale === 'en' ? system.nameEn : system.nameRu
}

export function polityLabel(polity, locale = 'ru') {
  if (!polity) return ''
  return locale === 'en' ? polity.nameEn : polity.nameRu
}
