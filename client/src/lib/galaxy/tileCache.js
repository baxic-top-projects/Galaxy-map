/**
 * Persistent tile/map cache (IndexedDB) so a refresh can paint from local data
 * like a map app, then revalidate against the network.
 */

const DB_NAME = 'galaxy-map-cache'
const DB_VERSION = 1
const STORE = 'entries'

/** @type {IDBDatabase | null} */
let dbPromise = null
/** In-memory fallback when IndexedDB is unavailable (SSR/tests). */
const memory = new Map()

export function catalogRevisionFromMap(map) {
  const meta = map?.meta || {}
  const grid = map?.tileGrid || {}
  return [
    meta.systemCount ?? '',
    meta.edgeCountDisplay ?? '',
    meta.edgeCountCanon ?? '',
    meta.mapLim ?? '',
    meta.centralDiskR ?? '',
    meta.source ?? '',
    meta.seed ?? '',
    grid.size ?? '',
    grid.mapLim ?? '',
    (map?.polities || []).length,
    (map?.systems || []).length,
  ].join('|')
}

function memoryGet(key) {
  return memory.get(key) ?? null
}

function memorySet(key, value) {
  memory.set(key, value)
}

function memoryDeletePrefix(prefix) {
  for (const key of [...memory.keys()]) {
    if (key.startsWith(prefix)) memory.delete(key)
  }
}

function openDb() {
  if (typeof indexedDB === 'undefined') return null
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onerror = () => reject(request.error)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    request.onsuccess = () => resolve(request.result)
  }).catch(() => null)
  return dbPromise
}

async function idbGet(key) {
  const db = await openDb()
  if (!db) return memoryGet(key)
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).get(key)
    req.onsuccess = () => resolve(req.result ?? null)
    req.onerror = () => reject(req.error)
  }).catch(() => memoryGet(key))
}

async function idbSet(key, value) {
  const db = await openDb()
  if (!db) {
    memorySet(key, value)
    return
  }
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  }).catch(() => {
    memorySet(key, value)
  })
}

async function idbDelete(key) {
  const db = await openDb()
  if (!db) {
    memory.delete(key)
    return
  }
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite')
    tx.objectStore(STORE).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  }).catch(() => {
    memory.delete(key)
  })
}

async function idbKeys() {
  const db = await openDb()
  if (!db) return [...memory.keys()]
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly')
    const req = tx.objectStore(STORE).getAllKeys()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  }).catch(() => [...memory.keys()])
}

function mapKey(revision) {
  return `map:${revision}`
}

function tileKey(revision, tx, ty) {
  return `tile:${revision}:${tx}:${ty}`
}

function edgesKey(revision) {
  return `edges:${revision}`
}

function searchKey(revision) {
  return `search:${revision}`
}

function systemsSnapshotKey(revision) {
  return `systems:${revision}`
}

function politicalPlateKey(revision) {
  return `politicalPlate:${revision}`
}

function revisionPointerKey() {
  return 'revision:current'
}

export async function clearTileCache() {
  const keys = await idbKeys()
  await Promise.all(keys.map((key) => idbDelete(key)))
  memory.clear()
}

export async function getCurrentCacheRevision() {
  return idbGet(revisionPointerKey())
}

export async function setCachedMap(revision, mapPayload) {
  await idbSet(mapKey(revision), {
    revision,
    savedAt: Date.now(),
    map: mapPayload,
  })
  await idbSet(revisionPointerKey(), revision)
}

export async function getCachedMap(revision = null) {
  const rev = revision || (await getCurrentCacheRevision())
  if (!rev) return null
  const entry = await idbGet(mapKey(rev))
  if (!entry?.map) return null
  return entry
}

export async function setCachedTile(revision, tx, ty, systems) {
  await idbSet(tileKey(revision, tx, ty), {
    revision,
    tx,
    ty,
    systems: systems || [],
    savedAt: Date.now(),
  })
}

export async function getCachedTile(revision, tx, ty) {
  const entry = await idbGet(tileKey(revision, tx, ty))
  if (!entry) return null
  return {
    tx: entry.tx,
    ty: entry.ty,
    systems: entry.systems || [],
  }
}

