/** Map canon type keys to public model / texture paths. */

const STAR_FALLBACK = {
  binary_class_g: 'class_g',
  class_m_giant: 'class_m',
  neutron_star: 'pulsar',
  supermassive_black_hole: 'black_hole',
}

const PLANET_FALLBACK = {
  ecumenopolis: 'continental',
  alpine: 'tundra',
}

export function starModelPath(typeKey) {
  return `/models/stars/star_type_${typeKey}.glb`
}

export function starPreviewPath(typeKey) {
  return `/models/stars/star_type_${typeKey}_preview.png`
}

export function starTypeArtPath(typeKey) {
  return `/textures/star_types/star_type_${typeKey}.png`
}

export function planetModelPath(typeKey) {
  return `/models/planets/planet_type_${typeKey}.glb`
}

export function planetPreviewPath(typeKey) {
  return `/models/planets/planet_type_${typeKey}_preview.png`
}

export function planetTypeArtPath(typeKey) {
  return `/textures/planet_types/planet_type_${typeKey}.png`
}

export function resolveStarTypeKey(typeKey) {
  return typeKey || 'class_g'
}

export function resolvePlanetTypeKey(typeKey) {
  return typeKey || 'continental'
}

export function starFallbackKey(typeKey) {
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
