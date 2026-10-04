/**
 * @typedef {{ id: string, token: string, stem: string|null, kind: string, nameEn: string, nameRu: string, starTypeKey: string, sectorId: string, capital: boolean, x: number, y: number, z: number, worldCount: number, shard: string }} GalaxySystem
 * @typedef {{ stem: string, nameEn: string, nameRu: string, bloc: string, kind: string, color: string, label: string }} Polity
 * @typedef {{ a: string, b: string }} Edge
 * @typedef {{ id: string, kind: string, token: string, nameEn: string, nameRu: string, stem: string|null, planetTypeKey?: string }} SearchEntry
 */

import { DEFAULT_MAP_LIM, tileCoordsForPoint } from './mapTiles.js'
import {
  catalogRevisionFromMap,
  clearTileCache,
  getCachedTile,
  loadGalaxyWarmCache,
  PLATE_BITMAP_OPTIONS,
  setCachedEdges,
  setCachedMap,
  setCachedSearch,
  setCachedSystemsSnapshot,
  setCachedTile,
} from './tileCache.js'
import junctionCanonNames from './junctionCanonNames.json'

const CYRILLIC_RE = /[А-Яа-яЁё]/
const LATIN_RE = /[A-Za-z]/

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

/** True RU label: has Cyrillic and no Latin (forbids "Стык Weaveith"). */
function isPureCyrillicName(value) {
  const text = (value || '').trim()
  return Boolean(text) && CYRILLIC_RE.test(text) && !LATIN_RE.test(text)
}

/**
 * Overlay canon junction names and strip legacy "Стык Weaveith" / "X Junction".
 * RU name must never be Стык + Latin.
 */
export function applyJunctionCanonNames(systems) {
  if (!systems?.length) return systems || []
  return systems.map((system) => {
    if (system?.kind !== 'junction') return system
    const canon = junctionCanonEntry(system)
    let nameEn = (canon?.nameEn || system.nameEn || system.token || '')
      .replace(/\s+Junction$/i, '')
      .trim()
    let nameRu = (canon?.nameRu || system.nameRu || '').trim()
    nameRu = nameRu.replace(/^Стык\s+/i, '').trim()
    if (!isPureCyrillicName(nameRu)) {
      nameRu = isPureCyrillicName(canon?.nameRu) ? canon.nameRu.trim() : ''
    }
    if (nameEn === system.nameEn && nameRu === system.nameRu) return system
    return { ...system, nameEn, nameRu }
  })
}

function assembleGalaxy(data) {
  const systems = applyJunctionCanonNames(data.systems || [])
  const byId = new Map(systems.map((system) => [system.id, system]))
  const search = uniquifyWorldSearch(data.search || [])
  const polityByStem = new Map((data.polities || []).map((polity) => [polity.stem, polity]))
  return {
    ...data,
    systems,
    tileGrid: data.tileGrid || null,
    cacheRevision: data.cacheRevision || null,
    edgesCanon: data.edgesCanon || [],
    edgesDisplay: data.edgesDisplay || [],
    search,
    byId,
    polityByStem,
  }
}

/**
 * Instant paint from IndexedDB (seed + previously fetched tiles).
 * Returns null when the local cache is empty.
 */
export async function loadGalaxyFromCache() {
  const warm = await loadGalaxyWarmCache()
  if (!warm) return null
  const galaxy = assembleGalaxy({
    ...warm.map,
    systems: warm.systems,
    edgesCanon: warm.edgesCanon,
    edgesDisplay: warm.edgesDisplay,
    search: warm.search,
    cacheRevision: warm.revision,
    meta: {
      ...(warm.map.meta || {}),
      systemsHydrated: warm.systemsHydrated,
      hasPoliticalPlate: warm.hasPoliticalPlate,
    },
  })
  // Prefetch the plate blob + decode while auth/scene boot so borders paint ASAP.
  if (warm.politicalPlate?.blob) {
    galaxy._cachedPoliticalPlate = warm.politicalPlate
    if (typeof createImageBitmap === 'function') {
      galaxy._plateBitmapPromise = createImageBitmap(
        warm.politicalPlate.blob,
        PLATE_BITMAP_OPTIONS,
      ).catch(() => null)
    }
  }
  return {
    galaxy,
    revision: warm.revision,
    tileKeys: warm.tileKeys,
    systemsHydrated: warm.systemsHydrated,
    hasPoliticalPlate: warm.hasPoliticalPlate,
  }
}

/**
 * Map bootstrap: meta + polities + seed systems + tileGrid (no edges/search yet).
 * Revalidates against the network and refreshes the persistent cache revision.
 */
