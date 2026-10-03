/**
 * @typedef {{ id: string, token: string, stem: string|null, kind: string, nameEn: string, nameRu: string, starTypeKey: string, sectorId: string, capital: boolean, x: number, y: number, z: number, worldCount: number, shard: string }} GalaxySystem
 * @typedef {{ stem: string, nameEn: string, nameRu: string, bloc: string, kind: string, color: string, label: string }} Polity
 * @typedef {{ a: string, b: string }} Edge
 * @typedef {{ id: string, kind: string, token: string, nameEn: string, nameRu: string, stem: string|null, planetTypeKey?: string }} SearchEntry
 */

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || ''
let activeWorldNames = new Map()
const WORLD_PREFIXES = [
  ['Ael', 'Аэль'], ['Ar', 'Ар'], ['Bel', 'Бел'], ['Cael', 'Каэль'],
  ['Dra', 'Дра'], ['Eri', 'Эри'], ['Fen', 'Фен'], ['Gal', 'Гал'],
  ['Iri', 'Ири'], ['Ka', 'Ка'], ['Lor', 'Лор'], ['Mer', 'Мер'],
  ['Nai', 'Наи'], ['Or', 'Ор'], ['Phae', 'Фэй'], ['Qua', 'Ква'],
  ['Rhy', 'Ри'], ['Sel', 'Сел'], ['Tal', 'Тал'], ['Vey', 'Вей'],
]
const WORLD_MIDDLES = [
  ['dor', 'дор'], ['lan', 'лан'], ['mir', 'мир'], ['nor', 'нор'],
  ['ras', 'рас'], ['the', 'те'], ['val', 'вал'], ['xen', 'ксен'],
  ['yor', 'йор'], ['zen', 'зен'], ['cal', 'кал'], ['fir', 'фир'],
  ['gol', 'гол'], ['hel', 'хел'], ['jor', 'жор'], ['kel', 'кел'],
  ['lum', 'лум'], ['mor', 'мор'], ['ryl', 'рил'], ['syl', 'сил'],
]
const WORLD_SUFFIXES = [
  ['a', 'а'], ['ae', 'ай'], ['an', 'ан'], ['ara', 'ара'],
  ['ea', 'ея'], ['el', 'эль'], ['en', 'ен'], ['ia', 'ия'],
  ['ion', 'ион'], ['is', 'ис'], ['on', 'он'], ['ora', 'ора'],
  ['os', 'ос'], ['um', 'ум'], ['une', 'ун'], ['yx', 'икс'],
  ['aris', 'арис'], ['eron', 'ерон'], ['iel', 'иэль'], ['oris', 'орис'],
]

function worldKey(systemId, token) {
  return `${systemId}\u0000${token || ''}`
}

