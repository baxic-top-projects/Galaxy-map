import visualOwnership from './visualOwnership.json'

/**
 * @typedef {{ id: string, token: string, stem: string|null, kind: string, nameEn: string, nameRu: string, starTypeKey: string, sectorId: string, capital: boolean, x: number, y: number, z: number, worldCount: number, shard: string }} GalaxySystem
 * @typedef {{ stem: string, nameEn: string, nameRu: string, bloc: string, kind: string, color: string, label: string }} Polity
 * @typedef {{ a: string, b: string }} Edge
 * @typedef {{ id: string, kind: string, token: string, nameEn: string, nameRu: string, stem: string|null, planetTypeKey?: string }} SearchEntry
 */

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || ''

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
export async function loadGalaxy(baseUrl = DEFAULT_API_BASE) {
  const url = `${String(baseUrl).replace(/\/$/, '')}/api/v1/galaxy`
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Failed to load galaxy index: ${response.status}`)
  }
  const data = await response.json()
  const systems = data.systems.map((system) => {
    const visualStem = visualOwnership[system.id]
    if (!visualStem || visualStem === system.stem) return system
    return { ...system, canonicalStem: system.stem, stem: visualStem }
  })
  const search = data.search.map((entry) => {
    const visualStem = visualOwnership[entry.id]
    return visualStem && visualStem !== entry.stem
      ? { ...entry, canonicalStem: entry.stem, stem: visualStem }
      : entry
  })
  const byId = new Map(systems.map((system) => [system.id, system]))
  const polityByStem = new Map(data.polities.map((polity) => [polity.stem, polity]))
  return {
    ...data,
    systems,
    search,
    byId,
    polityByStem,
  }
}

/**
 * @param {string | { id?: string, shard?: string }} systemOrId
 * @param {string} [baseUrl]
 */
export async function loadSystemDetail(systemOrId, baseUrl = DEFAULT_API_BASE) {
  const key =
    typeof systemOrId === 'string'
      ? systemOrId
      : systemOrId?.id || systemOrId?.shard || ''
  if (!key) throw new Error('System id is required')
  const url = `${String(baseUrl).replace(/\/$/, '')}/api/v1/systems/${encodeURIComponent(key)}`
  const response = await fetch(url)
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
