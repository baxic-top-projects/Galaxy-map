/** Map canon type keys to public model / texture paths. */

const STAR_FALLBACK = {
  binary_class_g: 'class_g',
  triple_class_g: 'class_g',
  trinary_class_g: 'class_g',
  class_m_giant: 'class_m',
  neutron_star: 'pulsar',
}

const PLANET_FALLBACK = {
  ecumenopolis: 'continental',
  alpine: 'tundra',
  moon: 'barren',
}

/** @type {string} */
let assetsBaseUrl = String(import.meta.env.VITE_ASSETS_BASE || '').replace(/\/$/, '')

/**
 * @typedef {{ url?: string, previewUrl?: string|null, artUrl?: string|null }} RemoteAsset
 */

/** @type {{
 *  stars: Map<string, RemoteAsset>,
 *  planets: Map<string, RemoteAsset>,
 *  features: Map<string, RemoteAsset>,
 * } | null} */
let remoteCatalog = null

function joinAssetUrl(path) {
  const normalized = path.startsWith('/') ? path : `/${path}`
  if (!assetsBaseUrl) return normalized
  return `${assetsBaseUrl}${normalized}`
}

/**
 * Optional remote catalog from asset-service / S3 manifest.
 * @param {{
 *   publicBaseUrl?: string,
 *   stars?: Array<RemoteAsset & { key: string }>,
 *   planets?: Array<RemoteAsset & { key: string }>,
 *   features?: Array<RemoteAsset & { key: string }>,
 * } | null | undefined} manifest
 */
export function applyAssetManifest(manifest) {
  if (!manifest) {
    remoteCatalog = null
    return
  }
  if (manifest.publicBaseUrl) {
    assetsBaseUrl = String(manifest.publicBaseUrl).replace(/\/$/, '')
  }
  const toMap = (rows = []) =>
    new Map(
      rows.map((row) => [
        row.key,
        {
          url: row.url,
          previewUrl: row.previewUrl || null,
          artUrl: row.artUrl || null,
        },
      ]),
    )
  remoteCatalog = {
    stars: toMap(manifest.stars),
    planets: toMap(manifest.planets),
    features: toMap(manifest.features),
  }
}

export function getAssetsBaseUrl() {
  return assetsBaseUrl
}

export function starModelPath(typeKey) {
  const remote = remoteCatalog?.stars.get(typeKey)?.url
  if (remote) return remote
  return joinAssetUrl(`/models/stars/star_type_${typeKey}.glb`)
}

export function starPreviewPath(typeKey) {
  const remote = remoteCatalog?.stars.get(typeKey)?.previewUrl
  if (remote) return remote
  return joinAssetUrl(`/models/stars/star_type_${typeKey}_preview.png`)
}

export function starTypeArtPath(typeKey) {
  const remote = remoteCatalog?.stars.get(typeKey)?.artUrl
  if (remote) return remote
  return joinAssetUrl(`/textures/star_types/star_type_${typeKey}.png`)
}

export function planetModelPath(typeKey) {
  const remote = remoteCatalog?.planets.get(typeKey)?.url
  if (remote) return remote
  return joinAssetUrl(`/models/planets/planet_type_${typeKey}.glb`)
}

export function planetPreviewPath(typeKey) {
  const remote = remoteCatalog?.planets.get(typeKey)?.previewUrl
  if (remote) return remote
  return joinAssetUrl(`/models/planets/planet_type_${typeKey}_preview.png`)
}

export function planetTypeArtPath(typeKey) {
  const remote = remoteCatalog?.planets.get(typeKey)?.artUrl
  if (remote) return remote
  return joinAssetUrl(`/textures/planet_types/planet_type_${typeKey}.png`)
}

export function featureModelPath(featureKey = 'asteroid_belt') {
  const remote = remoteCatalog?.features.get(featureKey)?.url
  if (remote) return remote
  return joinAssetUrl(`/models/features/system_feature_${featureKey}.glb`)
}

export function featurePreviewPath(featureKey = 'asteroid_belt') {
  const remote = remoteCatalog?.features.get(featureKey)?.previewUrl
  if (remote) return remote
  return joinAssetUrl(`/models/features/system_feature_${featureKey}_preview.png`)
}

export function featureArtPath(featureKey = 'asteroid_belt') {
  const remote = remoteCatalog?.features.get(featureKey)?.artUrl
  if (remote) return remote
  return joinAssetUrl(`/textures/system_features/system_feature_${featureKey}.png`)
}

/** Map / UI textures stored at textures/<name> in S3. */
export function mapTexturePath(fileName, cacheBust = '') {
  const url = joinAssetUrl(`/textures/${fileName}`)
  return cacheBust ? `${url}${url.includes('?') ? '&' : '?'}${cacheBust}` : url
}

export function resolveFeatureKey(feature) {
  const raw = String(feature || '').toLowerCase()
  if (raw.includes('asteroid')) return 'asteroid_belt'
  return 'asteroid_belt'
}

export function resolveStarTypeKey(typeKey, kind = 'star') {
  if (kind === 'well') return 'supermassive_black_hole'
  if (kind === 'black_hole') return 'black_hole'
  return typeKey || 'class_g'
}

export function resolvePlanetTypeKey(typeKey) {
  return typeKey || 'continental'
}

export function starFallbackKey(typeKey) {
  if (typeKey === 'black_hole' || typeKey === 'supermassive_black_hole') return typeKey
  return STAR_FALLBACK[typeKey] || 'class_g'
}

export function planetFallbackKey(typeKey) {
  return PLANET_FALLBACK[typeKey] || 'continental'
}

export function starColor(typeKey) {
  switch (typeKey) {
    case 'class_m':
    case 'class_m_giant':
      return 0xff6b4a
    case 'class_k':
      return 0xffb347
    case 'class_g':
    case 'binary_class_g':
    case 'triple_class_g':
    case 'trinary_class_g':
      return 0xffe08a
    case 'class_f':
      return 0xfff4c8
    case 'class_a':
      return 0xd7ecff
    case 'class_b':
      return 0x8ec7ff
    case 'pulsar':
    case 'neutron_star':
      return 0xb8d4ff
    case 'black_hole':
    case 'supermassive_black_hole':
      return 0xff66aa
    default:
      return 0xd7ecff
  }
}