function hash32(value) {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

function mintWorldName(key, usedEn, usedRu) {
  for (let attempt = 0; attempt < 128; attempt += 1) {
    let hash = hash32(`${key}:${attempt}`)
    const prefix = WORLD_PREFIXES[hash % WORLD_PREFIXES.length]
    hash = Math.floor(hash / WORLD_PREFIXES.length)
    const middle = WORLD_MIDDLES[hash % WORLD_MIDDLES.length]
    hash = Math.floor(hash / WORLD_MIDDLES.length)
    const suffix = WORLD_SUFFIXES[hash % WORLD_SUFFIXES.length]
    const nameEn = `${prefix[0]}${middle[0]}${suffix[0]}`
    const nameRu = `${prefix[1]}${middle[1]}${suffix[1]}`
    if (
      !usedEn.has(nameEn.toLocaleLowerCase()) &&
      !usedRu.has(nameRu.toLocaleLowerCase())
    ) {
      return { nameEn, nameRu }
    }
  }
  throw new Error(`Unable to generate a unique world name for ${key}`)
}

function uniquifyWorldSearch(search) {
  const usedEn = new Set()
  const usedRu = new Set()
  const namesByKey = new Map()
  const updated = search.map((entry) => {
    if (entry.kind !== 'world') return entry
    const baseEn = entry.nameEn || entry.token || 'World'
    const baseRu = entry.nameRu || entry.token || 'Мир'
    let nameEn = baseEn
    let nameRu = baseRu
    if (usedEn.has(nameEn.toLocaleLowerCase()) || usedRu.has(nameRu.toLocaleLowerCase())) {
      const minted = mintWorldName(worldKey(entry.id, entry.token), usedEn, usedRu)
      nameEn = minted.nameEn
      nameRu = minted.nameRu
    }
    usedEn.add(nameEn.toLocaleLowerCase())
    usedRu.add(nameRu.toLocaleLowerCase())
    namesByKey.set(worldKey(entry.id, entry.token), { nameEn, nameRu })
    return nameEn === entry.nameEn && nameRu === entry.nameRu
      ? entry
      : { ...entry, nameEn, nameRu }
  })
  activeWorldNames = namesByKey
  return updated
}

async function fetchGalaxyJson(path, baseUrl = DEFAULT_API_BASE, { timeoutMs = 20000 } = {}) {
  const url = `${String(baseUrl).replace(/\/$/, '')}${path}`
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  let response
  try {
    response = await fetch(url, { signal: controller.signal })
  } finally {
    clearTimeout(timeout)
  }
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`)
  }
  return response.json()
}

function assembleGalaxy(data) {
  const systems = data.systems || []
  const byId = new Map(systems.map((system) => [system.id, system]))
  const search = uniquifyWorldSearch(data.search || [])
  const polityByStem = new Map((data.polities || []).map((polity) => [polity.stem, polity]))
  return {
    ...data,
    systems,
    tileGrid: data.tileGrid || null,
    edgesCanon: data.edgesCanon || [],
    edgesDisplay: data.edgesDisplay || [],
    search,
    byId,
    polityByStem,
  }
}

/**
 * Map bootstrap: meta + polities + seed systems + tileGrid (no edges/search yet).
 * @returns {Promise<{
 *   meta: object,
 *   polities: Polity[],
 *   systems: GalaxySystem[],
 *   tileGrid: { size: number, mapLim: number } | null,
 *   edgesCanon: Edge[],
 *   edgesDisplay: Edge[],
 *   search: SearchEntry[],
 *   byId: Map<string, GalaxySystem>,
 *   polityByStem: Map<string, Polity>
 * }>}
 */
export async function loadGalaxyMap(baseUrl = DEFAULT_API_BASE, options = {}) {
  const data = await fetchGalaxyJson('/api/v1/galaxy/map', baseUrl, options)
  return assembleGalaxy({
    ...data,
    edgesCanon: [],
    edgesDisplay: [],
    search: [],
  })
}

/** @returns {Promise<{ tx: number, ty: number, systems: GalaxySystem[] }>} */
export async function loadGalaxySystemsTile(tx, ty, baseUrl = DEFAULT_API_BASE, options = {}) {
  const query = new URLSearchParams({
    tx: String(tx),
    ty: String(ty),
  })
  const data = await fetchGalaxyJson(`/api/v1/galaxy/systems?${query}`, baseUrl, options)
  return {
    tx: Number(data.tx ?? tx),
    ty: Number(data.ty ?? ty),
    systems: data.systems || [],
  }
}

/** Run async workers over items with a fixed concurrency limit. */
export async function mapPool(items, concurrency, worker) {
  const list = Array.isArray(items) ? items : []
  if (!list.length) return []
  const limit = Math.max(1, Math.min(concurrency || 1, list.length))
  const results = new Array(list.length)
  let nextIndex = 0
  async function run() {
    while (nextIndex < list.length) {
      const index = nextIndex
      nextIndex += 1
      results[index] = await worker(list[index], index)
    }
  }
  await Promise.all(Array.from({ length: limit }, () => run()))
  return results
}

/** @returns {Promise<{ edgesCanon: Edge[], edgesDisplay: Edge[] }>} */
export async function loadGalaxyEdges(baseUrl = DEFAULT_API_BASE, options = {}) {
  const data = await fetchGalaxyJson('/api/v1/galaxy/edges', baseUrl, options)
  return {
    edgesCanon: data.edgesCanon || [],
    edgesDisplay: data.edgesDisplay || [],
  }
}

/** @returns {Promise<SearchEntry[]>} */
export async function loadGalaxySearch(baseUrl = DEFAULT_API_BASE, options = {}) {
  const data = await fetchGalaxyJson('/api/v1/galaxy/search', baseUrl, options)
  return uniquifyWorldSearch(data.search || [])
}

/**
 * Full catalog in one request (compat / tests). Prefer loadGalaxyMap + slices.
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
export async function loadGalaxy(baseUrl = DEFAULT_API_BASE, options = {}) {
  const data = await fetchGalaxyJson('/api/v1/galaxy', baseUrl, options)
  // Ownership (painted + manual) is applied by catalog-service so the client
  // does not override a server-assigned stem with a stale local JSON map.
  return assembleGalaxy(data)
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
  const detail = await response.json()
  const worlds = (detail.worlds || []).map((world) => {
    const names = activeWorldNames.get(worldKey(detail.id || key, world.token))
    return names ? { ...world, ...names } : world
  })
  return {
    ...detail,
    worlds,
  }
}

export function systemLabel(system, locale = 'ru') {
  const label = locale === 'en' ? system.nameEn : system.nameRu
  if (label?.trim()) return label
  if (system.kind === 'black_hole') {
    return locale === 'en' ? 'Unnamed black hole' : 'Безымянная чёрная дыра'
  }
  if (system.kind === 'junction') {
    return locale === 'en' ? 'Hypercorridor junction' : 'Стык гиперкоридоров'
  }
  return locale === 'en' ? 'Unnamed star' : 'Безымянная звезда'
}

export function polityLabel(polity, locale = 'ru') {
  if (!polity) return ''
  return locale === 'en' ? polity.nameEn : polity.nameRu
}