export async function listCachedTiles(revision) {
  const prefix = `tile:${revision}:`
  const keys = await idbKeys()
  const tileKeys = keys.filter((key) => String(key).startsWith(prefix))
  const tiles = []
  for (const key of tileKeys) {
    const entry = await idbGet(key)
    if (!entry) continue
    tiles.push({
      tx: entry.tx,
      ty: entry.ty,
      systems: entry.systems || [],
    })
  }
  return tiles
}

export async function setCachedEdges(revision, edges) {
  await idbSet(edgesKey(revision), {
    revision,
    edgesCanon: edges?.edgesCanon || [],
    edgesDisplay: edges?.edgesDisplay || [],
    savedAt: Date.now(),
  })
}

export async function getCachedEdges(revision) {
  const entry = await idbGet(edgesKey(revision))
  if (!entry) return null
  return {
    edgesCanon: entry.edgesCanon || [],
    edgesDisplay: entry.edgesDisplay || [],
  }
}

export async function setCachedSearch(revision, search) {
  await idbSet(searchKey(revision), {
    revision,
    search: search || [],
    savedAt: Date.now(),
  })
}

export async function getCachedSearch(revision) {
  const entry = await idbGet(searchKey(revision))
  if (!entry) return null
  return entry.search || []
}

export async function setCachedSystemsSnapshot(revision, systems) {
  await idbSet(systemsSnapshotKey(revision), {
    revision,
    systems: systems || [],
    savedAt: Date.now(),
  })
}

export async function getCachedSystemsSnapshot(revision) {
  const entry = await idbGet(systemsSnapshotKey(revision))
  if (!entry) return null
  return entry.systems || null
}

export async function setCachedPoliticalPlate(revision, payload) {
  await idbSet(politicalPlateKey(revision), {
    revision,
    blob: payload.blob,
    labelAnchors: payload.labelAnchors || {},
    territoryAreas: payload.territoryAreas || {},
    labelMetrics: payload.labelMetrics || {},
    rasterSize: payload.rasterSize || 1,
    mapLim: payload.mapLim,
    savedAt: Date.now(),
  })
}

export async function getCachedPoliticalPlate(revision) {
  const entry = await idbGet(politicalPlateKey(revision))
  if (!entry?.blob) return null
  return entry
}

export async function listCachedTileKeys(revision) {
  const prefix = `tile:${revision}:`
  const keys = await idbKeys()
  return keys
    .map((key) => String(key))
    .filter((key) => key.startsWith(prefix))
    .map((key) => {
      const parts = key.split(':')
      return `${parts[parts.length - 2]}:${parts[parts.length - 1]}`
    })
}

/**
 * Warm-start payload assembled from IndexedDB for an instant first paint.
 */
export async function loadGalaxyWarmCache() {
  const entry = await getCachedMap()
  if (!entry?.map) return null
  const revision = entry.revision
  const snapshot = await getCachedSystemsSnapshot(revision)
  const tileKeys = await listCachedTileKeys(revision)
  const edges = await getCachedEdges(revision)
  const search = await getCachedSearch(revision)
  let systems = snapshot
  if (!systems) {
    const tiles = await listCachedTiles(revision)
    const byId = new Map()
    for (const system of entry.map.systems || []) byId.set(system.id, system)
    for (const tile of tiles) {
      for (const system of tile.systems || []) byId.set(system.id, system)
    }
    systems = Array.from(byId.values())
  }
  const gridSize = Number(entry.map.tileGrid?.size) || 0
  const expectedTiles = gridSize > 0 ? gridSize * gridSize : 0
  const hasPlate = Boolean(await getCachedPoliticalPlate(revision))
  return {
    revision,
    tileKeys,
    map: entry.map,
    systems,
    edgesCanon: edges?.edgesCanon || [],
    edgesDisplay: edges?.edgesDisplay || [],
    search: search || [],
    systemsHydrated:
      Boolean(snapshot?.length) ||
      (expectedTiles > 0 && tileKeys.length >= expectedTiles),
    hasPoliticalPlate: hasPlate,
  }
}

/** Test helper: wipe memory fallback. */
export function __resetTileCacheMemoryForTests() {
  memory.clear()
  dbPromise = null
  memoryDeletePrefix('')
}