export async function loadGalaxyMap(baseUrl = DEFAULT_API_BASE, options = {}) {
  const data = await fetchGalaxyJson('/api/v1/galaxy/map', baseUrl, options)
  const revision = catalogRevisionFromMap(data)
  const previous = options.previousRevision || null
  if (previous && previous !== revision) {
    await clearTileCache()
  }
  await setCachedMap(revision, {
    meta: data.meta || {},
    polities: data.polities || [],
    systems: data.systems || [],
    tileGrid: data.tileGrid || null,
  })
  return assembleGalaxy({
    ...data,
    edgesCanon: [],
    edgesDisplay: [],
    search: [],
    cacheRevision: revision,
  })
}

/** @returns {Promise<{ tx: number, ty: number, systems: GalaxySystem[] }>} */
export async function loadGalaxySystemsTile(tx, ty, baseUrl = DEFAULT_API_BASE, options = {}) {
  const revision = options.revision || null
  if (revision && options.preferCache !== false) {
    const cached = await getCachedTile(revision, tx, ty)
    if (cached) {
      return { ...cached, systems: applyJunctionCanonNames(cached.systems) }
    }
  }
  const query = new URLSearchParams({
    tx: String(tx),
    ty: String(ty),
  })
  const data = await fetchGalaxyJson(`/api/v1/galaxy/systems?${query}`, baseUrl, options)
  const tile = {
    tx: Number(data.tx ?? tx),
    ty: Number(data.ty ?? ty),
    systems: applyJunctionCanonNames(data.systems || []),
  }
  if (revision) {
    await setCachedTile(revision, tile.tx, tile.ty, tile.systems)
  }
  return tile
}

export async function persistGalaxyEdges(revision, edges) {
  if (!revision || !edges) return
  await setCachedEdges(revision, edges)
}

export async function persistGalaxySearch(revision, search) {
  if (!revision || !search) return
  await setCachedSearch(revision, search)
}

export async function persistGalaxySystemsSnapshot(revision, systems) {
  if (!revision || !systems?.length) return
  await setCachedSystemsSnapshot(revision, systems)
}

/** Split a full systems list into spatial tiles for the next warm start. */
export async function persistGalaxyTilesFromSystems(revision, systems, tileGrid) {
  if (!revision || !systems?.length || !tileGrid?.size) return
  const size = Number(tileGrid.size) || 0
  const mapLim = Number(tileGrid.mapLim) || DEFAULT_MAP_LIM
  if (size <= 0) return
  const buckets = new Map()
  for (const system of systems) {
    const { tx, ty } = tileCoordsForPoint(system.x, system.y, mapLim, size)
    const key = `${tx}:${ty}`
    let list = buckets.get(key)
    if (!list) {
      list = []
      buckets.set(key, list)
    }
    list.push(system)
  }
  await mapPool([...buckets.entries()], 8, async ([key, list]) => {
    const [tx, ty] = key.split(':').map(Number)
    await setCachedTile(revision, tx, ty, list)
  })
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
  const data = await fetchGalaxyJson('/api/v1/galaxy', baseUrl, {
    timeoutMs: 90000,
    ...options,
  })
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

function junctionCanonEntry(system) {
  if (!system) return null
  if (junctionCanonNames[system.id]) return junctionCanonNames[system.id]
  const token = system.token || (system.id || '').split(':').pop()
  if (!token) return null
  const idStem = (system.id || '').split(':')[0]
  for (const stem of [idStem, system.canonicalStem, system.stem]) {
    if (!stem) continue
    const hit = junctionCanonNames[`${stem}:${token}`]
    if (hit) return hit
  }
  return null
}

function junctionDisplayName(system, locale = 'ru') {
  if (locale === 'ru') {
    if (isPureCyrillicName(system.nameRu)) return system.nameRu.trim()
    const canon = junctionCanonEntry(system)?.nameRu?.trim()
    if (isPureCyrillicName(canon)) return canon
    return ''
  }
  const canon = junctionCanonEntry(system)?.nameEn?.trim()
  if (canon) return canon
  const cleaned = (system.nameEn || '').replace(/\s+Junction$/i, '').trim()
  return cleaned || system.token?.trim() || ''
}

export function systemLabel(system, locale = 'ru') {
  if (system?.kind === 'junction') {
    return (
      junctionDisplayName(system, locale) ||
      (locale === 'en' ? 'Hypercorridor junction' : 'Стык гиперкоридоров')
    )
  }
  const label = locale === 'en' ? system.nameEn : system.nameRu
  if (label?.trim()) return label
  if (system.kind === 'black_hole') {
    return locale === 'en' ? 'Unnamed black hole' : 'Безымянная чёрная дыра'
  }
  return locale === 'en' ? 'Unnamed star' : 'Безымянная звезда'
}

/** Map-side English id under the title (= compact nameEn; not a canon Token field). */
export function systemSignature(system) {
  if (!system) return ''
  if (system.kind === 'junction') return system.token || ''
  const en = system.nameEn?.trim()
  if (en) return en.replace(/[^A-Za-z0-9]+/g, '')
  return system.token || ''
}

export function polityLabel(polity, locale = 'ru') {
  if (!polity) return ''
  return locale === 'en' ? polity.nameEn : polity.nameRu
}
